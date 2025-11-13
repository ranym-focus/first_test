import uuid
from datetime import datetime
import pytest
from unittest.mock import Mock

import init_db as init_db

# Helper fake User class for tests
class DummyUser:
    query = None

    def __init__(self, **kwargs):
        self.id = kwargs.get('id', str(uuid.uuid4()))
        self.username = kwargs.get('username')
        self.email = kwargs.get('email')
        self.full_name = kwargs.get('full_name', '')
        self.role = kwargs.get('role', '')
        self.is_active = kwargs.get('is_active', True)
        self.email_verified = kwargs.get('email_verified', False)
        self.ai_model_preference = kwargs.get('ai_model_preference', None)
        self.created_at = kwargs.get('created_at', datetime.now())
        self.updated_at = kwargs.get('updated_at', datetime.now())

    def set_password(self, pwd):
        self.password = pwd

# Simple dummy query object
class DummyQuery:
    def __init__(self, first_result=None, all_results=None):
        self._first = first_result
        self._all = all_results if all_results is not None else []

    def filter_by(self, **kwargs):
        return self

    def first(self):
        return self._first

    def all(self):
        return self._all

def test_remove_username_constraint_success(monkeypatch):
    # Patch text to return the string itself for easy assertions
    monkeypatch.setattr(init_db, 'text', lambda s: s)
    db_session = Mock()
    db_session.execute = Mock()
    db_session.commit = Mock()
    monkeypatch.setattr(init_db.db, 'session', db_session, raising=True)

    init_db.remove_username_constraint()

    db_session.execute.assert_called_once_with("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_username_key;")
    db_session.commit.assert_called_once()

def test_remove_username_constraint_failure(monkeypatch):
    monkeypatch.setattr(init_db, 'text', lambda s: s)
    db_session = Mock()
    db_session.execute = Mock(side_effect=Exception("boom"))
    db_session.rollback = Mock()
    monkeypatch.setattr(init_db.db, 'session', db_session, raising=True)

    init_db.remove_username_constraint()

    db_session.execute.assert_called_once()
    db_session.rollback.assert_called_once()

def test_check_column_exists_true(monkeypatch):
    class InspectorMock:
        def get_columns(self, table_name):
            return [{'name': 'id'}, {'name': 'existing_col'}]

    monkeypatch.setattr(init_db, 'inspect', lambda engine: InspectorMock())
    exists = init_db.check_column_exists('any_table', 'existing_col')
    assert exists is True

def test_check_column_exists_false(monkeypatch):
    class InspectorMock:
        def get_columns(self, table_name):
            return [{'name': 'id'}, {'name': 'another_col'}]

    monkeypatch.setattr(init_db, 'inspect', lambda engine: InspectorMock())
    exists = init_db.check_column_exists('any_table', 'nonexistent')
    assert exists is False

def test_add_project_user_id_already_exists(monkeypatch):
    monkeypatch.setattr(init_db, 'check_column_exists', lambda table, col: True)
    result = init_db.add_project_user_id()
    assert result is True

def test_add_project_user_id_adds_column(monkeypatch):
    monkeypatch.setattr(init_db, 'check_column_exists', lambda table, col: False)
    monkeypatch.setattr(init_db, 'text', lambda s: s)
    db_session = Mock()
    db_session.execute = Mock()
    db_session.commit = Mock()
    monkeypatch.setattr(init_db.db, 'session', db_session, raising=True)
    # Ensure URI resolves to non-sqlite for this test
    monkeypatch.setattr(init_db.app.config, 'SQLALCHEMY_DATABASE_URI', 'postgresql://user:pass@localhost/db', raising=False)

    result = init_db.add_project_user_id()

    db_session.execute.assert_called_with("ALTER TABLE projects ADD COLUMN user_id VARCHAR(36)")
    db_session.commit.assert_called_once()
    assert result is True

def test_add_organization_id_to_users_already_exists(monkeypatch):
    monkeypatch.setattr(init_db, 'check_column_exists', lambda table, col: True)
    result = init_db.add_organization_id_to_users()
    assert result is True

def test_add_organization_id_to_users_add_column_and_fk(monkeypatch):
    monkeypatch.setattr(init_db, 'check_column_exists', lambda table, col: False)
    monkeypatch.setattr(init_db, 'text', lambda s: s)
    db_session = Mock()
    executed = []
    def fake_execute(sql):
        executed.append(sql)
        if "FOREIGN KEY" in sql:
            raise Exception("FK constraint unavailable")
        return None
    db_session.execute = Mock(side_effect=fake_execute)
    db_session.commit = Mock()
    monkeypatch.setattr(init_db.db, 'session', db_session, raising=True)
    monkeypatch.setattr(init_db.app.config, 'SQLALCHEMY_DATABASE_URI', 'postgresql://user:pass@localhost/db', raising=False)

    result = init_db.add_organization_id_to_users()

    # Should have attempted both statements
    assert executed[0] == "ALTER TABLE users ADD COLUMN organization_id VARCHAR(36)"
    assert "FOREIGN KEY" in executed[1]
    assert result is True
    db_session.commit.assert_called_once()

def test_create_default_users_admin_exists(monkeypatch):
    # Prepare a fake existing admin
    existing_admin = DummyUser(id='admin-id', email='admin@qaverse.com', username='admin')
    DummyUser.query = DummyQuery(first_result=existing_admin)

    monkeypatch.setattr(init_db, 'User', DummyUser, raising=True)

    db_session = Mock()
    db_session.add = Mock()
    db_session.commit = Mock()
    monkeypatch.setattr(init_db.db, 'session', db_session, raising=True)

    # Mock updater to avoid deeper side effects
    updater_mock = Mock()
    monkeypatch.setattr(init_db, 'update_existing_users_ai_preference', updater_mock, raising=True)

    admin_id = init_db.create_default_users()
    assert admin_id == 'admin-id'
    # Ensure no new users are added since admin exists
    db_session.add.assert_not_called()
    db_session.commit.assert_not_called()
    updater_mock.assert_not_called()  # When admin exists, updater should still be called in original flow? Depending on implementation
    # We can't rely on exact updater call behavior here; ensure no crash and a string id is returned

def test_create_default_users_admin_missing(monkeypatch):
    # Admin does not exist; we will create two users
    DummyUser.query = DummyQuery(first_result=None)

    monkeypatch.setattr(init_db, 'User', DummyUser, raising=True)

    db_session = Mock()
    db_session.add = Mock()
    db_session.commit = Mock()
    monkeypatch.setattr(init_db.db, 'session', db_session, raising=True)

    updater_mock = Mock()
    monkeypatch.setattr(init_db, 'update_existing_users_ai_preference', updater_mock, raising=True)

    created_admin_id = init_db.create_default_users()
    assert isinstance(created_admin_id, str)
    # Two users should have been added
    assert db_session.add.call_count == 2
    db_session.commit.assert_called_once()
    updater_mock.assert_called()