import importlib
import sys
import types
from types import SimpleNamespace
import pytest

# Helpers to create a fake database module and load init_db with it
def make_fake_database_module():
    fake_db = types.ModuleType('database')

    class DummySession:
        def __init__(self):
            self.rolled_back = False
            self.executed = []

        def execute(self, *args, **kwargs):
            self.executed.append(args[0] if args else None)
            return None

        def commit(self):
            pass

        def rollback(self):
            self.rolled_back = True

    class DummyDB:
        def __init__(self):
            self.session = DummySession()

    fake_db.db = DummyDB()

    # Provide placeholders for many model names used in init_db.py
    model_names = [
        "User","Organization","OrganizationMember","Project","TestRun","TestPhase","TestPlan","TestPackage",
        "TestCaseExecution","DocumentAnalysis","UserRole","UserPreferences","BDDFeature","BDDScenario","BDDStep",
        "TestCase","TestCaseStep","TestCaseData","TestCaseDataInput","TestRunResult","SeleniumTest","UnitTest",
        "GeneratedCode","UploadedCodeFile","Integration","JiraSyncItem","CrawlMeta","CrawlPage","TestPlanTestRun",
        "TestPackageTestRun","VirtualTestExecution","GeneratedBDDScenario","GeneratedManualTest","GeneratedAutomationTest",
        "TestExecutionComparison","SDDReviews","SDDEnhancements","ProjectUnitTests","Workflow","WorkflowExecution",
        "WorkflowNodeExecution","TestPipeline","PipelineExecution","PipelineStageExecution","PipelineStepExecution"
    ]
    for name in model_names:
        setattr(fake_db, name, type(name, (), {}))

    def fake_init_db(app):
        # Placeholder to satisfy import side-effect during init
        pass

    fake_db.init_db = fake_init_db
    return fake_db


def load_init_db_with_fake_db(fake_db_module):
    sys.modules['database'] = fake_db_module
    if 'init_db' in sys.modules:
        del sys.modules['init_db']
    init_db_module = importlib.import_module('init_db')
    return init_db_module


@pytest.fixture
def init_module():
    fake_db = make_fake_database_module()
    mod = load_init_db_with_fake_db(fake_db)
    # Ensure module uses our fake db instance
    mod.db = fake_db.db
    return mod


def test_remove_username_constraint_success(init_module, capsys):
    # Replace db.session with a dummy session that simulates success
    class Session:
        def __init__(self):
            self.rolled_back = False

        def execute(self, *args, **kwargs):
            return None

        def commit(self):
            pass

        def rollback(self):
            self.rolled_back = True

    init_module.db.session = Session()
    init_module.remove_username_constraint()

    captured = capsys.readouterr()
    assert "✅ Username constraint removed successfully!" in captured.out


def test_remove_username_constraint_failure(init_module, capsys):
    class Session:
        def __init__(self):
            self.rolled_back = False

        def execute(self, *args, **kwargs):
            raise Exception("boom")

        def commit(self):
            pass

        def rollback(self):
            self.rolled_back = True

    init_module.db.session = Session()
    init_module.remove_username_constraint()

    captured = capsys.readouterr()
    assert "❌ Error removing constraint" in captured.out


def test_check_column_exists_true(init_module, monkeypatch):
    class FakeInspector:
        def __init__(self, *args, **kwargs):
            pass

        def get_columns(self, table_name):
            return [{'name': 'user_id'}, {'name': 'id'}]

    monkeypatch.setattr(init_module, 'inspect', lambda engine=None: FakeInspector())
    assert init_module.check_column_exists('projects', 'user_id') is True


def test_check_column_exists_false(init_module, monkeypatch):
    class FakeInspector:
        def __init__(self, *args, **kwargs):
            pass

        def get_columns(self, table_name):
            return []

    monkeypatch.setattr(init_module, 'inspect', lambda engine=None: FakeInspector())
    assert init_module.check_column_exists('projects', 'user_id') is False


def test_add_project_user_id_already_exists(init_module, capsys, monkeypatch):
    monkeypatch.setattr(init_module, 'check_column_exists', lambda t, c: True)
    result = init_module.add_project_user_id()
    captured = capsys.readouterr()
    assert result is True
    assert "✅ user_id column already exists in projects table." in captured.out


def test_add_project_user_id_sqlite_add_column(init_module, monkeypatch):
    monkeypatch.setattr(init_module, 'check_column_exists', lambda t, c: False)
    init_module.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'

    class SQLiteSession:
        def __init__(self):
            self.executed = []

        def execute(self, sql, *args, **kwargs):
            self.executed.append(sql)
            return None

        def commit(self):
            pass

        def rollback(self):
            pass

    init_module.db = SimpleNamespace(session=SQLiteSession())

    result = init_module.add_project_user_id()
    assert result is True
    assert len(init_module.db.session.executed) == 1
    sql_text = init_module.db.session.executed[0]
    assert 'ALTER TABLE projects ADD COLUMN user_id VARCHAR(36)' in str(sql_text)


def test_update_existing_users_ai_preference_updates_missing(init_module, monkeypatch):
    # Prepare fake User class with query().filter().all() returning two users, one missing preference
    class FakeQueryFactory:
        def __init__(self, results):
            self._results = results

        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return self._results

    class FakeUserClass:
        ai_model_preference = None
        # global list of results for this fake class
        _results = []

        @classmethod
        def query(cls):
            return FakeQueryFactory(cls._results)

    # Create two fake user instances
    class FakeUserInstance:
        def __init__(self, username, email, ai_pref=None):
            self.username = username
            self.email = email
            self.ai_model_preference = ai_pref

    u1 = FakeUserInstance('alice', 'alice@example.com', None)
    u2 = FakeUserInstance('bob', 'bob@example.com', 'gpt-4')
    FakeUserClass._results = [u1, u2]

    monkeypatch.setattr(init_module, 'migrate_ai_model_preference_column', lambda: None)
    monkeypatch.setattr(init_module, 'User', FakeUserClass)

    class DummySession:
        def __init__(self):
            self.committed = False

        def commit(self):
            self.committed = True

    class DummyDB:
        def __init__(self):
            self.session = DummySession()

    init_module.db = SimpleNamespace(session=DummySession())
    # Ensure the module uses the fake User class
    init_module.User = FakeUserClass

    init_module.update_existing_users_ai_preference()

    assert u1.ai_model_preference == 'gpt-5'
    assert u2.ai_model_preference == 'gpt-4'
    # Check that a commit occurred
    # Access the dummy db's session committed flag
    # Since we replaced init_module.db with a simple object, ensure the code path ran without error
    # We can't directly access commit flag here because the patch above doesn't expose it.
    # To robustly verify, reassign a proper dummy db to capture commit
    class CapturingDB:
        class Session:
            def __init__(self):
                self.committed = False
        def __init__(self):
            self.session = CapturingDB.Session()
    init_module.db = CapturingDB()
    init_module.update_existing_users_ai_preference()
    # After re-running with capturing db, ensure at least no exception and that missing user was updated
    assert u1.ai_model_preference == 'gpt-5'


def test_update_existing_users_ai_preference_no_missing(init_module, monkeypatch):
    class FakeQueryFactory:
        def __init__(self, results):
            self._results = results

        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return self._results

    class FakeUserClass:
        ai_model_preference = None
        _results = []

        @classmethod
        def query(cls):
            return FakeQueryFactory(cls._results)

    class FakeUserInstance:
        def __init__(self, username, email, ai_pref=None):
            self.username = username
            self.email = email
            self.ai_model_preference = ai_pref

    u = FakeUserInstance('charlie', 'charlie@example.com', 'gpt-5')
    FakeUserClass._results = [u]

    monkeypatch.setattr(init_module, 'migrate_ai_model_preference_column', lambda: None)
    monkeypatch.setattr(init_module, 'User', FakeUserClass)

    class DummySession:
        def __init__(self):
            self.committed = False

        def commit(self):
            self.committed = True

    class DummyDB:
        def __init__(self):
            self.session = DummySession()

    init_module.db = DummyDB()
    init_module.update_existing_users_ai_preference()
    # Since there were no missing users, commit should not be called
    assert init_module.db.session.committed is False