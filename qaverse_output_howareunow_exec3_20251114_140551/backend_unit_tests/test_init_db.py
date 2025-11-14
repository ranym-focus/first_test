import importlib
import sys
import types
from types import SimpleNamespace
import uuid
import pytest

# Helper to create a fake 'database' module that init_db.py will import
def make_fake_database_module():
    fake = types.SimpleNamespace()

    # init_db(app) function in the fake database module (no-op)
    def fake_init_db(app):
        pass

    fake.init_db = fake_init_db

    # Simple in-memory DB session with basic hooks
    class DummySession:
        def __init__(self):
            self.executed = []
            self.committed = False
            self.rolled_back = False
            self.added = []

        def execute(self, query, *args, **kwargs):
            self.executed.append(query)
            return None

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

        def add(self, obj):
            self.added.append(obj)

    class DummyDB:
        def __init__(self):
            self.session = DummySession()
            self.engine = object()

    fake.db = DummyDB()

    # Basic User placeholder that can be replaced in tests
    class DummyQuery:
        def __init__(self, first_result=None, all_results=None):
            self._first = first_result
            self._all = all_results if all_results is not None else []

        def filter_by(self, **kwargs):
            return self

        def first(self):
            return self._first

        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return self._all

    class DummyUser:
        query = DummyQuery()
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
            self.password = None

        def set_password(self, password):
            self.password = password

    fake.User = DummyUser

    # Create placeholders for the remaining models to satisfy imports
    placeholder_names = [
        'Organization','OrganizationMember','Project','TestRun','TestPhase','TestPlan',
        'TestPackage','TestCaseExecution','DocumentAnalysis','UserRole','UserPreferences',
        'BDDFeature','BDDScenario','BDDStep','TestCase','TestCaseStep','TestCaseData',
        'TestCaseDataInput','TestRunResult','SeleniumTest','UnitTest','GeneratedCode',
        'UploadedCodeFile','Integration','JiraSyncItem','CrawlMeta','CrawlPage',
        'TestPlanTestRun','TestPackageTestRun','VirtualTestExecution','GeneratedBDDScenario',
        'GeneratedManualTest','GeneratedAutomationTest','TestExecutionComparison','SDDReviews',
        'SDDEnhancements','ProjectUnitTests','Workflow','WorkflowExecution','WorkflowNodeExecution',
        'TestPipeline','PipelineExecution','PipelineStageExecution','PipelineStepExecution'
    ]
    for name in placeholder_names:
        setattr(fake, name, type(name, (), {}))

    return fake

# Lazy loader for init_db module using the fake database
def load_init_db_module(fake_db=None):
    # Inject fake database module before importing init_db
    if fake_db is None:
        fake_db = make_fake_database_module()
    sys.modules['database'] = fake_db

    if 'init_db' in sys.modules:
        del sys.modules['init_db']
    init_db = importlib.import_module('init_db')
    return init_db

@pytest.fixture(autouse=True)
def run_around_tests(monkeypatch):
    # Ensure each test starts with a clean module state
    yield
    # Cleanup after each test
    if 'init_db' in sys.modules:
        del sys.modules['init_db']

def test_remove_username_constraint_success(monkeypatch):
    fake_db = make_fake_database_module()
    init_db = load_init_db_module(fake_db)

    # Ensure commit is tracked
    committed = {'flag': False}
    def fake_commit():
        committed['flag'] = True
    init_db.db.session.commit = fake_commit
    init_db.db.session.execute = lambda *args, **kwargs: None

    # Capture stdout
    import sys
    from io import StringIO
    old_stdout, sys.stdout = sys.stdout, StringIO()

    init_db.remove_username_constraint()

    # Restore stdout
    output = sys.stdout.getvalue()
    sys.stdout = old_stdout

    assert committed['flag'] is True
    assert "Username constraint removed successfully" in output

def test_remove_username_constraint_failure(monkeypatch):
    fake_db = make_fake_database_module()
    init_db = load_init_db_module(fake_db)

    # Simulate failure in SQL execution
    committed = {'rolled_back': False}
    def fake_rollback():
        committed['rolled_back'] = True
    init_db.db.session.execute = lambda *args, **kwargs: (_ for _ in ()).throw(Exception("boom"))
    init_db.db.session.rollback = fake_rollback

    # Capture stdout
    import sys
    from io import StringIO
    old_stdout, sys.stdout = sys.stdout, StringIO()

    init_db.remove_username_constraint()

    output = sys.stdout.getvalue()
    sys.stdout = old_stdout

    assert committed['rolled_back'] is True
    assert "Error removing constraint" in output

def test_check_column_exists_true_false(monkeypatch):
    fake_db = make_fake_database_module()
    init_db = load_init_db_module(fake_db)

    class DummyInspector:
        def __init__(self, cols):
            self._cols = cols
        def get_columns(self, table_name):
            return [{'name': c} for c in self._cols]

    # Case: column exists
    init_db.inspect = lambda eng: DummyInspector(['user_id', 'other'])
    assert init_db.check_column_exists('projects', 'user_id') is True

    # Case: column does not exist
    init_db.inspect = lambda eng: DummyInspector(['col1', 'col2'])
    assert init_db.check_column_exists('projects', 'user_id') is False

def test_add_project_user_id_when_missing_sqlite(monkeypatch):
    fake_db = make_fake_database_module()
    init_db = load_init_db_module(fake_db)

    # Simulate missing column
    init_db.check_column_exists = lambda table, col: False
    # Simulate sqlite URI
    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'

    executed = {'count': 0, 'texts': []}
    def fake_execute(query, *args, **kwargs):
        executed['count'] += 1
        executed['texts'].append(str(query))
        return None
    init_db.db.session.execute = fake_execute
    init_db.db.session.commit = lambda: None

    result = init_db.add_project_user_id()

    assert result is True
    assert executed['count'] >= 1
    assert "ALTER TABLE projects ADD COLUMN user_id VARCHAR(36)" in executed['texts'][0]

def test_add_project_user_id_already_exists(monkeypatch):
    fake_db = make_fake_database_module()
    init_db = load_init_db_module(fake_db)

    init_db.check_column_exists = lambda table, col: True

    result = init_db.add_project_user_id()

    assert result is True  # Should indicate nothing to do
    # Ensure no SQLALTER executed
    # We can't easily introspect no-ops, but ensuring no exception is raised suffices

def test_create_default_users_admin_exists(monkeypatch):
    fake_db = make_fake_database_module()

    # Admin user already exists: User.query.filter_by(...).first() returns an object with id
    class AdminExisting:
        query = type('Q', (), {'filter_by': lambda self, **kwargs: self,
                               'first': lambda self: type('Admin', (), {'id': 'admin-id', 'email': 'admin@qaverse.com'})()})()

        def __init__(self, **kwargs):
            pass
        def set_password(self, password):
            self.password = password

    fake_db.User = AdminExisting

    init_db = load_init_db_module(fake_db)

    # Patch db.session.add to track potential adds and commit
    adds = []
    init_db.db.session.add = lambda obj: adds.append(obj)

    admin_id_returned = init_db.create_default_users()

    assert admin_id_returned == 'admin-id'
    # Since admin already exists, adds should be empty
    assert len(adds) == 0

def test_update_existing_users_ai_preference_updates(monkeypatch):
    fake_db = make_fake_database_module()
    init_db = load_init_db_module(fake_db)

    # Migrate function is a no-op for test
    init_db.migrate_ai_model_preference_column = lambda: None

    # Prepare two user objects that will be updated
    class UserObj:
        def __init__(self, username, email, ai_model_preference=None):
            self.username = username
            self.email = email
            self.ai_model_preference = ai_model_preference

    users_list = [UserObj('alice', 'alice@example.com', None),
                  UserObj('bob', 'bob@example.com', None)]

    class DummyQueryAll:
        def __init__(self, users):
            self._users = users
        def filter(self, *args, **kwargs):
            return self
        def all(self):
            return self._users

    class DummyUserClass:
        ai_model_preference = None
        query = DummyQueryAll(users_list)

        def __init__(self, **kwargs):
            pass

    init_db.User = DummyUserClass

    committed = {'flag': False}
    def fake_commit():
        committed['flag'] = True
    init_db.db.session.commit = fake_commit

    init_db.update_existing_users_ai_preference()

    # All users should now have ai_model_preference set to 'gpt-5'
    assert all(u.ai_model_preference == 'gpt-5' for u in users_list)
    assert committed['flag'] is True