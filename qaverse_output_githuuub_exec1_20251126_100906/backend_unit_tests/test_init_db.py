import sys
import types
import itertools
import importlib

# ----------------------------
# Setup fake environment for imports
# ----------------------------

# Fake dotenv.load_dotenv
fake_dotenv = types.ModuleType("dotenv")
fake_dotenv.load_dotenv = lambda: None
sys.modules["dotenv"] = fake_dotenv

# Fake sqlalchemy with minimal required API
fake_sqlalchemy = types.ModuleType("sqlalchemy")
def fake_text(sql):
    # Return the string directly to simplify testing
    return sql
class FakeInspect:
    def __init__(self, engine=None):
        self.engine = engine
    def get_columns(self, table_name):
        return []
fake_sqlalchemy.text = fake_text
fake_sqlalchemy.inspect = lambda engine=None: FakeInspect(engine)
sys.modules["sqlalchemy"] = fake_sqlalchemy

# Fake Flask
class FakeFlask:
    def __init__(self, name):
        self.config = {}
fake_flask = types.ModuleType("flask")
fake_flask.Flask = FakeFlask
sys.modules["flask"] = fake_flask

# Fake database module with placeholders
class DummySession:
    def __init__(self):
        self.executed = []
        self.committed = False
        self.rolled_back = False

    def execute(self, sql):
        self.executed.append(sql)
        return None

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

class DummyDB:
    def __init__(self):
        self.session = DummySession()
        self.engine = object()

dummy_db = DummyDB()

class DummyUser:
    query = type("Q", (), {"filter_by": lambda *args, **kwargs: DummyUserQuery(None)})  # placeholder
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "generated-id")
        self.username = kwargs.get("username", "")
        self.email = kwargs.get("email", "")
        self.full_name = kwargs.get("full_name", "")
        self.role = kwargs.get("role", "")
        self.is_active = kwargs.get("is_active", True)
        self.email_verified = kwargs.get("email_verified", False)
        self.ai_model_preference = kwargs.get("ai_model_preference", None)
        self.created_at = kwargs.get("created_at", None)
        self.updated_at = kwargs.get("updated_at", None)
    def set_password(self, pw):  # dummy
        self.password = pw

class DummyUserQuery:
    def __init__(self, result):
        self._result = result
    def filter_by(self, **kwargs):
        return self
    def first(self):
        return self._result

# Some spaces for required names in the import
placeholder_names = [
    "Organization", "OrganizationMember", "Project", "TestRun", "TestPhase", "TestPlan", "TestPackage",
    "TestCaseExecution", "DocumentAnalysis", "UserRole", "UserPreferences", "BDDFeature", "BDDScenario",
    "BDDStep", "TestCase", "TestCaseStep", "TestCaseData", "TestCaseDataInput", "TestRunResult", "SeleniumTest",
    "UnitTest", "GeneratedCode", "UploadedCodeFile", "Integration", "JiraSyncItem", "CrawlMeta", "CrawlPage",
    "TestPlanTestRun", "TestPackageTestRun", "VirtualTestExecution", "GeneratedBDDScenario", "GeneratedManualTest",
    "GeneratedAutomationTest", "TestExecutionComparison", "SDDReviews", "SDDEnhancements", "ProjectUnitTests",
    "Workflow", "WorkflowExecution", "WorkflowNodeExecution", "TestPipeline", "PipelineExecution",
    "PipelineStageExecution", "PipelineStepExecution"
]

fake_db_module = types.ModuleType("database")
# database.init_db is a dummy function to be overridden by tests
def dummy_init_db(app):
    return None
fake_db_module.init_db = dummy_init_db
fake_db_module.db = dummy_db
# Expose placeholder classes
for name in placeholder_names:
    setattr(fake_db_module, name, object)
# Expose User placeholder (we override in tests as needed)
fake_db_module.User = DummyUser

sys.modules["database"] = fake_db_module

# Import the module under test after setting up the environment
init_db = importlib.import_module("init_db")

# ----------------------------
# Unit tests
# ----------------------------

def test_remove_username_constraint_success(monkeypatch, capsys):
    # Ensure execute runs without error
    def fake_execute(sql):
        return None
    init_db.db.session.execute = fake_execute
    init_db.db.session.commit = lambda: None

    init_db.remove_username_constraint()

    captured = capsys.readouterr().out
    assert "✅ Username constraint removed successfully!" in captured

def test_remove_username_constraint_failure(monkeypatch, capsys):
    def fake_execute(sql):
        raise Exception("boom")
    init_db.db.session.execute = fake_execute
    rollback_called = {"flag": False}
    def fake_rollback():
        rollback_called["flag"] = True
    init_db.db.session.rollback = fake_rollback

    init_db.remove_username_constraint()

    captured = capsys.readouterr().out
    assert "❌ Error removing constraint" in captured
    assert rollback_called["flag"] is True

def test_check_column_exists_true(monkeypatch):
    class DummyInspector:
        def __init__(self, cols):
            self._cols = cols
        def get_columns(self, table_name):
            return self._cols
    dummy_cols = [{'name': 'id'}, {'name': 'organization_id'}, {'name': 'username'}]
    monkeypatch.setattr(init_db, "inspect", lambda engine=None: DummyInspector(dummy_cols))
    assert init_db.check_column_exists('users', 'organization_id') is True

def test_check_column_exists_false(monkeypatch):
    class DummyInspector:
        def __init__(self, cols):
            self._cols = cols
        def get_columns(self, table_name):
            return self._cols
    dummy_cols = [{'name': 'id'}, {'name': 'username'}]
    monkeypatch.setattr(init_db, "inspect", lambda engine=None: DummyInspector(dummy_cols))
    assert init_db.check_column_exists('users', 'organization_id') is False

def test_add_project_user_id_already_exists(monkeypatch, capsys):
    monkeypatch.setattr(init_db, "check_column_exists", lambda table, col: True)
    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:pass@host/db'
    init_db.db.session.execute = lambda sql: None
    init_db.db.session.commit = lambda: None

    result = init_db.add_project_user_id()
    captured = capsys.readouterr().out
    assert result is True
    assert "✅ user_id column already exists in projects table." in captured

def test_add_project_user_id_success_postgresql(monkeypatch):
    # Simulate column not existing
    monkeypatch.setattr(init_db, "check_column_exists", lambda table, col: False)
    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:pass@host/db'
    seen_sql = {}

    def fake_execute(sql):
        seen_sql['sql'] = sql
        return None

    init_db.db.session.execute = fake_execute
    init_db.db.session.commit = lambda: None

    result = init_db.add_project_user_id()
    assert result is True
    assert "ALTER TABLE projects ADD COLUMN user_id VARCHAR(36)" in seen_sql['sql']

def test_add_project_user_id_error(monkeypatch):
    monkeypatch.setattr(init_db, "check_column_exists", lambda table, col: False)
    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:pass@host/db'
    def fake_execute(sql):
        raise Exception("boom")
    init_db.db.session.execute = fake_execute
    init_db.db.session.rollback = lambda: None

    result = init_db.add_project_user_id()
    assert result is False

def test_add_organization_id_to_users_exists(monkeypatch, capsys):
    monkeypatch.setattr(init_db, "check_column_exists", lambda table, col: True)
    result = init_db.add_organization_id_to_users()
    captured = capsys.readouterr().out
    assert result is True
    assert "✅ organization_id column already exists in users table." in captured

def test_add_organization_id_to_users_success_sqlite(monkeypatch):
    monkeypatch.setattr(init_db, "check_column_exists", lambda table, col: False)
    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
    seen = {}
    def fake_execute(sql):
        seen['sql'] = sql
        return None
    init_db.db.session.execute = fake_execute
    init_db.db.session.commit = lambda: None

    result = init_db.add_organization_id_to_users()
    assert result is True
    assert "ALTER TABLE users ADD COLUMN organization_id VARCHAR(36)" in seen['sql']

def test_create_default_users_admin_exists(monkeypatch):
    # Simulate that an admin user already exists
    class AdminObj:
        def __init__(self):
            self.id = 'existing-admin-id'
    class DummyQuery:
        def filter_by(self, **kwargs):
            return self
        def first(self):
            return AdminObj()
    class DummyUserModel:
        query = DummyQuery()
        def __init__(self, **kwargs):
            self.id = kwargs.get('id', 'new-id')
        def set_password(self, pw):
            self.password = pw

    # Patch User model
    init_db.User = DummyUserModel
    # Ensure create_default_users returns the admin id
    result = init_db.create_default_users()
    assert result == 'existing-admin-id'

def test_create_default_users_admin_missing_calls_create_and_update(monkeypatch):
    # Admin does not exist
    class DummyQueryAllNone:
        def filter_by(self, **kwargs):
            return self
        def first(self):
            return None
    class DummyUserFactory:
        query = DummyQueryAllNone()
        def __init__(self, **kwargs):
            self.id = kwargs.get('id', 'generated-id')
        def set_password(self, pw):
            self.password = pw

    # Patch User to our factory
    init_db.User = DummyUserFactory

    # Patch uuid.uuid4 to generate deterministic IDs for admin and Miriam
    ids = itertools.cycle(['admin-id-1', 'miriam-id-1'])
    class FakeUUIDObj:
        def __str__(self):
            return next(ids)
    def fake_uuid4():
        return FakeUUIDObj()
    monkeypatch.setattr(init_db.uuid, "uuid4", fake_uuid4)

    captured_flags = {"commit_called": False}
    def fake_commit():
        captured_flags["commit_called"] = True
    init_db.db.session.commit = fake_commit

    # Patch add to do nothing
    init_db.db.session.add = lambda x: None

    # Patch update_existing_users_ai_preference to avoid side-effects
    monkeypatch.setattr(init_db, "update_existing_users_ai_preference", lambda: None)

    # Ensure returns admin_id from the first uuid4
    result = init_db.create_default_users()
    assert result == 'admin-id-1'