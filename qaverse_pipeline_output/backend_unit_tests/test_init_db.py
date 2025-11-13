import sys
import importlib
import types
import uuid
from datetime import datetime

import pytest

# Helper to create a fake in-memory database module used by init_db.py
def create_fake_database_module(admin_existing_id=None):
    # Simple Admin stub used by User.query.filter_by(...).first()
    class AdminStub:
        def __init__(self, id):
            self.id = id

    # Fake query proxy to mimic User.query.filter_by(...).first()
    class FakeQueryProxy:
        def __init__(self, existing_id):
            self.existing_id = existing_id

        def filter_by(self, **kwargs):
            return self

        def first(self):
            if not self.existing_id:
                return None
            return AdminStub(self.existing_id)

    # Fake User model
    class FakeUser:
        _existing_admin = admin_existing_id
        # The query attribute is used as User.query.filter_by(...).first()
        query = FakeQueryProxy(_existing_admin)

        def __init__(self, id=None, username=None, email=None, full_name=None, role=None,
                     is_active=None, email_verified=None, ai_model_preference=None,
                     created_at=None, updated_at=None):
            self.id = id or str(uuid.uuid4())
            self.username = username
            self.email = email
            self.full_name = full_name
            self.role = role
            self.is_active = is_active
            self.email_verified = email_verified
            self.ai_model_preference = ai_model_preference
            self.created_at = created_at or datetime.now()
            self.updated_at = updated_at or datetime.now()
            self.password = None

        def set_password(self, password):
            self.password = password

    # Fake DB/session
    class FakeSession:
        def __init__(self):
            self.executed = []
            self.added = []
            self.committed = False
            self.rolled_back = False

        def execute(self, query):
            self.executed.append(query)

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

        def add(self, obj):
            self.added.append(obj)

    class FakeDB:
        def __init__(self):
            self.session = FakeSession()
            self.engine = object()  # placeholder for inspect(engine)

    # Stubs for many classes referenced by init_db.py to satisfy imports
    placeholder_class = type('Placeholder', (), {})

    # Build fake database module
    mod = types.ModuleType('database')
    mod.db = FakeDB()
    mod.User = FakeUser
    mod.Organization = placeholder_class
    mod.OrganizationMember = placeholder_class
    mod.Project = placeholder_class
    mod.TestRun = placeholder_class
    mod.TestPhase = placeholder_class
    mod.TestPlan = placeholder_class
    mod.TestPackage = placeholder_class
    mod.TestCaseExecution = placeholder_class
    mod.DocumentAnalysis = placeholder_class
    mod.UserRole = placeholder_class
    mod.UserPreferences = placeholder_class
    mod.BDDFeature = placeholder_class
    mod.BDDScenario = placeholder_class
    mod.BDDStep = placeholder_class
    mod.TestCase = placeholder_class
    mod.TestCaseStep = placeholder_class
    mod.TestCaseData = placeholder_class
    mod.TestCaseDataInput = placeholder_class
    mod.TestRunResult = placeholder_class
    mod.SeleniumTest = placeholder_class
    mod.UnitTest = placeholder_class
    mod.GeneratedCode = placeholder_class
    mod.UploadedCodeFile = placeholder_class
    mod.Integration = placeholder_class
    mod.JiraSyncItem = placeholder_class
    mod.CrawlMeta = placeholder_class
    mod.CrawlPage = placeholder_class
    mod.TestPlanTestRun = placeholder_class
    mod.TestPackageTestRun = placeholder_class
    mod.VirtualTestExecution = placeholder_class
    mod.GeneratedBDDScenario = placeholder_class
    mod.GeneratedManualTest = placeholder_class
    mod.GeneratedAutomationTest = placeholder_class
    mod.TestExecutionComparison = placeholder_class
    mod.SDDReviews = placeholder_class
    mod.SDDEnhancements = placeholder_class
    mod.ProjectUnitTests = placeholder_class
    mod.Workflow = placeholder_class
    mod.WorkflowExecution = placeholder_class
    mod.WorkflowNodeExecution = placeholder_class
    mod.TestPipeline = placeholder_class
    mod.PipelineExecution = placeholder_class
    mod.PipelineStageExecution = placeholder_class
    mod.PipelineStepExecution = placeholder_class

    # Fake init_db function to be called by init_db.py (no-op)
    def fake_init_db(app):
        return None
    mod.init_db = fake_init_db

    # Attach a minimal environment that init_db.py expects
    mod.__dict__['datetime'] = datetime
    return mod


# Helper to load init_db.py with the fake database module injected
def load_init_db_with_fake_db(admin_existing_id=None):
    if 'init_db' in sys.modules:
        del sys.modules['init_db']
    fake_db_module = create_fake_database_module(admin_existing_id)
    sys.modules['database'] = fake_db_module
    importlib.invalidate_caches()
    importlib.import_module('init_db')  # import to execute top-level code
    return sys.modules['init_db']


def test_remove_username_constraint_success(capfd):
    init_db = load_init_db_with_fake_db()
    init_db.remove_username_constraint()
    out = capfd.readouterr().out
    assert "✅ Username constraint removed successfully!" in out


def test_remove_username_constraint_failure(capfd):
    init_db = load_init_db_with_fake_db()
    # Make db.session.execute raise an exception to simulate failure
    def raise_exc(_):
        raise Exception("boom")
    init_db.db.session.execute = raise_exc
    init_db.remove_username_constraint()
    out = capfd.readouterr().out
    assert "❌ Error removing constraint" in out


def test_check_column_exists_true_false():
    init_db = load_init_db_with_fake_db()
    # Patch inspect to return a fake inspector with specified columns
    class FakeInspector:
        def __init__(self, cols):
            self._cols = cols
        def get_columns(self, table_name):
            return [{ 'name': c } for c in self._cols]

    # When column exists
    init_db.inspect = lambda engine: FakeInspector(['col1', 'col2'])
    assert init_db.check_column_exists('projects', 'col1') is True
    # When column does not exist
    assert init_db.check_column_exists('projects', 'col3') is False


def test_add_project_user_id_sqlite_and_already_exists(capfd):
    init_db = load_init_db_with_fake_db()
    # Ensure it's sqlite
    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'

    # Case: column does not exist yet
    init_db.check_column_exists = lambda table, column: False
    init_db.add_project_user_id()
    out = capfd.readouterr().out
    assert "user_id column added to projects table" in out

    # Case: column already exists
    init_db.check_column_exists = lambda table, column: True
    init_db.add_project_user_id()
    out = capfd.readouterr().out
    assert "✅ user_id column already exists in projects table." in out


def test_add_organization_id_to_users_exists_and_missing(capfd):
    init_db = load_init_db_with_fake_db()
    # Simulate sqlite or other DB; not critical for test
    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user@host/db'

    # When column doesn't exist yet
    init_db.check_column_exists = lambda table, column: False
    init_db.add_organization_id_to_users()
    out = capfd.readouterr().out
    assert "organization_id column added to users table" in out or "✅ organization_id column added to users table successfully!" in out

    # When column already exists
    init_db.check_column_exists = lambda table, column: True
    init_db.add_organization_id_to_users()
    out = capfd.readouterr().out
    # Should just skip with existing message
    assert "✅ organization_id column already exists in users table." in out


def test_create_default_users_admin_exists(capfd):
    # Admin already exists scenario
    admin_id = 'existing-admin-id'
    init_db = load_init_db_with_fake_db(admin_existing_id=admin_id)
    result = init_db.create_default_users()
    out = capfd.readouterr().out
    assert "Admin user already exists. Skipping user creation." in out
    assert result == admin_id


def test_create_default_users_creates_users_and_returns_admin_id(capfd):
    init_db = load_init_db_with_fake_db(admin_existing_id=None)

    # Prevent side effects from update_existing_users_ai_preference
    if hasattr(init_db, 'update_existing_users_ai_preference'):
        init_db.update_existing_users_ai_preference = lambda: None

    result = init_db.create_default_users()
    out = capfd.readouterr().out
    assert "Default users created successfully." in out
    assert isinstance(result, str)

    # Ensure two users were added to the fake db session
    added = getattr(init_db.db.session, 'added', [])
    assert len(added) == 2