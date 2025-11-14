import sys
import types
import importlib
from typing import Any
import pytest

# Helper to create a fresh mock "database" module and load the init_db module
def create_module_with_fake_db(monkeypatch) -> Any:
    fake_db_module = types.ModuleType("database")

    class DummySession:
        def __init__(self):
            self.executed = []
            self.committed = False
            self.rolledback = False
            self.raise_on_execute = False

        def execute(self, sql, *args, **kwargs):
            if self.raise_on_execute:
                raise Exception("execute error")
            # store a readable representation
            self.executed.append(str(sql))
            return None

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolledback = True

    class DummyDB:
        def __init__(self):
            self.session = DummySession()
            self.engine = object()

    fake_db_module.db = DummyDB()
    fake_db_module.init_db = lambda app=None: None  # no-op for tests

    # Export placeholder classes to satisfy imports in init_db.py
    class Placeholder:  # generic placeholder class
        pass

    class_names = [
        "User", "Organization", "OrganizationMember", "Project", "TestRun", "TestPhase",
        "TestPlan", "TestPackage", "TestCaseExecution", "DocumentAnalysis", "UserRole",
        "UserPreferences", "BDDFeature", "BDDScenario", "BDDStep", "TestCase", "TestCaseStep",
        "TestCaseData", "TestCaseDataInput", "TestRunResult", "SeleniumTest", "UnitTest",
        "GeneratedCode", "UploadedCodeFile", "Integration", "JiraSyncItem", "CrawlMeta",
        "CrawlPage", "TestPlanTestRun", "TestPackageTestRun", "VirtualTestExecution",
        "GeneratedBDDScenario", "GeneratedManualTest", "GeneratedAutomationTest",
        "TestExecutionComparison", "SDDReviews", "SDDEnhancements", "ProjectUnitTests",
        "Workflow", "WorkflowExecution", "WorkflowNodeExecution",
        "TestPipeline", "PipelineExecution", "PipelineStageExecution", "PipelineStepExecution"
    ]

    for name in class_names:
        setattr(fake_db_module, name, type(name, (), {}))

    sys.modules["database"] = fake_db_module

    # Fresh import of init_db
    if "init_db" in sys.modules:
        del sys.modules["init_db"]

    mod = importlib.import_module("init_db")
    # Avoid depending on SQLAlchemy's text wrapper in tests
    monkeypatch.setattr(mod, "text", lambda s: s, raising=False)
    return mod, fake_db_module

# Fixture to provide a fresh module environment for each test
@pytest.fixture
def fresh_init_db_module(monkeypatch):
    mod, _db = create_module_with_fake_db(monkeypatch)
    return mod

# Helper to test reset state between tests (ensures independence)
def reset_session(fake_db_module):
    fake_db_module.db = type("DB", (), {
        "session": type("Session", (), {
            "executed": [],
            "committed": False,
            "rolledback": False,
            "raise_on_execute": False,
            "execute": lambda self, sql, *a, **k: (_ for _ in ()).__next__(),  # no-op generator to avoid errors
            "commit": lambda self: setattr(self, "committed", True),
            "rollback": lambda self: setattr(self, "rolledback", True),
        })(),
        "engine": object(),
    })()

# Tests

def test_remove_username_constraint_success(monkeypatch, fresh_init_db_module, capsys):
    mod = fresh_init_db_module
    # Ensure the dummy session exists and is clean
    mod.db.session.executed = []
    mod.db.session.rolledback = False
    mod.db.session.committed = False

    mod.remove_username_constraint()

    captured = capsys.readouterr()
    assert "✅ Username constraint removed successfully!" in captured.out
    assert mod.db.session.committed is True
    assert mod.db.session.rolledback is False
    # Ensure an ALTER statement was issued
    assert any("ALTER TABLE users DROP CONSTRAINT" in s for s in mod.db.session.executed)

def test_remove_username_constraint_failure(monkeypatch, fresh_init_db_module, capsys):
    mod = fresh_init_db_module
    # Make the session raise on execute to simulate failure
    mod.db.session.raise_on_execute = True

    mod.remove_username_constraint()

    captured = capsys.readouterr()
    assert "❌ Error removing constraint" in captured.out
    # Ensure rollback was triggered
    assert mod.db.session.rolledback is True

def test_check_column_exists_true(monkeypatch, fresh_init_db_module):
    mod = fresh_init_db_module

    class FakeInspector:
        def get_columns(self, table_name):
            return [{"name": "id"}, {"name": "target_column"}]

    monkeypatch.setattr(mod, "inspect", lambda engine=None: FakeInspector(), raising=False)

    assert mod.check_column_exists("any_table", "target_column") is True

def test_check_column_exists_false(monkeypatch, fresh_init_db_module):
    mod = fresh_init_db_module

    class FakeInspector:
        def get_columns(self, table_name):
            return [{"name": "id"}]

    monkeypatch.setattr(mod, "inspect", lambda engine=None: FakeInspector(), raising=False)

    assert mod.check_column_exists("any_table", "missing_column") is False

def test_add_project_user_id_when_column_exists(monkeypatch, fresh_init_db_module, capsys):
    mod = fresh_init_db_module

    # Simulate that the column already exists
    monkeypatch.setattr(mod, "check_column_exists", lambda table, col: True, raising=False)

    result = mod.add_project_user_id()

    assert result is True
    # Should not execute any ALTER statements
    assert mod.db.session.executed == []
    captured = capsys.readouterr()
    assert "user_id column already exists" in captured.out

def test_add_project_user_id_success_sqlite(monkeypatch, fresh_init_db_module):
    mod = fresh_init_db_module

    # Force sqlite-like DB URL
    mod.app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///test.db"

    monkeypatch.setattr(mod, "check_column_exists", lambda table, col: False, raising=False)

    mod.db.session.executed = []
    result = mod.add_project_user_id()

    assert result is True
    # Expect one ALTER TABLE statement
    assert len(mod.db.session.executed) == 1
    assert "ALTER TABLE projects ADD COLUMN user_id VARCHAR(36)" in mod.db.session.executed[0]

def test_add_project_user_id_failure(monkeypatch, fresh_init_db_module):
    mod = fresh_init_db_module

    mod.app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///test.db"
    monkeypatch.setattr(mod, "check_column_exists", lambda table, col: False, raising=False)

    mod.db.session.raise_on_execute = True

    result = mod.add_project_user_id()

    assert result is False
    assert mod.db.session.rolledback is True

def test_add_organization_id_to_users_success(monkeypatch, fresh_init_db_module, capsys):
    mod = fresh_init_db_module

    # Simulate column missing
    monkeypatch.setattr(mod, "check_column_exists", lambda table, col: False, raising=False)

    # Non-SQLite path
    mod.app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql://user:pass@localhost/db"

    mod.db.session.executed = []
    result = mod.add_organization_id_to_users()

    assert result is True
    # Should have added column and then FK constraint
    assert len(mod.db.session.executed) >= 2
    assert "ALTER TABLE users ADD COLUMN organization_id VARCHAR(36)" in mod.db.session.executed[0]
    # The second statement should be a foreign key constraint addition (string check)
    assert any("FOREIGN KEY" in s for s in mod.db.session.executed[1:])

def test_add_organization_id_to_users_failure(monkeypatch, fresh_init_db_module):
    mod = fresh_init_db_module

    # Simulate immediate failure on first alter
    mod.db.session.raise_on_execute = True
    monkeypatch.setattr(mod, "check_column_exists", lambda table, col: False, raising=False)
    mod.app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql://user:pass@localhost/db"

    result = mod.add_organization_id_to_users()

    assert result is False
    assert mod.db.session.rolledback is True