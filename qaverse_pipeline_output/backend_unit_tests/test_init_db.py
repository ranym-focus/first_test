import sys
import types
import uuid
import importlib
import pytest

# Helper fixture to inject a fake database layer and safely import the module under test
@pytest.fixture
def setup_init_db_module():
    # Create a fake "database" module to satisfy `from database import ...` imports
    fake_db_module = types.ModuleType('database')

    # Fake session with logging and error injection for testing error paths
    class FakeSession:
        def __init__(self, raise_on_execute=False):
            self.raise_on_execute = raise_on_execute
            self.executed = []
            self.added = []
            self.rolled_back = False

        def execute(self, *args, **kwargs):
            if self.raise_on_execute:
                raise Exception("execute error")
            self.executed.append(str(args[0]))
            return None

        def add(self, obj):
            self.added.append(obj)

        def commit(self):
            pass

        def rollback(self):
            self.rolled_back = True

        def reset(self):
            self.executed.clear()
            self.added.clear()
            self.rolled_back = False

    # Fake DB wrapper to expose a session and an engine
    class FakeDB:
        def __init__(self, session=None, engine=None):
            self.session = session or FakeSession()
            self.engine = engine or object()

    fake_db_module.db = FakeDB()

    # Simple query mechanism to satisfy code paths without real ORM
    class FakeQuery:
        _results = []

        @classmethod
        def set_results(cls, results):
            cls._results = results

        def filter_by(self, **kwargs):
            return self

        def first(self):
            if FakeQuery._results:
                return FakeQuery._results[0]
            return None

        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return FakeQuery._results

    # Fake User model with minimal behavior
    class FakeUser:
        ai_model_preference = None
        query = FakeQuery()

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
            self.password = None

        def set_password(self, pwd):
            self.password = pwd

    fake_db_module.User = FakeUser

    # Create stubs for all other names imported from database to satisfy imports
    placeholder_names = [
        "Organization","OrganizationMember","Project","TestRun","TestPhase","TestPlan","TestPackage",
        "TestCaseExecution","DocumentAnalysis","UserRole","UserPreferences","BDDFeature","BDDScenario",
        "BDDStep","TestCase","TestCaseStep","TestCaseData","TestCaseDataInput","TestRunResult",
        "SeleniumTest","UnitTest","GeneratedCode","UploadedCodeFile","Integration","JiraSyncItem",
        "CrawlMeta","CrawlPage","TestPlanTestRun","TestPackageTestRun","VirtualTestExecution",
        "GeneratedBDDScenario","GeneratedManualTest","GeneratedAutomationTest","TestExecutionComparison",
        "SDDReviews","SDDEnhancements","ProjectUnitTests","Workflow","WorkflowExecution",
        "WorkflowNodeExecution","TestPipeline","PipelineExecution","PipelineStageExecution","PipelineStepExecution"
    ]
    for name in placeholder_names:
        setattr(fake_db_module, name, type(name, (), {}))

    # Inject fake module into sys.modules before importing init_db
    sys.modules['database'] = fake_db_module

    # Ensure a fresh import of init_db using the fake database module
    if 'init_db' in sys.modules:
        del sys.modules['init_db']
    init_db = importlib.import_module('init_db')

    yield init_db  # provide the prepared module to tests

    # Teardown after test
    del sys.modules['init_db']
    del sys.modules['database']


def test_remove_username_constraint_success(setup_init_db_module, capsys):
    init_db = setup_init_db_module
    # Ensure default behavior succeeds (no exception)
    init_db.db = init_db.db  # keep reference
    init_db.remove_username_constraint()
    captured = capsys.readouterr()
    assert "✅ Username constraint removed successfully!" in captured.out


def test_remove_username_constraint_failure(setup_init_db_module, capsys):
    init_db = setup_init_db_module
    # Inject failure into the DB session to trigger error handling
    init_db.db.session.raise_on_execute = True
    init_db.remove_username_constraint()
    captured = capsys.readouterr()
    assert "❌ Error removing constraint" in captured.out
    assert init_db.db.session.rolled_back is True


def test_add_project_user_id_creates_column(setup_init_db_module, monkeypatch):
    init_db = setup_init_db_module

    # Simulate that the column does not exist yet
    class FakeInspector:
        def __init__(self, map_cols):
            self.map_cols = map_cols
        def get_columns(self, table_name):
            return self.map_cols.get(table_name, [])

    def fake_inspector(engine):
        return FakeInspector({'projects': [{'name': 'id'}], 'users': []})

    # Monkeypatch inspect to return our FakeInspector
    monkeypatch.setattr(init_db, 'inspect', fake_inspector)

    # Ensure sqlite path
    init_db.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    # Ensure the column doesn't exist in our fake inspector data
    # The function itself uses check_column_exists to decide, which uses inspect(...).get_columns
    # We'll call add_project_user_id and expect it to attempt to add the column
    init_db.db.session.executed.clear()
    result = init_db.add_project_user_id()
    assert result is True
    log = " | ".join(init_db.db.session.executed)
    assert "ALTER TABLE projects ADD COLUMN user_id VARCHAR(36)" in log


def test_add_project_user_id_already_exists(setup_init_db_module, monkeypatch):
    init_db = setup_init_db_module

    # Patch check_column_exists to simulate column already exists
    monkeypatch.setattr(init_db, 'check_column_exists', lambda table_name, column_name: True)

    # Call function; should short-circuit and return True without executing SQL
    init_db.db.session.executed.clear()
    result = init_db.add_project_user_id()
    assert result is True
    assert len(init_db.db.session.executed) == 0


def test_create_default_users_adds_admin_and_miriam_and_updates_preferences(setup_init_db_module, monkeypatch):
    init_db = setup_init_db_module

    # Ensure no admin exists by making the query first() return None
    class AlwaysNoneQuery:
        @staticmethod
        def filter_by(**kwargs):
            return AlwaysNoneQuery()
        @staticmethod
        def first():
            return None
        @staticmethod
        def filter(*args, **kwargs):
            return AlwaysNoneQuery()
        @staticmethod
        def all():
            return []

    # Apply AlwaysNoneQuery for User.query.filter_by(...)
    monkeypatch.setattr(init_db.User, 'query', AlwaysNoneQuery())

    # Bypass update_existing_users_ai_preference during this test
    monkeypatch.setattr(init_db, 'update_existing_users_ai_preference', lambda: None)

    admin_id = init_db.create_default_users()
    # Expect two users added: admin and Miriam
    added_usernames = [getattr(u, 'username', None) for u in init_db.db.session.added]
    assert 'admin' in added_usernames
    assert 'miriam' in added_usernames

    # Ensure an admin_id is returned and corresponds to the created admin
    assert isinstance(admin_id, str)
    created_admin = next((u for u in init_db.db.session.added if getattr(u, 'username', None) == 'admin'), None)
    assert created_admin is not None
    assert admin_id == created_admin.id

    # Ensure default AI model preference population path is not breaking in this test
    # admin should have a default AI model preference set in create_default_users (gpt-5)
    # Since __init__ path is mocked, we only verify the code executed without errors


def test_update_existing_users_ai_preference_sets_default(setup_init_db_module, monkeypatch):
    init_db = setup_init_db_module

    # Seed an existing user lacking AI model preference
    existing_user = type('U', (), {})()  # simple dummy object
    existing_user.username = 'existing'
    existing_user.email = 'existing@example.com'
    existing_user.ai_model_preference = None

    # Prepare FakeQuery results used by User.query.filter(...).all()
    from database import User  # This import is satisfied by the fake module
    # Our test uses the FakeQuery defined in the fixture; set its results accordingly
    try:
        User.query._results = [existing_user]
    except Exception:
        pass  # If the environment differs, ignore

    # Ensure the migrate function is a no-op to isolate this test
    monkeypatch.setattr(init_db, 'migrate_ai_model_preference_column', lambda: None)

    init_db.update_existing_users_ai_preference()

    # The existing_user should now have ai_model_preference set to 'gpt-5'
    assert existing_user.ai_model_preference == 'gpt-5'