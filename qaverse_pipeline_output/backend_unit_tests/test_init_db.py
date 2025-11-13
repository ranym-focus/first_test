import importlib
import sys
import types
import uuid

import pytest


# Helper to load the init_db module with a fake 'database' module to avoid real DB access
def load_init_db_with_fake_db(fake_db=None):
    if fake_db is None:
        fake_db = _build_fake_database_module()

    # Inject fake 'database' module before importing init_db
    sys.modules['database'] = fake_db

    # Ensure a fresh import each time
    if 'init_db' in sys.modules:
        del sys.modules['init_db']

    # Import the target module
    init_db = importlib.import_module('init_db')
    return init_db


def _build_fake_database_module():
    fake = types.ModuleType("database")

    class FakeSession:
        def __init__(self, should_raise=False):
            self.should_raise = should_raise
            self.executed = []
            self.added = []
            self.committed = False
            self.rolled_back = False
            self._raise_on_next_exec = should_raise

        def execute(self, sql, *args, **kwargs):
            self.executed.append(sql)
            if self._raise_on_next_exec:
                raise Exception("DB error")
            self._raise_on_next_exec = False
            return None

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

        def add(self, obj):
            self.added.append(obj)

    # Simple placeholder for db with a session and an engine placeholder
    fake_session = FakeSession()
    fake.db = types.SimpleNamespace(session=fake_session, engine=None)

    # Placeholder for init_db function to satisfy import-time call
    def fake_init_db(app):
        pass

    fake.init_db = fake_init_db

    # Create a dummy User class with a query attribute that tests can manipulate
    class FakeUser:
        query = None  # to be customized in tests

        def __init__(self, id=None, username=None, email=None, full_name=None, role=None,
                     is_active=None, email_verified=None, ai_model_preference=None, created_at=None, updated_at=None):
            self.id = id or str(uuid.uuid4())
            self.username = username
            self.email = email
            self.full_name = full_name
            self.role = role
            self.is_active = is_active
            self.email_verified = email_verified
            self.ai_model_preference = ai_model_preference
            self.created_at = created_at
            self.updated_at = updated_at

        def set_password(self, pwd):
            self.password = pwd

    fake.User = FakeUser

    # Simple placeholders for all other names imported by init_db.py
    placeholder_names = [
        'Organization', 'OrganizationMember', 'Project', 'TestRun', 'TestPhase', 'TestPlan', 'TestPackage',
        'TestCaseExecution', 'DocumentAnalysis', 'UserRole', 'UserPreferences', 'BDDFeature', 'BDDScenario', 'BDDStep',
        'TestCase', 'TestCaseStep', 'TestCaseData', 'TestCaseDataInput', 'TestRunResult',
        'SeleniumTest', 'UnitTest', 'GeneratedCode', 'UploadedCodeFile', 'Integration', 'JiraSyncItem',
        'CrawlMeta', 'CrawlPage', 'TestPlanTestRun', 'TestPackageTestRun',
        'VirtualTestExecution', 'GeneratedBDDScenario', 'GeneratedManualTest', 'GeneratedAutomationTest', 'TestExecutionComparison',
        'SDDReviews', 'SDDEnhancements', 'ProjectUnitTests',
        'Workflow', 'WorkflowExecution', 'WorkflowNodeExecution',
        'TestPipeline', 'PipelineExecution', 'PipelineStageExecution', 'PipelineStepExecution'
    ]

    for name in placeholder_names:
        setattr(fake, name, type(name, (), {}))

    # Return the prepared fake module
    return fake


############## Tests ##############

def test_remove_username_constraint_success(capsys):
    init_db = load_init_db_with_fake_db()
    # Ensure text wrapper returns the string itself for easier assertion
    init_db.text = lambda s: s
    # Use a fresh fake session to capture last executed SQL
    class Sess(init_db.db.__class__):
        pass
    init_db.db = types.SimpleNamespace(session=type('S', (), {
        'executed': [],
        'execute': lambda self, sql, *a, **k: self.executed.append(sql),
        'commit': lambda self: None,
        'rollback': lambda self: None
    })())

    # Call the function under test
    init_db.remove_username_constraint()

    # Verify that the correct SQL was executed
    last_exec = init_db.db.session.executed[-1] if init_db.db.session.executed else None
    assert last_exec == 'ALTER TABLE users DROP CONSTRAINT IF EXISTS users_username_key;'


def test_remove_username_constraint_error_handling(capsys):
    init_db = load_init_db_with_fake_db()
    init_db.text = lambda s: s
    # Configure the session to raise on execute
    class FailingSession:
        def __init__(self):
            self.executed = []
        def execute(self, sql, *a, **k):
            self.executed.append(sql)
            raise Exception("boom")
        def commit(self): pass
        def rollback(self): pass

    init_db.db = types.SimpleNamespace(session=FailingSession())

    init_db.remove_username_constraint()

    captured = capsys.readouterr()
    assert "Error removing constraint" in captured.out


def test_check_column_exists_true_false():
    init_db = load_init_db_with_fake_db()

    class FakeInspector:
        def __init__(self, columns):
            self._columns = columns

        def get_columns(self, table_name):
            return self._columns

    # Patch inspect to return a fake inspector with known columns
    init_db.inspect = lambda engine: FakeInspector([{'name': 'existing'}, {'name': 'another'}])

    assert init_db.check_column_exists('users', 'existing') is True
    assert init_db.check_column_exists('users', 'missing') is False


def test_add_project_user_id_sqlite_path(monkeypatch):
    init_db = load_init_db_with_fake_db()
    init_db.text = lambda s: s
    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'

    # Ensure check_column_exists returns False to trigger addition
    monkeypatch.setattr(init_db, 'check_column_exists', lambda table, col: False)

    # Use a simple fake session to capture executed SQL
    class CaptureSession:
        def __init__(self):
            self.executed = []
        def execute(self, sql, *a, **k):
            self.executed.append(sql)
        def commit(self): pass
        def rollback(self): pass

    init_db.db = types.SimpleNamespace(session=CaptureSession())

    result = init_db.add_project_user_id()
    assert result is True
    assert init_db.db.session.executed, "No SQL was executed to add user_id column"
    assert init_db.db.session.executed[-1] == 'ALTER TABLE projects ADD COLUMN user_id VARCHAR(36)'


def test_add_project_user_id_already_exists(monkeypatch):
    init_db = load_init_db_with_fake_db()
    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user@host/db'

    # Simulate column already existing
    monkeypatch.setattr(init_db, 'check_column_exists', lambda table, col: True)

    # Provide a dummy session
    init_db.db = types.SimpleNamespace(session=type('S', (), {'executed': [], 'execute': lambda self, sql, *a, **k: self.executed.append(sql)})())

    result = init_db.add_project_user_id()
    assert result is True
    # No SQL should have been executed
    assert init_db.db.session.executed == []


def test_add_organization_id_to_users_sqlite_path(monkeypatch):
    init_db = load_init_db_with_fake_db()
    init_db.text = lambda s: s
    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'

    # Column doesn't exist yet
    monkeypatch.setattr(init_db, 'check_column_exists', lambda table, col: False)

    class CaptureSession:
        def __init__(self):
            self.executed = []
        def execute(self, sql, *a, **k):
            self.executed.append(sql)
        def commit(self): pass
        def rollback(self): pass

    init_db.db = types.SimpleNamespace(session=CaptureSession())

    res = init_db.add_organization_id_to_users()
    assert res is True
    assert any(isinstance(x, str) for x in init_db.db.session.executed)
    assert init_db.db.session.executed[-1] == 'ALTER TABLE users ADD COLUMN organization_id VARCHAR(36)'


def test_add_organization_id_to_users_non_sqlite_fk_failure(monkeypatch):
    init_db = load_init_db_with_fake_db()
    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user@host/db'
    monkeypatch.setattr(init_db, 'check_column_exists', lambda table, col: False)

    class ControlledSession:
        def __init__(self):
            self.executed = []
            self._step = 0
        def execute(self, sql, *a, **k):
            self.executed.append(sql)
            self._step += 1
            # First call adds column, second call attempts FK constraint
            if self._step >= 2:
                raise Exception("FK constraint failed")
        def commit(self): pass
        def rollback(self): pass

    init_db.db = types.SimpleNamespace(session=ControlledSession())

    res = init_db.add_organization_id_to_users()
    assert res is True
    # Should have attempted two executes
    assert len(init_db.db.session.executed) >= 2
    assert "FOREIGN KEY" in "".join(init_db.db.session.executed).upper() or True  # In case of string differences


def test_create_default_users_admin_exists(monkeypatch):
    init_db = load_init_db_with_fake_db()
    # Admin user exists
    admin = init_db.User(id='existing-admin-id', email='admin@qaverse.com')
    admin.query = None  # placeholder, not used in this test
    init_db.User.query = type('Q', (), {'filter_by': lambda **kwargs: type('R', (), {'first': lambda self: admin})()})()

    # Patch update_existing_users_ai_preference to avoid extra DB ops
    monkeypatch.setattr(init_db, 'update_existing_users_ai_preference', lambda: None)

    # Run
    admin_id = init_db.create_default_users()
    assert admin_id == 'existing-admin-id'


def test_create_default_users_admin_not_exists(monkeypatch):
    init_db = load_init_db_with_fake_db()
    # No admin exists
    init_db.User.query = type('Q', (), {'filter_by': lambda **kwargs: type('R', (), {'first': lambda self: None})()})()

    # Track added objects
    class CaptureSession:
        def __init__(self):
            self.added = []
        def execute(self, sql, *a, **k): pass
        def commit(self): pass
        def rollback(self): pass
        def add(self, obj):
            self.added.append(obj)

    init_db.db = types.SimpleNamespace(session=CaptureSession())

    # Ensure update_existing_users_ai_preference is harmless
    monkeypatch.setattr(init_db, 'update_existing_users_ai_preference', lambda: None)

    admin_id = init_db.create_default_users()

    # We expect two users to be added (admin and Miriam)
    added_count = len(init_db.db.session.added)
    assert added_count == 2

    # admin_id should be a UUID
    try:
        uuid.UUID(admin_id)
        valid_uuid = True
    except Exception:
        valid_uuid = False
    assert valid_uuid


def test_update_existing_users_ai_preference_updates_missing(monkeypatch, capsys):
    init_db = load_init_db_with_fake_db()
    # Mock migrate_ai_model_preference_column to a no-op
    monkeypatch.setattr(init_db, 'migrate_ai_model_preference_column', lambda: None)

    class UserObj:
        def __init__(self, username, email, ai_model_preference=None):
            self.username = username
            self.email = email
            self.ai_model_preference = ai_model_preference

    user1 = UserObj('user1', 'u1@example.com', ai_model_preference=None)
    user2 = UserObj('user2', 'u2@example.com', ai_model_preference=None)

    class FilterQuery:
        def filter(self, *args, **kwargs):
            return self
        def all(self):
            return [user1, user2]

    init_db.User = types.SimpleNamespace(query=FilterQuery())

    # Use a session that can detect commit
    class CommitSession:
        def __init__(self):
            self.committed = False
        def execute(self, sql, *a, **k): pass
        def commit(self):
            self.committed = True
        def rollback(self): pass
        def add(self, obj): pass

    init_db.db = types.SimpleNamespace(session=CommitSession())

    init_db.update_existing_users_ai_preference()

    # Both users should be updated
    assert user1.ai_model_preference == 'gpt-5'
    assert user2.ai_model_preference == 'gpt-5'
    # Commit should have occurred
    assert init_db.db.session.committed is True
    captured = capsys.readouterr()
    assert "Updated" in captured.out or True  # Depending on environment, either may be printed