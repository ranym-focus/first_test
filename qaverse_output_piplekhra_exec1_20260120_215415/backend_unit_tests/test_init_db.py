import sys
import types
import uuid
import importlib
import pytest

# ---------- Setup a fake database module before importing the target module ----------
def make_fake_database_module():
    mod = types.ModuleType("database")

    # A benign init_db function to prevent real DB migrations on import
    def fake_init_db(app=None):
        pass

    mod.init_db = fake_init_db

    # Lightweight placeholders for all names imported by init_db.py
    mod.db = types.SimpleNamespace(session=None)
    placeholder_names = [
        "User", "Organization", "OrganizationMember", "Project", "TestRun", "TestPhase",
        "TestPlan", "TestPackage", "TestCaseExecution", "DocumentAnalysis", "UserRole",
        "UserPreferences", "BDDFeature", "BDDScenario", "BDDStep", "TestCase", "TestCaseStep",
        "TestCaseData", "TestCaseDataInput", "TestRunResult", "SeleniumTest", "UnitTest",
        "GeneratedCode", "UploadedCodeFile", "Integration", "JiraSyncItem", "CrawlMeta",
        "CrawlPage", "TestPlanTestRun", "TestPackageTestRun", "VirtualTestExecution",
        "GeneratedBDDScenario", "GeneratedManualTest", "GeneratedAutomationTest",
        "TestExecutionComparison", "SDDReviews", "SDDEnhancements", "ProjectUnitTests",
        "Workflow", "WorkflowExecution", "WorkflowNodeExecution", "TestPipeline",
        "PipelineExecution", "PipelineStageExecution", "PipelineStepExecution"
    ]
    for name in placeholder_names:
        setattr(mod, name, object())

    return mod

fake_db = make_fake_database_module()
sys.modules["database"] = fake_db


# Import the target module after setting up the fake database to avoid real DB calls on import
import init_db as init_db  # type: ignore
importlib.reload(init_db)

# ---------- Tests start here ----------


class DummySession:
    def __init__(self, raise_on_execute=None):
        self.executed = []
        self.raised = raise_on_execute
        self.committed = False
        self.rolled_back = False

    def execute(self, sql):
        self.executed.append(str(sql))
        if self.raised:
            raise self.raised

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_remove_username_constraint_success(capfd):
    # Arrange
    dummy_db = types.SimpleNamespace(session=DummySession())
    init_db.db = dummy_db

    # Act
    init_db.remove_username_constraint()

    # Assert
    out = capfd.readouterr().out
    assert "Username constraint removed successfully" in out


def test_remove_username_constraint_failure(capfd):
    # Arrange
    dummy_db = types.SimpleNamespace(session=DummySession(raise_on_execute=Exception("boom")))
    init_db.db = dummy_db

    # Act
    init_db.remove_username_constraint()

    # Assert
    out = capfd.readouterr().out
    assert "❌ Error removing constraint" in out
    assert dummy_db.session.rolled_back is True


def test_check_column_exists_true_false():
    class FakeInspector:
        def __init__(self, cols):
            self._cols = cols
        def get_columns(self, table_name):
            return [{'name': c} for c in self._cols]

    # Case: column exists
    init_db.inspect = lambda eng: FakeInspector(['id', 'name', 'target_column'])
    assert init_db.check_column_exists('any_table', 'target_column') is True

    # Case: column does not exist
    init_db.inspect = lambda eng: FakeInspector(['id', 'name'])
    assert init_db.check_column_exists('any_table', 'target_column') is False


def test_add_project_user_id_already_exists(capfd):
    # Arrange
    init_db.check_column_exists = lambda table, col: True
    dummy_db = types.SimpleNamespace(session=DummySession())
    init_db.db = dummy_db

    # Act
    result = init_db.add_project_user_id()

    # Assert
    out = capfd.readouterr().out
    assert "user_id column already exists" in out
    assert result is True


def test_add_project_user_id_sqlite(capfd):
    # Arrange: sqlite path and column does not exist
    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
    init_db.check_column_exists = lambda table, col: False
    dummy_session = DummySession()
    init_db.db = types.SimpleNamespace(session=dummy_session)

    # Act
    result = init_db.add_project_user_id()

    # Assert
    assert result is True
    assert any("ALTER TABLE projects ADD COLUMN user_id VARCHAR(36)" in s for s in dummy_session.executed)
    assert dummy_session.committed is True


def test_add_organization_id_to_users_non_sqlite(capfd):
    # Arrange: non-SQLite path and column does not exist
    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user@host/db'
    init_db.check_column_exists = lambda table, col: False
    dummy_session = DummySession()
    init_db.db = types.SimpleNamespace(session=dummy_session)

    # Act
    result = init_db.add_organization_id_to_users()

    # Assert
    assert result is True
    # First statement: add column
    # Second statement: add foreign key constraint
    assert any("ALTER TABLE users ADD COLUMN organization_id VARCHAR(36)" in s for s in dummy_session.executed)
    assert any("ALTER TABLE users ADD CONSTRAINT fk_users_organization_id FOREIGN KEY" in s for s in dummy_session.executed)


def test_create_default_users_admin_already_exists(capfd):
    # Arrange: simulate existing admin
    class AdminRecord:
        id = 'existing-id'

    class QueryStub:
        def __init__(self, result):
            self._result = result
        def filter_by(self, **kwargs):
            return self
        def first(self):
            return self._result

    class UserStub:
        query = QueryStub(AdminRecord())

        def __init__(self, **kwargs):
            pass

        def set_password(self, password):
            pass

    init_db.User = UserStub
    init_db.update_existing_users_ai_preference = lambda: None
    admin_id = init_db.create_default_users()
    assert admin_id == 'existing-id'


def test_create_default_users_creates_users(capfd):
    # Arrange: no admin exists, create two users
    created_users = []

    class MockUser:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.password = None
            created_users.append(self)

        def set_password(self, pw):
            self.password = f"hashed-{pw}"

    class MockQueryAll:
        def filter_by(self, **kwargs):
            return self
        def first(self):
            return None

    class MockUserContainer:
        query = MockQueryAll()

    init_db.User = MockUserContainer  # so that .query.filter_by(...).first() returns None

    # Use deterministic UUIDs for admin/miriam
    ids = iter(['admin-uuid', 'miriam-uuid'])
    fake_uuid4 = lambda: next(ids)
    init_db.uuid.uuid4 = fake_uuid4  # patch inside module's uuid

    # Provide our MockUser class instantiation behavior
    MockUserContainer.__init__ = lambda self, **kwargs: None

    # Replace database session
    class MockSession:
        def __init__(self):
            self.added = []
            self.committed = False
        def add(self, obj):
            self.added.append(obj)
        def commit(self):
            self.committed = True
        def rollback(self):
            pass
    init_db.db = types.SimpleNamespace(session=MockSession())

    # Patch User to our MockUser class so that created users are tracked
    init_db.User = MockUser  # But create_default_users uses User(...) -> MockUser

    # To ensure that User(...) works for both admin and Miriam, we adjust the logic:
    # We'll simulate that create_default_users uses our MockUser; we already set User to MockUser.

    # Also ensure admin check returns None by adjusting the query used in create_default_users
    class QueryEmpty:
        @staticmethod
        def filter_by(**kwargs):
            return QueryEmpty
        @staticmethod
        def first():
            return None

    # Re-assign ready for the admin check
    init_db.User.query = QueryEmpty  # type: ignore

    # Create the test
    admin_id = init_db.create_default_users()

    # Assert admin_id equals first UUID
    assert admin_id == 'admin-uuid'

    # Assert two users were created
    assert len(init_db.db.session.added) == 2 if hasattr(init_db.db, 'session') else len(created_users)
    # Check usernames and AI model preference defaults
    usernames = [getattr(u, 'username', None) for u in init_db.db.session.added]
    assert 'admin' in usernames or 'miriam' in usernames
    # The admin/miriam are given ai_model_preference 'gpt-5' as per code
    for u in getattr(init_db.db.session, 'added', []):
        if hasattr(u, 'ai_model_preference'):
            assert u.ai_model_preference == 'gpt-5'


def test_update_existing_users_ai_preference_updates(capfd):
    # Arrange: prepare a user lacking AI preference
    class UserObj:
        def __init__(self, username, email, ai_model_preference=None):
            self.username = username
            self.email = email
            self.ai_model_preference = ai_model_preference

    missing = [UserObj('alice', 'alice@example.com', None)]
    class _Query:
        def filter_by(self, **kwargs):
            return self
        def all(self):
            return missing

    class UserStub:
        ai_model_preference = None
        query = _Query()

    init_db.User = UserStub

    # Mock migrate function (no-op)
    init_db.migrate_ai_model_preference_column = lambda: None

    # Mock db session
    class MockSession:
        def __init__(self):
            self.committed = False
        def commit(self):
            self.committed = True

    init_db.db = types.SimpleNamespace(session=MockSession())

    # Act
    init_db.update_existing_users_ai_preference()

    # Assert
    assert missing[0].ai_model_preference == 'gpt-5'
    assert init_db.db.session.committed is True


def test_update_existing_users_ai_preference_no_updates(capfd):
    class UserObj:
        def __init__(self, username, email, ai_model_preference=None):
            self.username = username
            self.email = email
            self.ai_model_preference = ai_model_preference

    no_missing = []  # No users without preference
    class _Query:
        def filter_by(self, **kwargs):
            return self
        def all(self):
            return no_missing

    class UserStub:
        ai_model_preference = None
        query = _Query()

    init_db.User = UserStub

    init_db.migrate_ai_model_preference_column = lambda: None

    class MockSession:
        def __init__(self):
            self.committed = False
        def commit(self):
            self.committed = True

    init_db.db = types.SimpleNamespace(session=MockSession())

    init_db.update_existing_users_ai_preference()

    # Since there were no updates, commit should not have been called
    assert init_db.db.session.committed is False