import sys
import types
import importlib
import pytest

# Create a fake 'database' module to satisfy init_db.py imports before actually importing it
database_module = types.ModuleType('database')

# Minimal dummy db with session for the functions
class DummySession:
    def __init__(self):
        self.executed = False
        self.committed = False
        self.rolled_back = False
        self.last_sql = None

    def execute(self, query, *args, **kwargs):
        self.executed = True
        self.last_sql = str(query)
        return None

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

class DummyDB:
    def __init__(self):
        self.session = DummySession()
        self.engine = object()

database_module.db = DummyDB()

# A no-op init_db function so import doesn't fail
database_module.init_db = lambda app=None: None

# Provide placeholder classes for all expected names to satisfy import
class _Placeholder: pass
names = [
    'User','Organization','OrganizationMember','Project','TestRun','TestPhase','TestPlan','TestPackage',
    'TestCaseExecution','DocumentAnalysis','UserRole','UserPreferences','BDDFeature','BDDScenario',
    'BDDStep','TestCase','TestCaseStep','TestCaseData','TestCaseDataInput','TestRunResult','SeleniumTest',
    'UnitTest','GeneratedCode','UploadedCodeFile','Integration','JiraSyncItem','CrawlMeta','CrawlPage',
    'TestPlanTestRun','TestPackageTestRun','VirtualTestExecution','GeneratedBDDScenario','GeneratedManualTest',
    'GeneratedAutomationTest','TestExecutionComparison','SDDReviews','SDDEnhancements','ProjectUnitTests',
    'Workflow','WorkflowExecution','WorkflowNodeExecution','TestPipeline','PipelineExecution',
    'PipelineStageExecution','PipelineStepExecution'
]
for name in names:
    setattr(database_module, name, _Placeholder)

sys.modules['database'] = database_module

# Now import the target module (this will use the fake database module)
init_db = importlib.import_module('init_db')


# Helper: reset fake users between tests where needed
class FakeExpression:
    def __init__(self, op, a, b=None):
        self.op = op
        self.a = a
        self.b = b

class FakeField:
    def __init__(self, name):
        self.name = name
    def __eq__(self, other):
        return FakeExpression('eq', self.name, other)
    def __or__(self, other):
        return FakeExpression('or', self.__eq__(None), other)

class FakeQuery:
    def __init__(self, model_class=None):
        self.model_class = model_class
        self._filters = {}
        self._predicate = None

    # support for filter_by(...)
    def filter_by(self, **kwargs):
        self._filters = kwargs
        return self

    # support for filter(...) with a predicate
    def filter(self, predicate):
        self._predicate = predicate
        return self

    def first(self):
        if not hasattr(FakeUser, "_instances"):
            return None
        for u in FakeUser._instances:
            ok = True
            for k, v in self._filters.items():
                if getattr(u, k) != v:
                    ok = False
                    break
            if ok:
                return u
        return None

    def all(self):
        if not hasattr(FakeUser, "_instances"):
            return []
        if self._predicate is None:
            return list(FakeUser._instances)
        # evaluate custom predicate against each user
        def _evaluate(user, expr):
            if isinstance(expr, FakeExpression):
                if expr.op == 'eq':
                    attr = expr.a
                    val = expr.b
                    return getattr(user, attr) == val
                if expr.op == 'or':
                    return _evaluate(user, expr.a) or _evaluate(user, expr.b)
            return False

        result = []
        for u in FakeUser._instances:
            if _evaluate(u, self._predicate):
                result.append(u)
        return result

class FakeUser:
    _instances = []
    ai_model_preference = FakeField('ai_model_preference')
    query = FakeQuery(None)

    def __init__(self, id, username=None, email=None, full_name=None, role=None, is_active=None,
                 email_verified=None, ai_model_preference=None, created_at=None, updated_at=None):
        self.id = id
        self.username = username
        self.email = email
        self.full_name = full_name
        self.role = role
        self.is_active = is_active
        self.email_verified = email_verified
        self.ai_model_preference = ai_model_preference
        self.created_at = created_at
        self.updated_at = updated_at
        self._password = None
        FakeUser._instances.append(self)

    def set_password(self, password):
        self._password = password

# Patchable attributes injected into tests
@pytest.fixture(autouse=True)
def clear_fake_users():
    # Reset fake user store before each test that uses it
    FakeUser._instances = []
    FakeQuery  # ensure class is defined
    # Rebind class attribute query
    FakeUser.query = FakeQuery(FakeUser)
    yield
    FakeUser._instances = []


# Test 1: remove_username_constraint success and error paths
def test_remove_username_constraint_success_and_error(capfd):
    # Success path
    class SimpleSessionSuccess(DummySession):
        pass
    init_db.db = types.SimpleNamespace(session=SimpleSessionSuccess(), engine=None)

    init_db.remove_username_constraint()
    out = capfd.readouterr().out
    assert "✅ Username constraint removed successfully!" in out

    # Error path
    class SimpleSessionFail(DummySession):
        def execute(self, *args, **kwargs):
            raise Exception("boom")
        def rollback(self):
            self.rolled_back = True
    init_db.db = types.SimpleNamespace(session=SimpleSessionFail(), engine=None)

    init_db.remove_username_constraint()
    out = capfd.readouterr().out
    assert "❌ Error removing constraint: boom" in out
    # rollback should be attempted
    assert getattr(init_db.db.session, "rolled_back", False) is True


# Test 2: check_column_exists using a fake inspector
def test_check_column_exists(monkeypatch):
    class FakeInspector:
        def __init__(self, cols_map):
            self._cols = cols_map
        def get_columns(self, table_name):
            return self._cols.get(table_name, [])

    cols_map = {
        'projects': [{'name': 'id'}, {'name': 'user_id'}],
        'users': [{'name': 'id'}]
    }

    # Patch init_db.inspect to return our fake inspector
    monkeypatch.setattr(init_db, 'inspect', lambda engine: FakeInspector(cols_map))

    init_db.db = types.SimpleNamespace(engine=None)

    assert init_db.check_column_exists('projects', 'user_id') is True
    assert init_db.check_column_exists('projects', 'nonexistent') is False
    assert init_db.check_column_exists('users', 'id') is True


# Test 3: add_project_user_id with existing and new column
def test_add_project_user_id(monkeypatch):
    # Case: already exists
    monkeypatch.setattr(init_db, 'check_column_exists', lambda table, col: True)
    init_db.app.config = {'SQLALCHEMY_DATABASE_URI': 'postgresql://user:pass@host/db'}
    init_db.db = types.SimpleNamespace(session=DummySession(), engine=None)

    assert init_db.add_project_user_id() is True

    # Case: does not exist, sqlite path
    monkeypatch.setattr(init_db, 'check_column_exists', lambda table, col: False)
    init_db.app.config = {'SQLALCHEMY_DATABASE_URI': 'sqlite:///test.db'}
    session = DummySession()
    # capture SQL executed
    init_db.db = types.SimpleNamespace(session=session, engine=None)

    assert init_db.add_project_user_id() is True
    assert session.last_sql is not None
    assert "ALTER TABLE projects ADD COLUMN user_id VARCHAR(36)" in session.last_sql


# Test 4: add_organization_id_to_users with sqlite path
def test_add_organization_id_to_users_sqlite(monkeypatch):
    monkeypatch.setattr(init_db, 'check_column_exists', lambda table, col: False)
    init_db.app.config = {'SQLALCHEMY_DATABASE_URI': 'sqlite:///test.db'}
    session = DummySession()
    init_db.db = types.SimpleNamespace(session=session, engine=None)

    assert init_db.add_organization_id_to_users() is True
    assert session.last_sql is not None
    assert "ALTER TABLE users ADD COLUMN organization_id VARCHAR(36)" in session.last_sql

    # Exists path
    monkeypatch.setattr(init_db, 'check_column_exists', lambda table, col: True)
    session2 = DummySession()
    init_db.db = types.SimpleNamespace(session=session2, engine=None)
    assert init_db.add_organization_id_to_users() is True
    assert session2.executed is False  # no SQL executed when exists


# Test 5: create_default_users when admin exists and when not
def test_create_default_users_admin_exists_and_not(monkeypatch):
    # Case admin exists
    existing_admin = FakeUser(id='admin-exists-id', username='admin', email='admin@qaverse.com',
                              full_name='Admin', role='admin', is_active=True, email_verified=True,
                              ai_model_preference='gpt-5')
    FakeUser._instances = [existing_admin]
    FakeUser.query = FakeQuery(FakeUser)
    monkeypatch.setattr(init_db, 'User', FakeUser)
    called = {'updated': False}
    monkeypatch.setattr(init_db, 'update_existing_users_ai_preference', lambda: called.update(updated=True))

    admin_id = init_db.create_default_users()
    assert admin_id == existing_admin.id

    # Case admin not exists
    FakeUser._instances = []
    FakeUser.query = FakeQuery(FakeUser)
    monkeypatch.setattr(init_db, 'User', FakeUser)

    # Patch to capture that update_existing_users_ai_preference is invoked
    flag = {'called': False}
    def fake_update():
        flag['called'] = True
    monkeypatch.setattr(init_db, 'update_existing_users_ai_preference', fake_update)

    admin_id = init_db.create_default_users()
    # There should be two new users created
    emails = [u.email for u in FakeUser._instances]
    assert 'admin@qaverse.com' in emails
    assert 'miriam.dahmoun@gmail.com' in emails
    # The returned admin_id should match the admin created above
    admin_user = next(u for u in FakeUser._instances if u.email == 'admin@qaverse.com')
    assert admin_id == admin_user.id
    assert flag['called'] is True


# Test 6: update_existing_users_ai_preference updates missing preferences
def test_update_existing_users_ai_preference_updates_missing(monkeypatch):
    # Prepare fake users
    FakeUser._instances = [
        FakeUser(id='u1', email='u1@example.com', ai_model_preference=None),
        FakeUser(id='u2', email='u2@example.com', ai_model_preference=''),
        FakeUser(id='u3', email='u3@example.com', ai_model_preference='existing')
    ]
    FakeUser.query = FakeQuery(FakeUser)

    # Patch to ensure migrate function is a no-op
    monkeypatch.setattr(init_db, 'migrate_ai_model_preference_column', lambda: None)

    # Use a fake db with commit tracking
    class CommitSession(DummySession):
        def __init__(self):
            super().__init__()
            self.committed = False
        def commit(self):
            self.committed = True

    init_db.db = types.SimpleNamespace(session=CommitSession(), engine=None)

    # Ensure update_existing_users_ai_preference uses our FakeUser
    monkeypatch.setattr(init_db, 'User', FakeUser)

    init_db.update_existing_users_ai_preference()

    # Verify two missing preferences updated to 'gpt-5'
    updated = [u for u in FakeUser._instances if u.ai_model_preference == 'gpt-5']
    assert len(updated) == 2
    assert any(u.id == 'u1' for u in updated)
    assert any(u.id == 'u2' for u in updated)

    # Ensure commit occurred
    assert init_db.db.session.committed is True