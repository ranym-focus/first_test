import types
import uuid
from datetime import datetime

import pytest

import init_db as init_db_module


# Helper dummy classes for User model simulations
class DummyQuery:
    def __init__(self, first_result=None, all_results=None):
        self._first = first_result
        self._all = all_results if all_results is not None else []

    def filter_by(self, **kwargs):
        return self

    def first(self):
        return self._first

    def all(self):
        return list(self._all)


class DummyUserForUpdate:
    # Attribute to simulate SA expression for ai_model_preference
    class _Attr:
        def __eq__(self, other):
            return self  # Dummy expression object

    ai_model_preference = _Attr()
    query = DummyQuery()


class DummyBinaryExpression:
    def __or__(self, other):
        return self


def test_remove_username_constraint_success(monkeypatch, capsys):
    class DummyDBSession:
        def execute(self, sql, *args, **kwargs):
            return None
        def commit(self):
            pass
        def rollback(self):
            pass

    dummy_db = types.SimpleNamespace(session=DummyDBSession())
    monkeypatch.setattr(init_db_module, 'db', dummy_db)
    init_db_module.remove_username_constraint()
    captured = capsys.readouterr()
    assert "✅ Username constraint removed successfully!" in captured.out


def test_remove_username_constraint_failure(monkeypatch, capsys):
    class DummyDBSession:
        def __init__(self):
            self.rolled_back = False

        def execute(self, sql, *args, **kwargs):
            raise Exception("boom")

        def commit(self):
            pass

        def rollback(self):
            self.rolled_back = True

    dummy_db = types.SimpleNamespace(session=DummyDBSession())
    monkeypatch.setattr(init_db_module, 'db', dummy_db)
    init_db_module.remove_username_constraint()
    captured = capsys.readouterr()
    assert "Error removing constraint" in captured.out or "❌" in captured.out
    assert dummy_db.session.rolled_back is True


def test_check_column_exists_true_false(monkeypatch):
    # Patch inspect to simulate columns in a table
    class DummyInspector:
        def __init__(self, cols):
            self._cols = cols

        def get_columns(self, table_name):
            return self._cols

    monkeypatch.setattr(init_db_module, 'inspect', lambda engine: DummyInspector([{'name': 'existing'}, {'name': 'another'}]))
    # Test existing
    assert init_db_module.check_column_exists('projects', 'existing') is True
    # Test non-existing
    assert init_db_module.check_column_exists('projects', 'missing') is False


def test_add_project_user_id_success(monkeypatch, capsys):
    # Ensure column does not exist
    monkeypatch.setattr(init_db_module, 'check_column_exists', lambda table, col: False)
    # Pretend to be sqlite
    monkeypatch.setitem(init_db_module.app.config, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///test.db')

    class DummyDBSession:
        def __init__(self):
            self.executed = []

        def execute(self, sql, *args, **kwargs):
            self.executed.append(sql)

        def commit(self):
            pass

        def rollback(self):
            pass

    dummy_db = types.SimpleNamespace(session=DummyDBSession())
    monkeypatch.setattr(init_db_module, 'db', dummy_db)

    init_db_module.add_project_user_id()
    captured = capsys.readouterr()
    assert "user_id column added to projects table successfully" in captured.out


def test_add_project_user_id_failure(monkeypatch, capsys):
    class DummyDBSession:
        def execute(self, sql, *args, **kwargs):
            raise Exception("fail")

        def commit(self):
            pass

        def rollback(self):
            pass

    dummy_db = types.SimpleNamespace(session=DummyDBSession())
    monkeypatch.setattr(init_db_module, 'db', dummy_db)
    monkeypatch.setattr(init_db_module, 'check_column_exists', lambda t, c: False)
    monkeypatch.setitem(init_db_module.app.config, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///test.db')

    init_db_module.add_project_user_id()
    captured = capsys.readouterr()
    assert "Error adding user_id column" in captured.out or "❌" in captured.out


def test_create_default_users_admin_exists(monkeypatch):
    existing_admin = types.SimpleNamespace(id='existing-admin-id')
    class DummyUser:
        # Simulate an existing admin in the DB
        query = DummyQuery(first_result=existing_admin)

        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
            self.password = None

        def set_password(self, pw):
            self.password = pw

    dummy_db = types.SimpleNamespace(session=type('S', (), {'add': lambda self, o: None, 'commit': lambda self: None, 'rollback': lambda self: None})())
    monkeypatch.setattr(init_db_module, 'db', dummy_db)
    monkeypatch.setattr(init_db_module, 'User', DummyUser)
    admin_id = init_db_module.create_default_users()
    assert admin_id == 'existing-admin-id'


def test_create_default_users_admin_created(monkeypatch):
    created_users = []

    class DummyUser:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.password = None
            created_users.append(self)

        def set_password(self, pw):
            self.password = pw

        # For admin existence check
        query = DummyQuery(first_result=None)

    class DummySession:
        def __init__(self):
            self.added = []

        def add(self, obj):
            self.added.append(obj)

        def commit(self):
            pass

        def rollback(self):
            pass

    dummy_db = types.SimpleNamespace(session=DummySession())
    monkeypatch.setattr(init_db_module, 'db', dummy_db)
    monkeypatch.setattr(init_db_module, 'User', DummyUser)
    # Ensure no existing admin
    DummyUser.query = DummyQuery(first_result=None)
    # Patch to avoid side effects of update_existing_users_ai_preference
    monkeypatch.setattr(init_db_module, 'update_existing_users_ai_preference', lambda: None)

    admin_id = init_db_module.create_default_users()
    # Two users should be created
    assert len(created_users) == 2
    usernames = [u.username for u in created_users]
    assert 'admin' in usernames
    assert 'miriam' in usernames
    assert isinstance(admin_id, str) and len(admin_id) > 0


def test_update_existing_users_ai_preference_updates(monkeypatch):
    # Patch migration step
    called = {'migrate': False}
    monkeypatch.setattr(init_db_module, 'migrate_ai_model_preference_column', lambda: called.update({'migrate': True}))
    # Prepare two users: one without preference, one with existing
    user1 = types.SimpleNamespace(username='u1', ai_model_preference=None)
    user2 = types.SimpleNamespace(username='u2', ai_model_preference='gpt-4')

    class DummyUser:
        ai_model_preference = DummyUserForUpdate.ai_model_preference
        query = DummyQuery(all_results=[user1, user2])

    monkeypatch.setattr(init_db_module, 'User', DummyUser)

    # Patch db.session
    class DummyDBSession:
        def __init__(self):
            self.committed = False
        def commit(self):
            self.committed = True
    dummy_db = types.SimpleNamespace(session=DummyDBSession())
    monkeypatch.setattr(init_db_module, 'db', dummy_db)

    init_db_module.update_existing_users_ai_preference()

    assert user1.ai_model_preference == 'gpt-5'
    assert user2.ai_model_preference == 'gpt-4'
    assert dummy_db.session.committed is True
    assert called['migrate'] is True


def test_add_organization_id_to_users_success(monkeypatch, capsys):
    monkeypatch.setattr(init_db_module, 'check_column_exists', lambda table, col: False)
    monkeypatch.setitem(init_db_module.app.config, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///test.db')
    class DummyDBSession:
        def __init__(self):
            self.executed = []
        def execute(self, sql, *args, **kwargs):
            self.executed.append(sql)
        def commit(self): pass
        def rollback(self): pass
    dummy_db = types.SimpleNamespace(session=DummyDBSession())
    monkeypatch.setattr(init_db_module, 'db', dummy_db)

    init_db_module.add_organization_id_to_users()
    captured = capsys.readouterr()
    assert "organization_id column added to users table successfully" in captured.out or "✅ organization_id column added to users table successfully" in captured.out


def test_add_organization_id_to_users_failure(monkeypatch, capsys):
    class DummyDBSession:
        def execute(self, sql, *args, **kwargs):
            raise Exception("fail")

        def commit(self): pass
        def rollback(self): pass
    dummy_db = types.SimpleNamespace(session=DummyDBSession())
    monkeypatch.setattr(init_db_module, 'db', dummy_db)
    monkeypatch.setattr(init_db_module, 'check_column_exists', lambda table, col: False)
    monkeypatch.setitem(init_db_module.app.config, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///test.db')

    init_db_module.add_organization_id_to_users()
    captured = capsys.readouterr()
    assert "Error adding organization_id column" in captured.out or "❌" in captured.out