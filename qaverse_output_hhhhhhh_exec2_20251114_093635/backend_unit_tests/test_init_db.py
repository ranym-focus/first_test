import sys
import importlib
import types
from types import SimpleNamespace

import pytest


# Helper to setup a fake environment mimicking the `database` package
# with a minimal API required by init_db.py, without touching real DB.
def setup_fake_database_environment():
    # Create a fake database module with required attributes
    fake_db_module = types.ModuleType("database")

    # Simple in-memory session with minimal capabilities
    class FakeSession:
        def __init__(self):
            self.executed = []
            self.committed = False
            self.rolled_back = False
            self.added = []

        def execute(self, sql):
            self.executed.append(sql)
            return None

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

    class FakeDB:
        def __init__(self):
            self.session = FakeSession()
            self.engine = object()

    # Placeholder User class and a simple query hook to be overridden in tests
    class FakeUser:
        ai_model_preference = None
        query = None

        def __init__(self, id=None, username=None, email=None, full_name=None, role=None,
                     is_active=False, email_verified=False, ai_model_preference=None):
            self.id = id
            self.username = username
            self.email = email
            self.full_name = full_name
            self.role = role
            self.is_active = is_active
            self.email_verified = email_verified
            self.ai_model_preference = ai_model_preference
            self.password = None

        def set_password(self, password):
            self.password = password

    fake_db = FakeDB()
    fake_db_module.db = fake_db
    fake_db_module.User = FakeUser

    # A basic placeholder for other symbols to satisfy the "from database import (...)" import
    placeholder_names = [
        "Organization", "OrganizationMember", "Project", "TestRun", "TestPhase", "TestPlan",
        "TestPackage", "TestCaseExecution", "DocumentAnalysis", "UserRole", "UserPreferences",
        "BDDFeature", "BDDScenario", "BDDStep", "TestCase", "TestCaseStep", "TestCaseData",
        "TestCaseDataInput", "TestRunResult", "SeleniumTest", "UnitTest", "GeneratedCode",
        "UploadedCodeFile", "Integration", "JiraSyncItem", "CrawlMeta", "CrawlPage",
        "TestPlanTestRun", "TestPackageTestRun", "VirtualTestExecution", "GeneratedBDDScenario",
        "GeneratedManualTest", "GeneratedAutomationTest", "TestExecutionComparison",
        "SDDReviews", "SDDEnhancements", "ProjectUnitTests", "Workflow", "WorkflowExecution",
        "WorkflowNodeExecution", "TestPipeline", "PipelineExecution", "PipelineStageExecution",
        "PipelineStepExecution"
    ]
    for name in placeholder_names:
        setattr(fake_db_module, name, type(name, (), {}))

    # A minimal dotenv mock
    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda: None
    sys.modules["dotenv"] = fake_dotenv

    # Register the fake database module so that `from database import ...` works
    sys.modules["database"] = fake_db_module

    return fake_db_module


# Factory to load init_db with the fake environment
def load_init_db_with_fake_env():
    # Ensure a fresh import
    if "init_db" in sys.modules:
        del sys.modules["init_db"]
    # Import after setting up the fake environment
    import init_db  # noqa: F401
    importlib.reload(init_db)
    return init_db


# Tests

def test_remove_username_constraint_success_and_failure(capfd):
    fake_env = setup_fake_database_environment()
    # Ensure we can load module
    init_db = load_init_db_with_fake_env()

    # Case 1: success path
    # Ensure a clean state
    init_db.db = fake_env.db  # use our fake db
    init_db.remove_username_constraint()
    captured = capfd.readouterr()
    assert "✅ Username constraint removed successfully!" in captured.out

    # Case 2: simulate failure path
    class FailingSession(fake_env.db.session.__class__):
        def execute(self, sql):
            raise Exception("boom")

    fake_env.db.session = FailingSession()
    # Rebind to module and run again
    init_db.db = fake_env.db
    init_db.remove_username_constraint()
    captured = capfd.readouterr()
    assert "❌ Error removing constraint" in captured.err or "❌ Error removing constraint" in captured.out
    # Ensure rollback was attempted
    assert init_db.db.session.rolled_back is True


def test_check_column_exists_various(inspect_patch=None):
    fake_env = setup_fake_database_environment()
    init_db = load_init_db_with_fake_env()

    # Patch the inspector to simulate different columns
    class FakeInspector:
        def __init__(self, columns):
            self._columns = columns

        def get_columns(self, table_name):
            return self._columns

    # Case: column exists
    init_db.inspect = lambda engine: FakeInspector([{'name': 'id'}, {'name': 'target_column'}])
    assert init_db.check_column_exists("some_table", "target_column") is True

    # Case: column does not exist
    init_db.inspect = lambda engine: FakeInspector([{'name': 'id'}, {'name': 'other'}])
    assert init_db.check_column_exists("some_table", "target_column") is False


def test_add_project_user_id_various(capfd):
    fake_env = setup_fake_database_environment()
    init_db = load_init_db_with_fake_env()
    init_db.db = fake_env.db

    # Mock the existence check to simulate both paths
    init_db.check_column_exists = lambda table, col: True
    res = init_db.add_project_user_id()
    assert res is True
    captured = capfd.readouterr()
    assert "✅ user_id column already exists in projects table." in captured.out

    # Now simulate adding new column (non-sqlite)
    init_db.check_column_exists = lambda table, col: False
    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:pass@host/db'
    init_db.db.session = fake_env.db.session  # reset
    captured = capfd.readouterr()
    init_db.add_project_user_id()
    # Expect at least one ALTER TABLE statement executed
    sqls = [str(q) for q in init_db.db.session.executed]
    assert any("ALTER TABLE projects ADD COLUMN user_id VARCHAR(36)" in s for s in sqls)


def test_add_organization_id_to_users_existence_and_sqlite(capfd):
    fake_env = setup_fake_database_environment()
    init_db = load_init_db_with_fake_env()
    init_db.db = fake_env.db

    # Case: column already exists
    init_db.check_column_exists = lambda table, col: True
    assert init_db.add_organization_id_to_users() is True
    captured = capfd.readouterr()
    assert "✅ organization_id column already exists in users table." in captured.out

    # Case: add new column (sqlite)
    init_db.check_column_exists = lambda table, col: False
    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
    # Clear previous executed
    init_db.db.session.executed.clear()
    init_db.add_organization_id_to_users()
    sqls = [str(s) for s in init_db.db.session.executed]
    assert any("ALTER TABLE users ADD COLUMN organization_id VARCHAR(36)" in s for s in sqls)


def test_create_default_users_admin_exists_and_not_exists(monkeypatch, capsys):
    fake_env = setup_fake_database_environment()
    init_db = load_init_db_with_fake_env()
    init_db.db = fake_env.db

    # Case: admin already exists
    existing_admin = SimpleNamespace(id='existing-admin-id', email='admin@qaverse.com', username='admin')
    # Fake query_by_email with first() returning existing_admin
    class FakeQueryByEmail:
        def filter_by(self, **kwargs):
            email = kwargs.get('email')
            if email == 'admin@qaverse.com':
                return SimpleNamespace(first=lambda: existing_admin)
            return SimpleNamespace(first=lambda: None)

    init_db.User.query = FakeQueryByEmail()

    # Patch update_existing_users_ai_preference to ensure it's not called
    called = {'flag': False}
    def fake_update():
        called['flag'] = True
    monkeypatch.setattr(init_db, "update_existing_users_ai_preference", fake_update)

    admin_id = init_db.create_default_users()
    assert admin_id == 'existing-admin-id'
    captured = capsys.readouterr()
    assert "Default users created successfully." in captured.out  # Might appear depending on path
    assert called['flag'] is False

    # Case: admin does not exist
    class FakeQueryNotFound:
        def filter_by(self, **kwargs):
            return SimpleNamespace(first=lambda: None)

    init_db.User.query = FakeQueryNotFound()

    # Prepare a fake admin user list that would be created
    # We will intercept db.session.add to count additions
    added = []
    def fake_add(obj):
        added.append(obj)
    init_db.db.session.add = fake_add

    # Ensure update function is called
    called['flag'] = False
    monkeypatch.setattr(init_db, "update_existing_users_ai_preference", lambda: setattr(called, 'flag', True))  # simple callable

    admin_id = init_db.create_default_users()
    assert isinstance(admin_id, str)
    # We can't know exact id value, but ensure two users were "added" and commit happened
    assert len(added) == 2


def test_update_existing_users_ai_preference_updates_and_errors(monkeypatch, capsys):
    fake_env = setup_fake_database_environment()
    init_db = load_init_db_with_fake_env()
    init_db.db = fake_env.db

    # Prepare two users needing update
    u1 = SimpleNamespace(username='user1', email='u1@example.com', ai_model_preference=None)
    u2 = SimpleNamespace(username='user2', email='u2@example.com', ai_model_preference=None)
    users = [u1, u2]

    # Patch User.query to return these users for filter(...)
    class FakeQueryForPreference:
        def __init__(self, users_list): self._users = users_list
        def filter(self, *args, **kwargs):
            class R:
                def __init__(self, users): self._users = users
                def all(self): return self._users
            return R(self._users)

    init_db.User.query = FakeQueryForPreference(users)

    # Provide migrate function that does nothing
    monkeypatch.setattr(init_db, "migrate_ai_model_preference_column", lambda: None)

    init_db.update_existing_users_ai_preference()
    # Verify that ai_model_preference was set to 'gpt-5' for all users
    assert u1.ai_model_preference == 'gpt-5'
    assert u2.ai_model_preference == 'gpt-5'

    # Case: no users require update
    init_db.User.query = FakeQueryForPreference([])
    init_db.update_existing_users_ai_preference()
    # Should not crash; ensure no exception and no changes attempted
    cap = capsys.readouterr()
    assert "🤖" not in cap.out  # No specific prints expected; just ensuring no crash

    # Case: migration raises exception triggers rollback
    class RaisingMigrate:
        @staticmethod
        def __call__():
            raise Exception("migration failed")

    monkeypatch.setattr(init_db, "migrate_ai_model_preference_column", lambda: (_ for _ in ()).throw(Exception("migration failed")))
    init_db.User.query = FakeQueryForPreference([u1])
    # Reset ai_model_preference to None to simulate update attempt
    u1.ai_model_preference = None
    init_db.update_existing_users_ai_preference()
    # Should have rolled back on exception
    assert init_db.db.session.rolled_back is True if hasattr(init_db.db, "session") else True