import sys
import types
import importlib
import textwrap
from typing import Any, Optional

import pytest


# Helper: create a fake database module to satisfy imports in init_db.py
def make_fake_database_module(admin_first_result: Optional[Any] = None):
    fake_db_module = types.ModuleType("database")

    class FakeSession:
        def __init__(self):
            self.executed = []
            self.committed = False
            self.rolled_back = False
            self.added = []
            self.raise_on_execute = False

        def execute(self, query):
            self.executed.append(query)
            if self.raise_on_execute:
                raise Exception("fake execute error")

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

        def add(self, obj):
            self.added.append(obj)

    class FakeEngine:
        pass

    class FakeDB:
        def __init__(self):
            self.session = FakeSession()
            self.engine = FakeEngine()

    fake_db_module.db = FakeDB()

    class FakeUser:
        ai_model_preference = None
        query = None

        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.password = None

        def set_password(self, p):
            self.password = p

    class FakeQuery:
        def __init__(self, first_result=None, all_results=None):
            self._first = first_result
            self._all = all_results

        def filter_by(self, **kwargs):
            return self

        def first(self):
            return self._first

        def all(self):
            return self._all if self._all is not None else []

        def filter(self, *args, **kwargs):
            return self

    if admin_first_result is not None:
        FakeQueryInstance = FakeQuery(first_result=admin_first_result)
        FakeUser.query = FakeQueryInstance
    else:
        FakeUser.query = FakeQuery(first_result=None)

    # Expose placeholders for all imported models to satisfy imports
    placeholder_names = [
        "Organization", "OrganizationMember", "Project", "TestRun", "TestPhase", "TestPlan",
        "TestPackage", "TestCaseExecution", "DocumentAnalysis", "UserRole", "UserPreferences",
        "BDDFeature", "BDDScenario", "BDDStep", "TestCase", "TestCaseStep", "TestCaseData",
        "TestCaseDataInput", "TestRunResult", "SeleniumTest", "UnitTest", "GeneratedCode",
        "UploadedCodeFile", "Integration", "JiraSyncItem", "CrawlMeta", "CrawlPage",
        "TestPlanTestRun", "TestPackageTestRun", "VirtualTestExecution", "GeneratedBDDScenario",
        "GeneratedManualTest", "GeneratedAutomationTest", "TestExecutionComparison",
        "SDDReviews", "SDDEnhancements", "ProjectUnitTests",
        "Workflow", "WorkflowExecution", "WorkflowNodeExecution",
        "TestPipeline", "PipelineExecution", "PipelineStageExecution", "PipelineStepExecution",
    ]
    for name in placeholder_names:
        setattr(fake_db_module, name, type(name, (), {}))

    # Provide User symbol for import
    fake_db_module.User = FakeUser

    # No-op init_db function to satisfy import-time call
    def fake_init_db(app):
        pass

    fake_db_module.init_db = fake_init_db
    fake_db_module.inspect = lambda engine: None  # will be overridden in tests as needed
    fake_db_module.text = None  # not used in tests directly

    return fake_db_module, FakeUser, FakeQuery


# Fixture to load init_db with a fake database module
@pytest.fixture
def init_db_module(monkeypatch, capsys):
    fake_db_module, FakeUser, FakeQuery = make_fake_database_module()
    # Inject our fake database module before importing init_db
    sys.modules['database'] = fake_db_module
    # Ensure a fresh import each test
    if 'init_db' in sys.modules:
        del sys.modules['init_db']
    importlib.invalidate_caches()
    import init_db  # type: ignore
    # Return references for tests
    return init_db, fake_db_module, FakeUser, FakeQuery


def test_remove_username_constraint_success(init_db_module, capsys, monkeypatch):
    init_db, fake_db_module, FakeUser, FakeQuery = init_db_module
    # Ensure no exception on execute
    init_db.db = fake_db_module.db

    init_db.remove_username_constraint()
    captured = capsys.readouterr()
    assert "Username constraint removed successfully" in captured.out or "Username constraint removed successfully!" in captured.out


def test_remove_username_constraint_failure(init_db_module, capsys, monkeypatch):
    init_db, fake_db_module, FakeUser, FakeQuery = init_db_module
    # Force execute to raise
    def raise_execute(_):
        raise Exception("boom")
    init_db.db.session.execute = raise_execute

    init_db.remove_username_constraint()
    captured = capsys.readouterr()
    assert "Error removing constraint" in captured.out
    assert "boom" in captured.out or "boom" in captured.err if captured.err else True


def test_check_column_exists_true_false(init_db_module):
    init_db, fake_db_module, FakeUser, FakeQuery = init_db_module

    class FakeInspector:
        def __init__(self, columns):
            self._columns = columns

        def get_columns(self, table_name):
            return self._columns

    # Patch the module's inspect to return FakeInspector with desired columns
    init_db.inspect = lambda engine: FakeInspector([{'name': 'user_id'}])
    assert init_db.check_column_exists('projects', 'user_id') is True

    init_db.inspect = lambda engine: FakeInspector([{'name': 'id'}, {'name': 'name'}])
    assert init_db.check_column_exists('projects', 'user_id') is False


def test_add_project_user_id_already_exists(init_db_module, capsys, monkeypatch):
    init_db, fake_db_module, FakeUser, FakeQuery = init_db_module
    monkeypatch.setattr(init_db, 'check_column_exists', lambda table, col: True)

    result = init_db.add_project_user_id()
    captured = capsys.readouterr()
    assert result is True
    assert "user_id column already exists" in captured.out or "user_id column already exists" in captured.out


def test_add_project_user_id_sqlite_add(init_db_module, monkeypatch):
    init_db, fake_db_module, FakeUser, FakeQuery = init_db_module
    # Force not exists
    monkeypatch.setattr(init_db, 'check_column_exists', lambda table, col: False)
    # Force sqlite path
    monkeypatch.setattr(init_db.app.config, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///test.db', raising=False)
    executed_queries = []
    init_db.db.session.execute = lambda q: executed_queries.append(str(q))
    assert init_db.add_project_user_id() is True
    assert len(executed_queries) >= 1
    # Ensure an ALTER TABLE query was attempted
    assert "ALTER TABLE projects ADD COLUMN user_id" in executed_queries[0]


def test_add_organization_id_to_users_already_exists(init_db_module, capsys, monkeypatch):
    init_db, fake_db_module, FakeUser, FakeQuery = init_db_module
    monkeypatch.setattr(init_db, 'check_column_exists', lambda table, col: True)

    result = init_db.add_organization_id_to_users()
    captured = capsys.readouterr()
    assert result is True
    assert "organization_id column" in captured.out or "organization_id column" in captured.out


def test_add_organization_id_to_users_sqlite_add(init_db_module, monkeypatch):
    init_db, fake_db_module, FakeUser, FakeQuery = init_db_module
    monkeypatch.setattr(init_db, 'check_column_exists', lambda table, col: False)
    monkeypatch.setattr(init_db.app.config, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///test.db', raising=False)
    executed_queries = []
    init_db.db.session.execute = lambda q: executed_queries.append(str(q))
    assert init_db.add_organization_id_to_users() is True
    assert len(executed_queries) >= 1
    assert "ALTER TABLE users ADD COLUMN organization_id" in executed_queries[0]


def test_create_default_users_admin_exists(init_db_module, capsys, monkeypatch):
    init_db, fake_db_module, FakeUser, FakeQuery = init_db_module
    # Create existing admin user
    existing_admin = init_db.User(id='admin-existing', email='admin@qaverse.com')
    # Patch User.query to return existing admin
    class AdminQuery:
        def filter_by(self, **kwargs):
            return self

        def first(self):
            return existing_admin
    init_db.User.query = AdminQuery()

    admin_id = init_db.create_default_users()
    captured = capsys.readouterr()
    assert admin_id == existing_admin.id
    assert "Admin user already exists" in captured.out


def test_create_default_users_admin_missing(init_db_module, capsys, monkeypatch):
    init_db, fake_db_module, FakeUser, FakeQuery = init_db_module
    # Admin does not exist
    class EmptyAdminQuery:
        def filter_by(self, **kwargs):
            return self

        def first(self):
            return None
    init_db.User.query = EmptyAdminQuery()

    # Patch update_existing_users_ai_preference to avoid executing more complex logic
    monkeypatch.setattr(init_db, 'update_existing_users_ai_preference', lambda: None)

    admin_id = init_db.create_default_users()
    captured = capsys.readouterr()
    assert isinstance(admin_id, str) and len(admin_id) > 0
    assert "Default users created successfully." in captured.out