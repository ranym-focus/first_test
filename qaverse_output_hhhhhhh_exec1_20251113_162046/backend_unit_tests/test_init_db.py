import sys
import types
import uuid
import importlib
from pathlib import Path

import pytest

# Helper to build a fake 'database' module to be used by init_db.py during tests
def _build_fake_database_module(admin_exists=False, admin_user=None):
    fake = types.ModuleType('database')

    class DummySession:
        def __init__(self):
            self.calls = []
            self.raise_on_execute = False

        def execute(self, query, *args, **kwargs):
            if self.raise_on_execute:
                raise Exception("execute error")
            self.calls.append(('execute', query))
            return None

        def commit(self):
            self.calls.append(('commit',))

        def rollback(self):
            self.calls.append(('rollback',))

        def add(self, obj):
            self.calls.append(('add', obj))

    class DummyDB:
        def __init__(self):
            self.session = DummySession()

        @property
        def engine(self):
            return object()

    class FakeUserQuery:
        def __init__(self):
            self.admin_exists = admin_exists
            self.admin_user = admin_user

        def filter_by(self, **kwargs):
            if kwargs.get('email') == 'admin@qaverse.com' and self.admin_exists:
                return types.SimpleNamespace(first=lambda: self.admin_user)
            return types.SimpleNamespace(first=lambda: None)

    class FakeUser:
        query = FakeUserQuery()

        def __init__(self, **kwargs):
            self.id = kwargs.get('id', str(uuid.uuid4()))
            self.username = kwargs.get('username')
            self.email = kwargs.get('email')
            self.full_name = kwargs.get('full_name')
            self.role = kwargs.get('role')
            self.is_active = kwargs.get('is_active', True)
            self.email_verified = kwargs.get('email_verified', False)
            self.ai_model_preference = kwargs.get('ai_model_preference')
            self.created_at = kwargs.get('created_at', None)
            self.updated_at = kwargs.get('updated_at', None)
            self.password = None

        def set_password(self, pw):
            self.password = pw

    # Minimal fake 'init_db' function (to avoid side effects during import)
    fake.init_db = lambda app: None
    fake.db = DummyDB()
    fake.User = FakeUser

    # Stub out all other ORM models to avoid ImportError during module import
    placeholder_names = [
        "Organization", "OrganizationMember", "Project", "TestRun", "TestPhase", "TestPlan",
        "TestPackage", "TestCaseExecution", "DocumentAnalysis", "UserRole", "UserPreferences",
        "BDDFeature", "BDDScenario", "BDDStep", "TestCase", "TestCaseStep", "TestCaseData",
        "TestCaseDataInput", "TestRunResult", "SeleniumTest", "UnitTest", "GeneratedCode",
        "UploadedCodeFile", "Integration", "JiraSyncItem", "CrawlMeta", "CrawlPage", "TestPlanTestRun",
        "TestPackageTestRun", "VirtualTestExecution", "GeneratedBDDScenario", "GeneratedManualTest",
        "GeneratedAutomationTest", "TestExecutionComparison", "SDDReviews", "SDDEnhancements",
        "ProjectUnitTests", "Workflow", "WorkflowExecution", "WorkflowNodeExecution",
        "TestPipeline", "PipelineExecution", "PipelineStageExecution", "PipelineStepExecution",
    ]
    for name in placeholder_names:
        setattr(fake, name, type(name, (), {}))

    sys.modules['database'] = fake
    return fake


# Loader to initialize the init_db module with the fake database
def _load_init_db_with_fake_db(admin_exists=False, admin_user=None, sqlite_uri=False):
    fake_db = _build_fake_database_module(admin_exists=admin_exists, admin_user=admin_user)

    # Ensure a fresh import of init_db.py using the fake database
    if 'init_db' in sys.modules:
        del sys.modules['init_db']

    mod = importlib.import_module('init_db')

    # Expose sqlite config if needed by tests
    if sqlite_uri:
        mod.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    return mod


def test_remove_username_constraint_success(capfd):
    mod = _load_init_db_with_fake_db()
    mod.remove_username_constraint()
    out = capfd.readouterr().out
    assert "Username constraint removed successfully" in out or "Username constraint removed" in out


def test_remove_username_constraint_failure(capfd):
    mod = _load_init_db_with_fake_db()
    mod.db.session.raise_on_execute = True
    mod.remove_username_constraint()
    out = capfd.readouterr().out
    assert "Error removing constraint" in out or "❌ Error removing constraint" in out


def test_check_column_exists_true_false(monkeypatch):
    mod = _load_init_db_with_fake_db()

    class FakeInspector:
        def __init__(self, columns):
            self._columns = [{'name': c} for c in columns]
        def get_columns(self, table_name):
            return self._columns

    # Test exists
    monkeypatch.setattr(mod, 'inspect', lambda eng: FakeInspector(['id', 'username', 'email']))
    assert mod.check_column_exists('users', 'email') is True

    # Test does not exist
    monkeypatch.setattr(mod, 'inspect', lambda eng: FakeInspector(['id', 'username']))
    assert mod.check_column_exists('users', 'email') is False


def test_add_project_user_id_existing_column(capfd):
    mod = _load_init_db_with_fake_db()
    # Simulate that the column already exists
    mod.check_column_exists = lambda table, col: True
    result = mod.add_project_user_id()
    assert result is True
    out = capfd.readouterr().out
    assert "user_id column already exists" in out or "user_id column already exists" in out


def test_add_project_user_id_sqlite_path(capfd):
    mod = _load_init_db_with_fake_db()
    mod.check_column_exists = lambda table, col: False
    mod.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
    result = mod.add_project_user_id()
    assert result is True
    out = capfd.readouterr().out
    assert "Adding user_id column" in out or "user_id column added" in out


def test_add_project_user_id_error(capfd):
    mod = _load_init_db_with_fake_db()
    mod.check_column_exists = lambda table, col: False
    mod.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
    mod.db.session.raise_on_execute = True
    result = mod.add_project_user_id()
    assert result is False
    out = capfd.readouterr().out
    assert "Error adding user_id column" in out or "❌ Error" in out


def test_add_organization_id_to_users_existing_column(capfd):
    mod = _load_init_db_with_fake_db()
    mod.check_column_exists = lambda table, col: True
    result = mod.add_organization_id_to_users()
    assert result is True
    out = capfd.readouterr().out
    assert "organization_id column already exists" in out or "organization_id column already exists" in out


def test_add_organization_id_to_users_sqlite_path(capfd):
    mod = _load_init_db_with_fake_db()
    mod.check_column_exists = lambda table, col: False
    mod.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
    result = mod.add_organization_id_to_users()
    assert result is True
    out = capfd.readouterr().out
    assert "organization_id column added" in out or "Adding organization_id" in out


def test_create_default_users_admin_exists(capfd):
    admin_user = types.SimpleNamespace(id='admin-id', email='admin@qaverse.com')
    mod = _load_init_db_with_fake_db(admin_exists=True, admin_user=admin_user)
    admin_id = mod.create_default_users()
    assert admin_id == 'admin-id'
    out = capfd.readouterr().out
    assert "Admin user already exists" in out or "Admin user" in out


def test_create_default_users_admin_missing(cap):
    # Ensure update_existing_users_ai_preference is called during creation
    admin_user = types.SimpleNamespace(id='admin-id', email='admin@qaverse.com')
    mod = _load_init_db_with_fake_db(admin_exists=False, admin_user=admin_user)

    called = {'flag': False}
    def fake_update():
        called['flag'] = True
    mod.update_existing_users_ai_preference = fake_update

    admin_id = mod.create_default_users()
    assert isinstance(admin_id, str)
    assert called['flag'] is True


def test_update_existing_users_ai_preference_updates_users(capfd):
    mod = _load_init_db_with_fake_db()
    # Migrate column is a no-op in test
    mod.migrate_ai_model_preference_column = lambda: None

    user1 = types.SimpleNamespace(username='u1', ai_model_preference=None, email='u1@example.com')
    user2 = types.SimpleNamespace(username='u2', ai_model_preference='', email='u2@example.com')
    mod.User.query = types.SimpleNamespace(filter=lambda *a, **k: types.SimpleNamespace(all=lambda: [user1, user2]))

    mod.update_existing_users_ai_preference()
    assert user1.ai_model_preference == 'gpt-5'
    assert user2.ai_model_preference == 'gpt-5'
    # Ensure commit happened
    commits = [c for c in mod.db.session.calls if c[0] == 'commit']
    assert len(commits) >= 1


def test_update_existing_users_ai_preference_no_changes(capfd):
    mod = _load_init_db_with_fake_db()
    mod.migrate_ai_model_preference_column = lambda: None
    mod.User.query = types.SimpleNamespace(filter=lambda *a, **k: types.SimpleNamespace(all=lambda: []))

    mod.update_existing_users_ai_preference()
    # No changes, so no commit should be called
    commits = [c for c in mod.db.session.calls if c[0] == 'commit']
    assert len(commits) == 0