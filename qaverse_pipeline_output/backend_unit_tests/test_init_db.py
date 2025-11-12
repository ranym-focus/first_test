import importlib
import sys
import types
from uuid import UUID

import pytest


# Helper to load init_db with a fake database module to isolate tests
@pytest.fixture
def load_init_db_with_fake_db(monkeypatch):
    # Create a fake 'database' module with minimal interfaces
    fake_db_module = types.ModuleType("database")

    # In-memory storages for test verification
    fake_db_module.DUMMY_CREATED_USERS = []
    fake_db_module.DUMMY_EXECUTED_SQL = []

    class FakeSession:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0

        def execute(self, sql, *args, **kwargs):
            # Record the executed SQL for inspection
            fake_db_module.DUMMY_EXECUTED_SQL.append(str(sql))

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

    class FakeDB:
        def __init__(self):
            self.session = FakeSession()
            self.engine = object()

    fake_db = FakeDB()
    fake_db_module.db = fake_db

    # Fake User class that the init_db module will import
    class FakeUser:
        ai_model_preference = None
        query = None  # Will be replaced per-test as needed

        def __init__(self, **kwargs):
            # Persist provided fields onto the instance
            for k, v in kwargs.items():
                setattr(self, k, v)
            self.password = None
            # If id not provided, generate one to mimic real behavior
            self.id = kwargs.get("id", "generated-id-" + str(len(fake_db_module.DUMMY_CREATED_USERS)))
            fake_db_module.DUMMY_CREATED_USERS.append(self)

        def set_password(self, raw):
            self.password = raw

    fake_db_module.User = FakeUser

    # Placeholders for other models required by import
    for name in [
        "Organization",
        "OrganizationMember",
        "Project",
        "TestRun",
        "TestPhase",
        "TestPlan",
        "TestPackage",
        "TestCaseExecution",
        "DocumentAnalysis",
        "UserRole",
        "UserPreferences",
        "BDDFeature",
        "BDDScenario",
        "BDDStep",
        "TestCase",
        "TestCaseStep",
        "TestCaseData",
        "TestCaseDataInput",
        "TestRunResult",
        "SeleniumTest",
        "UnitTest",
        "GeneratedCode",
        "UploadedCodeFile",
        "Integration",
        "JiraSyncItem",
        "CrawlMeta",
        "CrawlPage",
        "TestPlanTestRun",
        "TestPackageTestRun",
        "VirtualTestExecution",
        "GeneratedBDDScenario",
        "GeneratedManualTest",
        "GeneratedAutomationTest",
        "TestExecutionComparison",
        "SDDReviews",
        "SDDEnhancements",
        "ProjectUnitTests",
        "Workflow",
        "WorkflowExecution",
        "WorkflowNodeExecution",
        "TestPipeline",
        "PipelineExecution",
        "PipelineStageExecution",
        "PipelineStepExecution",
    ]:
        setattr(fake_db_module, name, type(name, (), {}))

    # Stub init_db function to avoid real DB initialization side-effects
    fake_db_module.init_db = lambda app=None: None

    # Inject the fake module into sys.modules before importing init_db
    sys.modules["database"] = fake_db_module

    # Import the module under test
    init_db = importlib.import_module("init_db")

    # Expose the fake db and module for tests
    yield init_db, fake_db_module

    # Cleanup after test
    if "init_db" in sys.modules:
        del sys.modules["init_db"]
    if "database" in sys.modules:
        del sys.modules["database"]


def test_remove_username_constraint_success(load_init_db_with_fake_db, capsys, monkeypatch):
    init_db, fake_db_module = load_init_db_with_fake_db
    # Call with a functioning fake DB
    init_db.remove_username_constraint()
    captured = capsys.readouterr().out
    assert "Username constraint removed successfully" in captured or "Username constraint removed" in captured
    # Ensure a commit happened
    assert fake_db_module.db.session.commits == 1
    # Ensure an ALTER statement was attempted (captured in executed SQL)
    assert len(fake_db_module.DUMMY_EXECUTED_SQL) >= 1


def test_remove_username_constraint_failure(load_init_db_with_fake_db, capsys, monkeypatch):
    init_db, fake_db_module = load_init_db_with_fake_db

    # Inject a failing execute to trigger rollback
    def failing_execute(sql, *args, **kwargs):
        raise Exception("boom")

    fake_db_module.db.session.execute = failing_execute

    init_db.remove_username_constraint()
    captured = capsys.readouterr().out
    assert "Error removing constraint" in captured or "Error removing constraint" in captured
    # Ensure a rollback happened
    assert fake_db_module.db.session.rollbacks >= 1


def test_check_column_exists(monkeypatch, load_init_db_with_fake_db):
    init_db, _ = load_init_db_with_fake_db

    class DummyInspector:
        def __init__(self, columns):
            self._columns = columns

        def get_columns(self, table_name):
            return self._columns.get(table_name, [])

    # Patch init_db.inspect to return our DummyInspector
    dummy_columns = {
        'projects': [{'name': 'id'}, {'name': 'user_id'}],
        'users': [{'name': 'id'}],
    }
    monkeypatch.setattr(init_db, "inspect", lambda engine: DummyInspector(dummy_columns))

    assert init_db.check_column_exists('projects', 'user_id') is True
    assert init_db.check_column_exists('projects', 'nonexistent') is False


def test_add_project_user_id_exists(load_init_db_with_fake_db, monkeypatch):
    init_db, fake_db_module = load_init_db_with_fake_db
    # Simulate the column already exists
    monkeypatch.setattr(init_db, "check_column_exists", lambda table, col: True)

    # Set a non-sqlite DB URI to exercise path where no errors occur
    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:pass@localhost/db'

    # Call
    assert init_db.add_project_user_id() is True

    # Ensure no new SQL executed
    assert len(fake_db_module.DUMMY_EXECUTED_SQL) == 0


def test_add_project_user_id_not_exists(load_init_db_with_fake_db, monkeypatch):
    init_db, fake_db_module = load_init_db_with_fake_db
    # Simulate column not exists
    monkeypatch.setattr(init_db, "check_column_exists", lambda table, col: False)

    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:pass@localhost/db'

    assert init_db.add_project_user_id() is True
    # Ensure an alter table statement was executed
    assert len(fake_db_module.DUMMY_EXECUTED_SQL) >= 1
    # Ensure a commit happened
    assert fake_db_module.db.session.commits >= 1


def test_add_organization_id_to_users_exists(load_init_db_with_fake_db, monkeypatch):
    init_db, fake_db_module = load_init_db_with_fake_db
    monkeypatch.setattr(init_db, "check_column_exists", lambda table, col: True)

    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:pass@localhost/db'
    assert init_db.add_organization_id_to_users() is True
    # No new SQL expected
    assert len(fake_db_module.DUMMY_EXECUTED_SQL) == 0


def test_add_organization_id_to_users_not_exists(load_init_db_with_fake_db, monkeypatch):
    init_db, fake_db_module = load_init_db_with_fake_db
    monkeypatch.setattr(init_db, "check_column_exists", lambda table, col: False)

    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:pass@localhost/db'
    # Use a non-sqlite URI to test normal path
    assert init_db.add_organization_id_to_users() is True
    assert len(fake_db_module.DUMMY_EXECUTED_SQL) >= 1


def test_add_organization_id_to_users_fk_constraint_error(load_init_db_with_fake_db, monkeypatch):
    init_db, fake_db_module = load_init_db_with_fake_db
    monkeypatch.setattr(init_db, "check_column_exists", lambda table, col: False)

    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:pass@localhost/db'

    # Make execute raise when FK constraint is attempted
    def custom_execute(sql, *args, **kwargs):
        s = str(sql)
        if "fk_users_organization_id" in s or "FOREIGN KEY" in s:
            raise Exception("FK error")
        fake_db_module.DUMMY_EXECUTED_SQL.append(s)

    fake_db_module.db.session.execute = custom_execute

    # Should handle inner exception and still return True
    assert init_db.add_organization_id_to_users() is True


def test_create_default_users_admin_exists(load_init_db_with_fake_db, monkeypatch):
    init_db, fake_db_module = load_init_db_with_fake_db

    # Admin exists scenario
    class FoundAdmin:
        id = 'existing-admin-id'

    # FakeUser.query.filter_by(...).first() should return FoundAdmin
    class DummyQueryByFilterBy:
        def __init__(self, first_result):
            self._first = first_result
        def filter_by(self, **kwargs):
            return self
        def first(self):
            return self._first

    fake_db_module.User.query = DummyQueryByFilterBy(FoundAdmin())

    # Stub out the AI model preference update to avoid side-effects
    monkeypatch.setattr(init_db, "update_existing_users_ai_preference", lambda: None)

    admin_id = init_db.create_default_users()
    assert admin_id == FoundAdmin.id
    # Since admin exists, no new users should be created
    assert len(fake_db_module.DUMMY_CREATED_USERS) == 0


def test_create_default_users_admin_not_exists(load_init_db_with_fake_db, monkeypatch):
    init_db, fake_db_module = load_init_db_with_fake_db

    # Admin does not exist scenario
    class DummyQueryByFilterBy:
        def __init__(self, first_result=None):
            self._first = first_result
        def filter_by(self, **kwargs):
            return self
        def first(self):
            return self._first

        def __bool__(self):
            return self._first is not None

    fake_db_module.User.query = DummyQueryByFilterBy(None)

    # Stub update function
    monkeypatch.setattr(init_db, "update_existing_users_ai_preference", lambda: None)

    created_admin_id = init_db.create_default_users()

    # Expect two users created (admin and Miriam)
    assert len(fake_db_module.DUMMY_CREATED_USERS) >= 2
    # The first created user should have password set to 'admin'
    created_admins = [u for u in fake_db_module.DUMMY_CREATED_USERS if getattr(u, "username", "") == "admin"]
    assert len(created_admins) == 1
    assert created_admins[0].password == "admin"

    # The function should return a UUID-like string
    try:
        UUID(created_admin_id, version=4)
    except Exception:
        pytest.fail("Returned admin_id is not a valid UUID")