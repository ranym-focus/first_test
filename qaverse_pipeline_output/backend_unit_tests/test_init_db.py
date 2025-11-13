import importlib
import sys
import types
from types import SimpleNamespace

import pytest


# Helper to load init_db with a fake database module to avoid real DB operations
@pytest.fixture
def init_db_with_fake_db(monkeypatch):
    # Create a fake 'database' module with minimal stubs
    fake_db_mod = types.ModuleType("database")

    # Minimal dummy 'init_db' function to be called by init_db.py
    fake_db_mod.init_db = lambda app: None

    # Dummy db with a session object
    class DummySession:
        def __init__(self):
            self.executed = []
            self.committed = False
            self.rolled_back = False

        def execute(self, stmt):
            # Record the SQL text representation if possible
            try:
                self.executed.append(str(stmt))
            except Exception:
                self.executed.append(repr(stmt))

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

        def add(self, obj):
            # no-op for tests
            pass

    fake_db = SimpleNamespace(session=DummySession(), engine=None)

    fake_db_mod.db = fake_db

    # Create placeholders for all model names imported in init_db.py
    model_names = [
        "User", "Organization", "OrganizationMember", "Project", "TestRun", "TestPhase",
        "TestPlan", "TestPackage", "TestCaseExecution", "DocumentAnalysis", "UserRole",
        "UserPreferences", "BDDFeature", "BDDScenario", "BDDStep", "TestCase", "TestCaseStep",
        "TestCaseData", "TestCaseDataInput", "TestRunResult", "SeleniumTest", "UnitTest",
        "GeneratedCode", "UploadedCodeFile", "Integration", "JiraSyncItem", "CrawlMeta",
        "CrawlPage", "TestPlanTestRun", "TestPackageTestRun", "VirtualTestExecution",
        "GeneratedBDDScenario", "GeneratedManualTest", "GeneratedAutomationTest",
        "TestExecutionComparison", "SDDReviews", "SDDEnhancements", "ProjectUnitTests",
        "Workflow", "WorkflowExecution", "WorkflowNodeExecution", "TestPipeline",
        "PipelineExecution", "PipelineStageExecution", "PipelineStepExecution",
        # For safety, include any other names that might be imported
        "init_db"
    ]

    for name in model_names:
        setattr(fake_db_mod, name, object())  # simple placeholder

    # Inject fake module into sys.modules before importing init_db
    sys.modules["database"] = fake_db_mod

    # Import/reload init_db with the fake database
    if "init_db" in sys.modules:
        del sys.modules["init_db"]
    init_db_module = importlib.import_module("init_db")
    importlib.reload(init_db_module)

    # Return the module for tests to use
    return init_db_module


def test_remove_username_constraint_success(init_db_with_fake_db, capsys, monkeypatch):
    init_db = init_db_with_fake_db
    # Patch db.session.execute to record calls and ensure commit happens
    calls = []

    class DummyExecSession:
        def __init__(self, parent):
            self.parent = parent

        def execute(self, stmt):
            calls.append(str(stmt))

        def commit(self):
            calls.append("COMMIT")

        def rollback(self):
            calls.append("ROLLBACK")

    init_db.db = SimpleNamespace(session=DummyExecSession(None), engine=None)

    init_db.remove_username_constraint()

    assert any("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_username_key;" in c for c in calls) or any(
        "DROP CONSTRAINT" in c for c in calls
    )
    assert "COMMIT" in calls
    captured = capsys.readouterr()
    assert "✅ Username constraint removed successfully!" in captured.out


def test_remove_username_constraint_failure(init_db_with_fake_db, capsys, monkeypatch):
    init_db = init_db_with_fake_db

    class FailingExecSession:
        def __init__(self, parent):
            pass

        def execute(self, stmt):
            raise Exception("boom")

        def commit(self):
            pass

        def rollback(self):
            pass

    init_db.db = SimpleNamespace(session=FailingExecSession(None), engine=None)

    init_db.remove_username_constraint()

    captured = capsys.readouterr()
    assert "❌ Error removing constraint" in captured.out


def test_check_column_exists_true_false(init_db_with_fake_db):
    init_db = init_db_with_fake_db

    class FakeInspector:
        def __init__(self, columns):
            self._columns = columns

        def get_columns(self, table_name):
            return self._columns

    # Patch inspect to return our fake inspector
    monkey_inspect = lambda engine: FakeInspector([{"name": "id"}, {"name": "user_id"}])
    init_db.inspect = monkey_inspect
    # Provide a dummy db.engine since it's passed to inspect
    init_db.db = SimpleNamespace(engine="dummy_engine")

    assert init_db.check_column_exists("projects", "user_id") is True

    # Now test for a missing column
    monkey_inspect_missing = lambda engine: FakeInspector([{"name": "id"}])
    init_db.inspect = monkey_inspect_missing

    assert init_db.check_column_exists("projects", "user_id") is False


def test_add_project_user_id_already_exists(init_db_with_fake_db, capsys):
    init_db = init_db_with_fake_db

    # Patch the check_column_exists to simulate presence
    init_db.check_column_exists = lambda table, column: True

    result = init_db.add_project_user_id()

    assert result is True
    captured = capsys.readouterr()
    assert "✅ user_id column already exists in projects table." in captured.out


def test_add_project_user_id_sqlite(init_db_with_fake_db):
    init_db = init_db_with_fake_db

    # Simulate sqlite
    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
    init_db.check_column_exists = lambda table, column: False

    exec_calls = []

    class DummyExecSession:
        def __init__(self, parent):
            pass

        def execute(self, stmt):
            exec_calls.append(str(stmt))

        def commit(self):
            exec_calls.append("COMMIT")

        def rollback(self):
            exec_calls.append("ROLLBACK")

    init_db.db = SimpleNamespace(session=DummyExecSession(None), engine=None)

    result = init_db.add_project_user_id()
    assert result is True
    assert any("ALTER TABLE projects ADD COLUMN user_id VARCHAR(36)" in s for s in exec_calls)


def test_add_organization_id_to_users_already_exists(init_db_with_fake_db, capsys):
    init_db = init_db_with_fake_db
    init_db.check_column_exists = lambda table, column: True

    result = init_db.add_organization_id_to_users()

    assert result is True
    captured = capsys.readouterr()
    assert "✅ organization_id column already exists in users table." in captured.out


def test_add_organization_id_to_users_sqlite(init_db_with_fake_db):
    init_db = init_db_with_fake_db
    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
    init_db.check_column_exists = lambda table, column: False

    exec_calls = []

    class DummyExecSession:
        def __init__(self, parent):
            pass

        def execute(self, stmt):
            exec_calls.append(str(stmt))

        def commit(self):
            exec_calls.append("COMMIT")

        def rollback(self):
            exec_calls.append("ROLLBACK")

    init_db.db = SimpleNamespace(session=DummyExecSession(None), engine=None)

    result = init_db.add_organization_id_to_users()

    assert result is True
    assert any("ALTER TABLE users ADD COLUMN organization_id VARCHAR(36)" in s for s in exec_calls)


def test_update_existing_users_ai_preference_sets_defaults(init_db_with_fake_db, monkeypatch):
    init_db = init_db_with_fake_db

    # Stub migrate_ai_model_preference_column
    init_db.migrate_ai_model_preference_column = lambda: None

    # Create dummy users lacking ai_model_preference
    class DummyUserInstance:
        def __init__(self, username, email, ai_model_preference=None):
            self.username = username
            self.email = email
            self.ai_model_preference = ai_model_preference

    user1 = DummyUserInstance("u1", "u1@example.com", None)
    user2 = DummyUserInstance("u2", "u2@example.com", "")

    class DummyQuery:
        def __init__(self, results):
            self._results = results

        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return self._results

    class DummyUserModel:
        ai_model_preference = None
        query = DummyQuery([user1, user2])

    init_db.User = DummyUserModel

    # Capture commit
    class DummySession:
        def __init__(self):
            self.committed = False

        def commit(self):
            self.committed = True

        def add(self, obj):
            pass

    init_db.db = SimpleNamespace(session=DummySession(), engine=None)

    init_db.update_existing_users_ai_preference()

    assert user1.ai_model_preference == "gpt-5"
    assert user2.ai_model_preference == "gpt-5"
    assert init_db.db.session.committed is True