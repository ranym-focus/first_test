"""
QAVerse Database Initialization and Migration Script

This script handles database initialization, schema migrations, and sample data creation
for the QAVerse application. It ensures the database schema is up-to-date with all
the latest changes and migrations.

FEATURES:
- Complete database table creation
- Schema migrations for all database changes
- AI model preference support
- User management with default admin accounts
- Sample data creation for development/testing
- Production-ready migration support

USAGE:
    python init_db.py --full-init     # Full initialization with sample data
    python init_db.py --migrate-only  # Run migrations only (for production)
    python init_db.py --sample-data   # Create sample data only
    python init_db.py                 # Default: create sample data

MIGRATIONS INCLUDED:
- AI model preference column for users
- BDD scenarios examples_data column
- BDD features content column (Gherkin)
- BDD steps element_metadata column (for Selenium)
- User roles content column (JSON data)
- Document analysis content column (JSON data)
- BDD scenario name length increase (255 -> 1000 chars)
- Test runs user_id column for multi-tenant support
- Projects user_id column for ownership
- Users organization_id column for organization support
- Users email verification columns (email_verified, verification_token, etc.)
- Username constraint removal for flexibility
- Test management cascade delete constraints (for proper test run deletion)
- Test cases category column length increase (100 -> 1000 chars)
- Selenium tests table schema completion (test_framework, last_run_* columns)
- Uploaded code files table creation (for unit test generation feature)
- User preferences table creation (for AI model selection feature)
- Test management unique constraints (prevent duplicate names per project/phase)
- SDD reviews table creation (for SDD analysis feature)
- SDD enhancements table creation (for SDD enhancement feature)
- Project unit tests table creation (for project-level unit test management)
- Virtual testing tables creation (virtual_test_executions, generated_bdd_scenarios, generated_manual_tests, generated_automation_tests)
- Workflow system tables creation (workflows, workflow_executions, workflow_node_executions)
- Users test_runs_passed and test_runs_limit columns (for usage tracking)

PRODUCTION DEPLOYMENT:
For AWS production deployment, use:
    python init_db.py --migrate-only

This will run all necessary migrations without creating sample data.
"""

import os
import sys
import uuid
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask
from sqlalchemy import inspect, text
from database import (
    init_db, db, User, Organization, OrganizationMember, Project, TestRun, TestPhase, TestPlan, TestPackage,
    TestCaseExecution, DocumentAnalysis, UserRole, UserPreferences, BDDFeature, BDDScenario, BDDStep,
    TestCase, TestCaseStep, TestCaseData, TestCaseDataInput, TestRunResult,
    SeleniumTest, UnitTest, GeneratedCode, UploadedCodeFile, Integration, JiraSyncItem,
    CrawlMeta, CrawlPage, TestPlanTestRun, TestPackageTestRun,
    VirtualTestExecution, GeneratedBDDScenario, GeneratedManualTest, GeneratedAutomationTest, TestExecutionComparison,
    SDDReviews, SDDEnhancements, ProjectUnitTests,
    Workflow, WorkflowExecution, WorkflowNodeExecution,
    TestPipeline, PipelineExecution, PipelineStageExecution, PipelineStepExecution
)

# Set UTF-8 encoding for Windows compatibility
if sys.platform == 'win32':
    # Set console encoding to UTF-8
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    # Set environment variable for PostgreSQL client encoding
    os.environ['PGCLIENTENCODING'] = 'UTF8'

# Load environment variables
load_dotenv()

# Create a Flask app
app = Flask(__name__)

# Configure SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://qaverse_user:qaverse_password@127.0.0.1:5432/qaverse_dev')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the database
init_db(app)

def remove_username_constraint():
    """Remove the unique constraint on username field from users table."""
    try:
        # Execute SQL directly using SQLAlchemy
        db.session.execute(text('ALTER TABLE users DROP CONSTRAINT IF EXISTS users_username_key;'))
        db.session.commit()
        print("✅ Username constraint removed successfully!")
    except Exception as e:
        print(f"❌ Error removing constraint: {e}")
        db.session.rollback()

def check_column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns

def add_project_user_id():
    """Add user_id column to projects table if it doesn't exist."""
    try:
        # Check if the column already exists
        if check_column_exists('projects', 'user_id'):
            print("✅ user_id column already exists in projects table.")
            return True

        print("🔧 Adding user_id column to projects table...")

        # Determine the database type
        db_url = app.config['SQLALCHEMY_DATABASE_URI']
        is_sqlite = db_url.startswith('sqlite')

        # Add the user_id column
        if is_sqlite:
            # SQLite syntax
            db.session.execute(text("ALTER TABLE projects ADD COLUMN user_id VARCHAR(36)"))
        else:
            # PostgreSQL or MySQL
            db.session.execute(text("ALTER TABLE projects ADD COLUMN user_id VARCHAR(36)"))

        db.session.commit()
        print("✅ user_id column added to projects table successfully!")
        return True

    except Exception as e:
        print(f"❌ Error adding user_id column: {e}")
        db.session.rollback()
        return False

def add_organization_id_to_users():
    """Add organization_id column to users table if it doesn't exist."""
    try:
        # Check if the column already exists
        if check_column_exists('users', 'organization_id'):
            print("✅ organization_id column already exists in users table.")
            return True

        print("🔧 Adding organization_id column to users table...")

        # Determine the database type
        db_url = app.config['SQLALCHEMY_DATABASE_URI']
        is_sqlite = db_url.startswith('sqlite')

        # Add the organization_id column
        if is_sqlite:
            # SQLite syntax
            db.session.execute(text("ALTER TABLE users ADD COLUMN organization_id VARCHAR(36)"))
        else:
            # PostgreSQL or MySQL - Add column and foreign key constraint
            db.session.execute(text("ALTER TABLE users ADD COLUMN organization_id VARCHAR(36)"))
            # Add foreign key constraint if organizations table exists
            try:
                db.session.execute(text("ALTER TABLE users ADD CONSTRAINT fk_users_organization_id FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE SET NULL"))
            except Exception as fk_error:
                print(f"⚠️ Could not add foreign key constraint (organizations table may not exist yet): {fk_error}")

        db.session.commit()
        print("✅ organization_id column added to users table successfully!")
        return True

    except Exception as e:
        print(f"❌ Error adding organization_id column: {e}")
        db.session.rollback()
        return False

def create_default_users():
    """Create default users in the database."""
    # Check if admin user already exists
    admin_user = User.query.filter_by(email='admin@qaverse.com').first()
    if admin_user:
        print("Admin user already exists. Skipping user creation.")
        return admin_user.id

    # Create admin user
    admin_id = str(uuid.uuid4())
    admin_user = User(
        id=admin_id,
        username='admin',
        email='admin@qaverse.com',
        full_name='QAVerse Administrator',
        role='admin',
        is_active=True,
        email_verified=True,
        ai_model_preference='gpt-5',  # Set default AI model preference
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    admin_user.set_password('admin')
    db.session.add(admin_user)

    # Create user for Miriam
    miriam_id = str(uuid.uuid4())
    miriam_user = User(
        id=miriam_id,
        username='miriam',
        email='miriam.dahmoun@gmail.com',
        full_name='Miriam Dahmoun',
        role='admin',
        is_active=True,
        email_verified=True,
        ai_model_preference='gpt-5',  # Set default AI model preference
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    miriam_user.set_password('password123')
    db.session.add(miriam_user)

    db.session.commit()
    print("Default users created successfully.")

    # Update existing users with default AI model preference if they don't have one
    update_existing_users_ai_preference()

    return admin_id

def update_existing_users_ai_preference():
    """Update existing users with default AI model preference if they don't have one."""
    try:
        # First, ensure the ai_model_preference column exists
        migrate_ai_model_preference_column()

        # Find users without AI model preference set
        users_without_preference = User.query.filter(
            (User.ai_model_preference == None) | (User.ai_model_preference == '')
        ).all()

        if users_without_preference:
            print(f"Updating {len(users_without_preference)} existing users with default AI model preference...")

            for user in users_without_preference:
                user.ai_model_preference = 'gpt-5'  # Set default to gpt-5
                print(f"  - Updated user: {user.username} ({user.email})")

            db.session.commit()
            print("✅ Existing users updated with AI model preferences")
        else:
            print("✅ All users already have AI model preferences set")

    except Exception as e:
        print(f"⚠️ Error updating existing users: {e}")
        db.session.rollback()

def migrate_ai_model_preference_column():
    """Add ai_model_preference column to users table if it doesn't exist."""
    try:
        from sqlalchemy import inspect, text

        # Check if the column already exists
        inspector = inspect(db.engine)
        columns = inspector.get_columns('users')
        column_names = [col['name'] for col in columns]

        if 'ai_model_preference' not in column_names:
            print("Adding ai_model_preference column to users table...")

            # Add the column with default value
            db.session.execute(text("""
                ALTER TABLE users
                ADD COLUMN ai_model_preference VARCHAR(50) DEFAULT 'gpt-5'
            """))
            db.session.commit()

            print("✅ ai_model_preference column added successfully")
        else:
            print("✅ ai_model_preference column already exists")

    except Exception as e:
        print(f"⚠️ Error adding ai_model_preference column: {e}")
        db.session.rollback()
        # Don't raise the exception, just log it

def migrate_bdd_scenarios_examples_data():
    """Add examples_data column to bdd_scenarios table if it doesn't exist."""
    try:
        # Check if the column already exists
        if check_column_exists('bdd_scenarios', 'examples_data'):
            print("✅ examples_data column already exists in bdd_scenarios table.")
            return True

        print("🔧 Adding examples_data column to bdd_scenarios table...")

        # Add the examples_data column
        db.session.execute(text("ALTER TABLE bdd_scenarios ADD COLUMN examples_data TEXT"))
        db.session.commit()
        print("✅ examples_data column added to bdd_scenarios table successfully!")
        return True

    except Exception as e:
        print(f"❌ Error adding examples_data column: {e}")
        db.session.rollback()
        return False

def migrate_bdd_features_content():
    """Add content column to bdd_features table if it doesn't exist."""
    try:
        # Check if the column already exists
        if check_column_exists('bdd_features', 'content'):
            print("✅ content column already exists in bdd_features table.")
            return True

        print("🔧 Adding content column to bdd_features table...")

        # Add the content column
        db.session.execute(text("ALTER TABLE bdd_features ADD COLUMN content TEXT"))
        db.session.commit()
        print("✅ content column added to bdd_features table successfully!")
        return True

    except Exception as e:
        print(f"❌ Error adding content column: {e}")
        db.session.rollback()
        return False

def migrate_bdd_steps_element_metadata():
    """Add element_metadata column to bdd_steps table if it doesn't exist."""
    try:
        # Check if the column already exists
        if check_column_exists('bdd_steps', 'element_metadata'):
            print("✅ element_metadata column already exists in bdd_steps table.")
            return True

        print("🔧 Adding element_metadata column to bdd_steps table...")

        # Determine the database type
        db_url = app.config['SQLALCHEMY_DATABASE_URI']
        is_sqlite = db_url.startswith('sqlite')

        # Add the element_metadata column
        if is_sqlite:
            # SQLite syntax
            db.session.execute(text("ALTER TABLE bdd_steps ADD COLUMN element_metadata TEXT"))
        else:
            # PostgreSQL or MySQL - use JSONB for better performance
            db.session.execute(text("ALTER TABLE bdd_steps ADD COLUMN element_metadata JSONB"))

        db.session.commit()
        print("✅ element_metadata column added to bdd_steps table successfully!")
        return True

    except Exception as e:
        print(f"❌ Error adding element_metadata column: {e}")
        db.session.rollback()
        return False

def migrate_user_roles_content():
    """Add content column to user_roles table if it doesn't exist."""
    try:
        # Check if the column already exists
        if check_column_exists('user_roles', 'content'):
            print("✅ content column already exists in user_roles table.")
            return True

        print("🔧 Adding content column to user_roles table...")

        # Determine the database type
        db_url = app.config['SQLALCHEMY_DATABASE_URI']
        is_sqlite = db_url.startswith('sqlite')

        # Add the content column
        if is_sqlite:
            # SQLite syntax
            db.session.execute(text("ALTER TABLE user_roles ADD COLUMN content TEXT"))
        else:
            # PostgreSQL or MySQL - use JSONB for better performance
            db.session.execute(text("ALTER TABLE user_roles ADD COLUMN content JSONB"))

        db.session.commit()
        print("✅ content column added to user_roles table successfully!")
        return True

    except Exception as e:
        print(f"❌ Error adding content column: {e}")
        db.session.rollback()
        return False

def migrate_document_analysis_content():
    """Add content column to document_analysis table if it doesn't exist."""
    try:
        # Check if the column already exists
        if check_column_exists('document_analysis', 'content'):
            print("✅ content column already exists in document_analysis table.")
            return True

        print("🔧 Adding content column to document_analysis table...")

        # Determine the database type
        db_url = app.config['SQLALCHEMY_DATABASE_URI']
        is_sqlite = db_url.startswith('sqlite')

        # Add the content column
        if is_sqlite:
            # SQLite syntax
            db.session.execute(text("ALTER TABLE document_analysis ADD COLUMN content TEXT"))
        else:
            # PostgreSQL or MySQL - use JSONB for better performance
            db.session.execute(text("ALTER TABLE document_analysis ADD COLUMN content JSONB"))

        db.session.commit()
        print("✅ content column added to document_analysis table successfully!")
        return True

    except Exception as e:
        print(f"❌ Error adding content column: {e}")
        db.session.rollback()
        return False

def migrate_bdd_scenario_name_length():
    """Increase the length of the name column in bdd_scenarios table from 255 to 1000 characters."""
    try:
        print("🔧 Updating bdd_scenarios name column length to 1000 characters...")

        # Determine the database type
        db_url = app.config['SQLALCHEMY_DATABASE_URI']
        is_sqlite = db_url.startswith('sqlite')

        if is_sqlite:
            # SQLite doesn't support ALTER COLUMN, but it's more flexible with text lengths
            print("✅ SQLite detected - text length is flexible, no migration needed")
        else:
            # PostgreSQL or MySQL
            db.session.execute(text("ALTER TABLE bdd_scenarios ALTER COLUMN name TYPE VARCHAR(1000)"))
            db.session.commit()
            print("✅ bdd_scenarios name column length updated successfully!")

        return True

    except Exception as e:
        print(f"❌ Error updating bdd_scenarios name column length: {e}")
        db.session.rollback()
        return False

def migrate_test_run_user_id():
    """Add user_id column to test_runs table if it doesn't exist."""
    try:
        # Check if the column already exists
        if check_column_exists('test_runs', 'user_id'):
            print("✅ user_id column already exists in test_runs table.")
            return True

        print("🔧 Adding user_id column to test_runs table...")

        # Add the user_id column
        db.session.execute(text("ALTER TABLE test_runs ADD COLUMN user_id VARCHAR(36)"))

        # Add foreign key constraint if using PostgreSQL
        db_url = app.config['SQLALCHEMY_DATABASE_URI']
        if not db_url.startswith('sqlite'):
            try:
                db.session.execute(text("ALTER TABLE test_runs ADD CONSTRAINT fk_test_runs_user_id FOREIGN KEY (user_id) REFERENCES users(id)"))
            except Exception as e:
                print(f"⚠️ Could not add foreign key constraint: {e}")

        db.session.commit()
        print("✅ user_id column added to test_runs table successfully!")
        return True

    except Exception as e:
        print(f"❌ Error adding user_id column to test_runs: {e}")
        db.session.rollback()
        return False

def migrate_test_management_cascade_deletes():
    """Ensure cascade delete constraints are properly set for test management tables."""
    try:
        print("🔧 Updating test management foreign key constraints for cascade deletes...")

        # Determine the database type
        db_url = app.config['SQLALCHEMY_DATABASE_URI']
        is_sqlite = db_url.startswith('sqlite')

        if is_sqlite:
            # SQLite doesn't support modifying foreign key constraints after table creation
            print("✅ SQLite detected - cascade deletes handled by SQLAlchemy ORM")
            return True

        # For PostgreSQL, ensure the foreign key constraints have CASCADE DELETE
        try:
            # Check if the constraints already have CASCADE DELETE
            # If not, we'll drop and recreate them

            # Drop existing constraints if they exist (ignore errors if they don't exist)
            try:
                db.session.execute(text("ALTER TABLE test_plan_test_runs DROP CONSTRAINT IF EXISTS test_plan_test_runs_test_run_id_fkey"))
                db.session.execute(text("ALTER TABLE test_package_test_runs DROP CONSTRAINT IF EXISTS test_package_test_runs_test_run_id_fkey"))
            except Exception as e:
                print(f"⚠️ Note: Some constraints may not exist yet: {e}")

            # Add the constraints with CASCADE DELETE
            db.session.execute(text("""
                ALTER TABLE test_plan_test_runs
                ADD CONSTRAINT test_plan_test_runs_test_run_id_fkey
                FOREIGN KEY (test_run_id) REFERENCES test_runs(id) ON DELETE CASCADE
            """))

            db.session.execute(text("""
                ALTER TABLE test_package_test_runs
                ADD CONSTRAINT test_package_test_runs_test_run_id_fkey
                FOREIGN KEY (test_run_id) REFERENCES test_runs(id) ON DELETE CASCADE
            """))

            db.session.commit()
            print("✅ Test management cascade delete constraints updated successfully!")
            return True

        except Exception as e:
            print(f"⚠️ Could not update cascade delete constraints: {e}")
            # This is not critical - the SQLAlchemy ORM relationships will handle the deletes
            db.session.rollback()
            return True

    except Exception as e:
        print(f"❌ Error updating cascade delete constraints: {e}")
        db.session.rollback()
        return False


def migrate_test_cases_category_length():
    """Increase test_cases category column length from 100 to 255 characters."""
    try:
        inspector = inspect(db.engine)

        # Check if test_cases table exists
        if 'test_cases' not in inspector.get_table_names():
            print("⚠️ test_cases table doesn't exist, skipping category length migration")
            return True

        print("🔧 Migrating test_cases category column length...")

        # Check current column definition
        columns = inspector.get_columns('test_cases')
        category_column = next((col for col in columns if col['name'] == 'category'), None)

        if not category_column:
            print("⚠️ category column doesn't exist in test_cases table")
            return True

        # Check if migration is needed
        current_length = getattr(category_column.get('type'), 'length', None)

        if current_length and current_length >= 255:
            print("✅ test_cases category column already has sufficient length")
            return True

        # Perform migration for PostgreSQL
        if db.engine.dialect.name == 'postgresql':
            try:
                db.session.execute(text("ALTER TABLE test_cases ALTER COLUMN category TYPE character varying(255)"))
                db.session.commit()
                print("✅ test_cases category column length increased to 255 characters")
                return True
            except Exception as e:
                print(f"⚠️ Error increasing category column length: {e}")
                db.session.rollback()
                return False
        else:
            # For other databases (SQLite, MySQL)
            try:
                db.session.execute(text("ALTER TABLE test_cases MODIFY COLUMN category VARCHAR(255)"))
                db.session.commit()
                print("✅ test_cases category column length increased to 255 characters")
                return True
            except Exception as e:
                print(f"⚠️ Error increasing category column length: {e}")
                db.session.rollback()
                return False

    except Exception as e:
        print(f"⚠️ Error in test_cases category length migration: {e}")
        db.session.rollback()
        return False

def migrate_uploaded_code_files_table():
    """Create uploaded_code_files table if it doesn't exist."""
    try:
        inspector = inspect(db.engine)

        # Check if the table already exists
        if 'uploaded_code_files' in inspector.get_table_names():
            print("✅ uploaded_code_files table already exists.")
            return True

        print("🔧 Creating uploaded_code_files table...")

        # Determine the database type
        db_url = app.config['SQLALCHEMY_DATABASE_URI']
        is_sqlite = db_url.startswith('sqlite')

        # Create the table
        if is_sqlite:
            # SQLite syntax
            db.session.execute(text("""
                CREATE TABLE uploaded_code_files (
                    id VARCHAR(36) PRIMARY KEY,
                    project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
                    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
                    file_name VARCHAR(255) NOT NULL,
                    original_file_name VARCHAR(255) NOT NULL,
                    file_path VARCHAR(500) NOT NULL,
                    file_size INTEGER NOT NULL,
                    file_content TEXT NOT NULL,
                    language VARCHAR(50),
                    framework VARCHAR(100),
                    code_type VARCHAR(50),
                    testing_framework VARCHAR(50),
                    testing_strategy VARCHAR(100),
                    analysis_data TEXT,
                    confidence INTEGER DEFAULT 0,
                    unit_test_generated BOOLEAN DEFAULT 0,
                    unit_test_id VARCHAR(36) REFERENCES unit_tests(id),
                    status VARCHAR(20) DEFAULT 'uploaded',
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
        else:
            # PostgreSQL or MySQL
            db.session.execute(text("""
                CREATE TABLE uploaded_code_files (
                    id VARCHAR(36) PRIMARY KEY,
                    project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
                    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
                    file_name VARCHAR(255) NOT NULL,
                    original_file_name VARCHAR(255) NOT NULL,
                    file_path VARCHAR(500) NOT NULL,
                    file_size INTEGER NOT NULL,
                    file_content TEXT NOT NULL,
                    language VARCHAR(50),
                    framework VARCHAR(100),
                    code_type VARCHAR(50),
                    testing_framework VARCHAR(50),
                    testing_strategy VARCHAR(100),
                    analysis_data JSONB,
                    confidence INTEGER DEFAULT 0,
                    unit_test_generated BOOLEAN DEFAULT FALSE,
                    unit_test_id VARCHAR(36) REFERENCES unit_tests(id),
                    status VARCHAR(20) DEFAULT 'uploaded',
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

        db.session.commit()
        print("✅ uploaded_code_files table created successfully!")
        return True

    except Exception as e:
        print(f"❌ Error creating uploaded_code_files table: {e}")
        db.session.rollback()
        return False

def migrate_user_preferences_table():
    """Create user_preferences table if it doesn't exist."""
    try:
        inspector = inspect(db.engine)

        # Check if the table already exists
        if 'user_preferences' in inspector.get_table_names():
            print("✅ user_preferences table already exists.")
            return True

        print("🔧 Creating user_preferences table...")

        # Determine the database type
        db_url = app.config['SQLALCHEMY_DATABASE_URI']
        is_sqlite = db_url.startswith('sqlite')

        # Create the table
        if is_sqlite:
            # SQLite syntax
            db.session.execute(text("""
                CREATE TABLE user_preferences (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
                    ai_model VARCHAR(50) DEFAULT 'gpt-5',
                    temperature REAL DEFAULT 1.0,
                    max_tokens INTEGER DEFAULT 4000,
                    timeout INTEGER DEFAULT 30,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
        else:
            # PostgreSQL or MySQL
            db.session.execute(text("""
                CREATE TABLE user_preferences (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
                    ai_model VARCHAR(50) DEFAULT 'gpt-5',
                    temperature REAL DEFAULT 1.0,
                    max_tokens INTEGER DEFAULT 4000,
                    timeout INTEGER DEFAULT 30,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

        db.session.commit()
        print("✅ user_preferences table created successfully!")
        return True

    except Exception as e:
        print(f"❌ Error creating user_preferences table: {e}")
        db.session.rollback()
        return False

def migrate_users_email_verification():
    """Add email verification columns to users table if they don't exist."""
    try:
        # Check if the columns already exist
        if (check_column_exists('users', 'email_verified') and
            check_column_exists('users', 'verification_token') and
            check_column_exists('users', 'verification_token_expires_at')):
            print("✅ Email verification columns already exist in users table.")
            return True

        print("🔧 Adding email verification columns to users table...")

        # Add email verification columns
        if not check_column_exists('users', 'email_verified'):
            db.session.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT false"))

        if not check_column_exists('users', 'verification_token'):
            db.session.execute(text("ALTER TABLE users ADD COLUMN verification_token VARCHAR(100)"))

        if not check_column_exists('users', 'verification_token_expires_at'):
            db.session.execute(text("ALTER TABLE users ADD COLUMN verification_token_expires_at TIMESTAMP"))

        db.session.commit()
        print("✅ Email verification columns added successfully!")
        return True

    except Exception as e:
        print(f"❌ Error adding email verification columns: {e}")
        db.session.rollback()
        return False

def migrate_users_test_runs_passed():
    """Add test_runs_passed column to users table if it doesn't exist."""
    try:
        # Check if the column already exists
        if check_column_exists('users', 'test_runs_passed'):
            print("✅ test_runs_passed column already exists in users table.")
            return True

        print("🔧 Adding test_runs_passed column to users table...")

        # Add test_runs_passed column
        db.session.execute(text("ALTER TABLE users ADD COLUMN test_runs_passed INTEGER DEFAULT 0"))
        db.session.commit()

        print("✅ test_runs_passed column added successfully!")
        return True

    except Exception as e:
        print(f"❌ Error adding test_runs_passed column: {e}")
        db.session.rollback()
        return False

def migrate_users_test_runs_limit():
    """Add test_runs_limit column to users table if it doesn't exist."""
    try:
        # Check if the column already exists
        if check_column_exists('users', 'test_runs_limit'):
            print("✅ test_runs_limit column already exists in users table.")
            return True

        print("🔧 Adding test_runs_limit column to users table...")

        # Add test_runs_limit column
        db.session.execute(text("ALTER TABLE users ADD COLUMN test_runs_limit INTEGER"))
        db.session.commit()

        print("✅ test_runs_limit column added successfully!")
        return True

    except Exception as e:
        print(f"❌ Error adding test_runs_limit column: {e}")
        db.session.rollback()
        return False

def migrate_selenium_tests_schema():
    """Add missing columns to selenium_tests table if they don't exist."""
    try:
        # Check if selenium_tests table exists
        inspector = inspect(db.engine)
        if 'selenium_tests' not in inspector.get_table_names():
            print("⚠️ selenium_tests table doesn't exist yet - will be created by db.create_all()")
            return True

        # Check if the critical columns already exist
        missing_columns = []
        required_columns = [
            ('test_framework', 'VARCHAR(50)', 'selenium_python'),
            ('last_run_output', 'TEXT', None),
            ('last_run_error', 'TEXT', None),
            ('last_run_duration', 'INTEGER', None),
            ('last_run_screenshots', 'JSONB', None)
        ]

        for col_name, col_type, default_value in required_columns:
            if not check_column_exists('selenium_tests', col_name):
                missing_columns.append((col_name, col_type, default_value))

        if not missing_columns:
            print("✅ All selenium_tests columns already exist.")
            return True

        print("🔧 Adding missing columns to selenium_tests table...")

        # Add missing columns
        for col_name, col_type, default_value in missing_columns:
            alter_sql = f"ALTER TABLE selenium_tests ADD COLUMN {col_name} {col_type}"
            if default_value:
                alter_sql += f" DEFAULT '{default_value}'"

            db.session.execute(text(alter_sql))
            print(f"  ✅ Added {col_name} column")

        db.session.commit()
        print("✅ Selenium tests schema migration completed!")
        return True

    except Exception as e:
        print(f"❌ Error migrating selenium_tests schema: {e}")
        db.session.rollback()
        return False

def create_sample_data():
    """Create sample data in the database."""
    with app.app_context():
        # Check if there are already projects in the database
        if Project.query.count() > 0:
            print("Database already contains data. Skipping sample data creation.")
            return

        # Remove username constraint to allow duplicate usernames
        remove_username_constraint()

        # Add user_id column to projects table if needed
        add_project_user_id()

        # Add organization_id column to users table if needed
        add_organization_id_to_users()

        # Run all database migrations
        migrate_ai_model_preference_column()
        migrate_bdd_scenarios_examples_data()
        migrate_bdd_features_content()
        migrate_bdd_steps_element_metadata()
        migrate_user_roles_content()
        migrate_document_analysis_content()
        migrate_bdd_scenario_name_length()
        migrate_test_run_user_id()
        migrate_test_management_cascade_deletes()
        migrate_test_cases_category_length()
        migrate_uploaded_code_files_table()
        migrate_user_preferences_table()
        migrate_users_email_verification()
        migrate_users_test_runs_passed()
        migrate_users_test_runs_limit()
        migrate_selenium_tests_schema()
        migrate_sdd_reviews_table()
        migrate_sdd_enhancements_table()
        migrate_project_unit_tests_table()
        migrate_virtual_testing_tables()
        migrate_workflow_tables()
        migrate_test_management_unique_constraints()

        # Create default users first
        admin_user_id = create_default_users()

        # Create sample projects with user ownership
        projects = [
            {
                'id': str(uuid.uuid4()),
                'user_id': admin_user_id,
                'name': 'E-Commerce Platform',
                'description': 'Online shopping platform with user accounts, product catalog, and checkout process.',
                'status': 'active'
            },
            {
                'id': str(uuid.uuid4()),
                'user_id': admin_user_id,
                'name': 'Banking Application',
                'description': 'Secure banking application with account management, transfers, and bill payments.',
                'status': 'active'
            },
            {
                'id': str(uuid.uuid4()),
                'user_id': admin_user_id,
                'name': 'Healthcare Portal',
                'description': 'Patient portal for appointment scheduling, medical records, and communication with providers.',
                'status': 'active'
            }
        ]

        # Add projects to the database
        for project_data in projects:
            project = Project(**project_data)
            db.session.add(project)

        # Commit the changes
        db.session.commit()

        # Create sample test runs for each project
        now = datetime.now()

        # Sample domain expertise data
        def get_domain_expertise_for_project(project_name):
            """Get domain expertise data based on project type."""
            if 'Banking' in project_name:
                return {
                    'domain_info': {
                        'primary_business_domain': 'Banking and Financial Services',
                        'specific_sub_domains': [
                            'Account Management',
                            'Transaction Processing',
                            'Compliance and Regulatory',
                            'Payment Systems'
                        ],
                        'key_domain_specific_terminology': [
                            'Account Balance',
                            'Transaction History',
                            'KYC (Know Your Customer)',
                            'AML (Anti-Money Laundering)',
                            'Payment Gateway',
                            'Settlement Process'
                        ],
                        'domain_specific_business_rules': [
                            'All transactions must be logged for audit purposes',
                            'Account balances cannot go below zero without overdraft protection',
                            'Customer identity must be verified before account access',
                            'Regulatory compliance must be maintained for all operations'
                        ]
                    },
                    'domain_expertise': 'You are an expert in banking and financial services domain. When analyzing requirements and generating test cases, consider regulatory compliance, security measures, transaction integrity, and audit trails.',
                    'system_prompt_with_domain': 'Enhanced system prompt with banking domain expertise for comprehensive test case generation.'
                }
            elif 'E-Commerce' in project_name:
                return {
                    'domain_info': {
                        'primary_business_domain': 'E-Commerce and Retail',
                        'specific_sub_domains': [
                            'Product Catalog Management',
                            'Shopping Cart and Checkout',
                            'User Account Management',
                            'Payment Processing',
                            'Order Management'
                        ],
                        'key_domain_specific_terminology': [
                            'Product Catalog',
                            'Shopping Cart',
                            'Checkout Process',
                            'Payment Gateway',
                            'Order Fulfillment',
                            'Inventory Management'
                        ],
                        'domain_specific_business_rules': [
                            'Products must have valid inventory before purchase',
                            'Payment must be processed before order confirmation',
                            'User authentication required for checkout',
                            'Order tracking must be available after purchase'
                        ]
                    },
                    'domain_expertise': 'You are an expert in e-commerce and retail domain. Focus on user experience, payment security, inventory management, and order processing workflows.',
                    'system_prompt_with_domain': 'Enhanced system prompt with e-commerce domain expertise for comprehensive test case generation.'
                }
            else:  # Healthcare
                return {
                    'domain_info': {
                        'primary_business_domain': 'Healthcare and Medical Services',
                        'specific_sub_domains': [
                            'Patient Management',
                            'Appointment Scheduling',
                            'Medical Records',
                            'Provider Communication',
                            'HIPAA Compliance'
                        ],
                        'key_domain_specific_terminology': [
                            'Patient Portal',
                            'Medical Records',
                            'Appointment Scheduling',
                            'HIPAA Compliance',
                            'Provider Communication',
                            'Health Information'
                        ],
                        'domain_specific_business_rules': [
                            'Patient data must be HIPAA compliant',
                            'Medical records require proper authorization',
                            'Appointment scheduling must prevent conflicts',
                            'Provider communication must be secure'
                        ]
                    },
                    'domain_expertise': 'You are an expert in healthcare domain. Ensure HIPAA compliance, patient privacy, secure communication, and proper medical record management.',
                    'system_prompt_with_domain': 'Enhanced system prompt with healthcare domain expertise for comprehensive test case generation.'
                }

        for project in Project.query.all():
            # Get domain expertise for this project
            domain_data = get_domain_expertise_for_project(project.name)

            # Create a few test runs for each project
            test_runs = [
                {
                    'id': str(uuid.uuid4()),
                    'project_id': project.id,
                    'user_id': admin_user_id,
                    'name': f'Initial Requirements Analysis - {project.name}',
                    'status': 'passed',
                    'type': 'bdd',
                    'started_at': now - timedelta(days=30),
                    'completed_at': now - timedelta(days=29),
                    'total_tests': 10,
                    'passed_tests': 8,
                    'failed_tests': 1,
                    'skipped_tests': 1,
                    'total_scenarios': 15,
                    'passed_scenarios': 12,
                    'failed_scenarios': 2,
                    'pending_scenarios': 1,
                    'meta_data': {
                        'hasAnalysis': True,
                        'hasBddFeatures': True,
                        'hasManualTestCases': True,
                        'hasDomainExpertise': True,
                        **domain_data  # Include domain expertise data
                    }
                },
                {
                    'id': str(uuid.uuid4()),
                    'project_id': project.id,
                    'user_id': admin_user_id,
                    'name': f'Sprint 1 Regression - {project.name}',
                    'status': 'passed',
                    'type': 'selenium',
                    'started_at': now - timedelta(days=15),
                    'completed_at': now - timedelta(days=14),
                    'total_tests': 15,
                    'passed_tests': 13,
                    'failed_tests': 2,
                    'skipped_tests': 0,
                    'total_scenarios': 0,
                    'passed_scenarios': 0,
                    'failed_scenarios': 0,
                    'pending_scenarios': 0,
                    'meta_data': {
                        'hasAnalysis': False,
                        'hasBddFeatures': False,
                        'hasManualTestCases': False,
                        'hasDomainExpertise': False
                    }
                },
                {
                    'id': str(uuid.uuid4()),
                    'project_id': project.id,
                    'user_id': admin_user_id,
                    'name': f'Sprint 2 Features - {project.name}',
                    'status': 'running',
                    'type': 'bdd',
                    'started_at': now - timedelta(hours=2),
                    'completed_at': None,
                    'total_tests': 8,
                    'passed_tests': 3,
                    'failed_tests': 1,
                    'skipped_tests': 4,
                    'total_scenarios': 12,
                    'passed_scenarios': 5,
                    'failed_scenarios': 2,
                    'pending_scenarios': 5,
                    'meta_data': {
                        'hasAnalysis': True,
                        'hasBddFeatures': True,
                        'hasManualTestCases': True,
                        'hasDomainExpertise': True,
                        **domain_data  # Include domain expertise data
                    }
                }
            ]

            # Add test runs to the database
            for test_run_data in test_runs:
                test_run = TestRun(**test_run_data)
                db.session.add(test_run)

        # Commit the changes
        db.session.commit()

        # Create test management structures
        create_test_management_structures(admin_user_id)

        print("Sample data created successfully.")

def create_test_management_structures(admin_user_id):
    """Create sample test management structures (phases, plans, packages)."""
    print("Creating test management structures...")

    for project in Project.query.all():
        # Create test phases for each project
        phases = [
            {
                'id': str(uuid.uuid4()),
                'project_id': project.id,
                'name': 'Requirements Analysis Phase',
                'description': 'Initial analysis and BDD scenario generation',
                'status': 'completed',
                'start_date': datetime.now() - timedelta(days=45),
                'end_date': datetime.now() - timedelta(days=30)
            },
            {
                'id': str(uuid.uuid4()),
                'project_id': project.id,
                'name': 'Development Testing Phase',
                'description': 'Unit and integration testing during development',
                'status': 'in_progress',
                'start_date': datetime.now() - timedelta(days=30),
                'end_date': datetime.now() + timedelta(days=15)
            },
            {
                'id': str(uuid.uuid4()),
                'project_id': project.id,
                'name': 'System Testing Phase',
                'description': 'End-to-end system testing and validation',
                'status': 'planned',
                'start_date': datetime.now() + timedelta(days=15),
                'end_date': datetime.now() + timedelta(days=45)
            }
        ]

        # Add phases to database
        for phase_data in phases:
            phase = TestPhase(**phase_data)
            db.session.add(phase)

        db.session.commit()

        # Create test plans and packages for each phase
        for phase in TestPhase.query.filter_by(project_id=project.id).all():
            # Create test plans
            plans = [
                {
                    'id': str(uuid.uuid4()),
                    'test_phase_id': phase.id,
                    'name': f'{phase.name} - Functional Tests',
                    'description': 'Functional testing plan',
                    'status': 'active' if phase.status == 'in_progress' else 'draft'
                },
                {
                    'id': str(uuid.uuid4()),
                    'test_phase_id': phase.id,
                    'name': f'{phase.name} - Security Tests',
                    'description': 'Security testing plan',
                    'status': 'active' if phase.status == 'in_progress' else 'draft'
                }
            ]

            # Create test packages
            packages = [
                {
                    'id': str(uuid.uuid4()),
                    'test_phase_id': phase.id,
                    'name': f'{phase.name} - Smoke Tests',
                    'description': 'Smoke testing package',
                    'status': 'active' if phase.status == 'in_progress' else 'draft'
                },
                {
                    'id': str(uuid.uuid4()),
                    'test_phase_id': phase.id,
                    'name': f'{phase.name} - Regression Tests',
                    'description': 'Regression testing package',
                    'status': 'active' if phase.status == 'in_progress' else 'draft'
                }
            ]

            # Add plans and packages to database
            for plan_data in plans:
                plan = TestPlan(**plan_data)
                db.session.add(plan)

            for package_data in packages:
                package = TestPackage(**package_data)
                db.session.add(package)

    db.session.commit()
    print("Test management structures created successfully.")

def migrate_virtual_testing_tables():
    """Create virtual testing tables if they don't exist."""
    try:
        inspector = inspect(db.engine)

        # Determine database type
        db_url = app.config['SQLALCHEMY_DATABASE_URI']
        is_postgres = db_url.startswith('postgresql')

        # Check if virtual_test_executions table exists
        if 'virtual_test_executions' not in inspector.get_table_names():
            print("🔧 Creating virtual_test_executions table...")

            if is_postgres:
                db.session.execute(text("""
                    CREATE TABLE virtual_test_executions (
                        id VARCHAR(36) PRIMARY KEY,
                        test_run_id VARCHAR(36) REFERENCES test_runs(id),
                        user_id VARCHAR(36) NOT NULL REFERENCES users(id),
                        project_id VARCHAR(36) REFERENCES projects(id),
                        test_name VARCHAR(255) NOT NULL,
                        test_description TEXT NOT NULL,
                        target_url VARCHAR(500),
                        target_type VARCHAR(20) DEFAULT 'web',
                        status VARCHAR(20) DEFAULT 'pending',
                        total_turns INTEGER DEFAULT 0,
                        max_turns INTEGER DEFAULT 15,
                        timeout_seconds INTEGER DEFAULT 300,
                        headless BOOLEAN DEFAULT FALSE,
                        start_time TIMESTAMP,
                        end_time TIMESTAMP,
                        duration_seconds FLOAT,
                        final_output TEXT,
                        error_message TEXT,
                        test_actions JSONB,
                        screenshots_path VARCHAR(500),
                        report_path VARCHAR(500),
                        execution_log TEXT,
                        gemini_model VARCHAR(100) DEFAULT 'gemini-2.5-computer-use-preview-10-2025',
                        parent_execution_id VARCHAR(36) REFERENCES virtual_test_executions(id),
                        version_number INTEGER DEFAULT 1,
                        is_replay BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            else:
                db.session.execute(text("""
                    CREATE TABLE virtual_test_executions (
                        id VARCHAR(36) PRIMARY KEY,
                        test_run_id VARCHAR(36),
                        user_id VARCHAR(36) NOT NULL,
                        project_id VARCHAR(36),
                        test_name VARCHAR(255) NOT NULL,
                        test_description TEXT NOT NULL,
                        target_url VARCHAR(500),
                        target_type VARCHAR(20) DEFAULT 'web',
                        status VARCHAR(20) DEFAULT 'pending',
                        total_turns INTEGER DEFAULT 0,
                        max_turns INTEGER DEFAULT 15,
                        timeout_seconds INTEGER DEFAULT 300,
                        headless BOOLEAN DEFAULT 0,
                        start_time TIMESTAMP,
                        end_time TIMESTAMP,
                        duration_seconds REAL,
                        final_output TEXT,
                        error_message TEXT,
                        test_actions TEXT,
                        screenshots_path VARCHAR(500),
                        report_path VARCHAR(500),
                        execution_log TEXT,
                        gemini_model VARCHAR(100) DEFAULT 'gemini-2.5-computer-use-preview-10-2025',
                        parent_execution_id VARCHAR(36),
                        version_number INTEGER DEFAULT 1,
                        is_replay BOOLEAN DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (test_run_id) REFERENCES test_runs(id),
                        FOREIGN KEY (user_id) REFERENCES users(id),
                        FOREIGN KEY (project_id) REFERENCES projects(id),
                        FOREIGN KEY (parent_execution_id) REFERENCES virtual_test_executions(id)
                    )
                """))

            db.session.commit()
            print("✅ virtual_test_executions table created successfully!")
        else:
            print("✅ virtual_test_executions table already exists.")

            # Check if replay columns exist, add them if missing
            print("🔧 Checking for replay functionality columns...")
            columns = [col['name'] for col in inspector.get_columns('virtual_test_executions')]

            if 'parent_execution_id' not in columns:
                print("🔧 Adding parent_execution_id column...")
                if is_postgres:
                    db.session.execute(text("""
                        ALTER TABLE virtual_test_executions
                        ADD COLUMN parent_execution_id VARCHAR(36) REFERENCES virtual_test_executions(id)
                    """))
                else:
                    db.session.execute(text("""
                        ALTER TABLE virtual_test_executions
                        ADD COLUMN parent_execution_id VARCHAR(36)
                    """))
                db.session.commit()
                print("✅ parent_execution_id column added!")

            if 'version_number' not in columns:
                print("🔧 Adding version_number column...")
                db.session.execute(text("""
                    ALTER TABLE virtual_test_executions
                    ADD COLUMN version_number INTEGER DEFAULT 1
                """))
                db.session.commit()
                print("✅ version_number column added!")

            if 'is_replay' not in columns:
                print("🔧 Adding is_replay column...")
                if is_postgres:
                    db.session.execute(text("""
                        ALTER TABLE virtual_test_executions
                        ADD COLUMN is_replay BOOLEAN DEFAULT FALSE
                    """))
                else:
                    db.session.execute(text("""
                        ALTER TABLE virtual_test_executions
                        ADD COLUMN is_replay BOOLEAN DEFAULT 0
                    """))
                db.session.commit()
                print("✅ is_replay column added!")

            print("✅ Replay functionality columns verified!")

        # Check if generated_bdd_scenarios table exists
        if 'generated_bdd_scenarios' not in inspector.get_table_names():
            print("🔧 Creating generated_bdd_scenarios table...")

            json_type = 'JSONB' if is_postgres else 'TEXT'
            db.session.execute(text(f"""
                CREATE TABLE generated_bdd_scenarios (
                    id VARCHAR(36) PRIMARY KEY,
                    execution_id VARCHAR(36) NOT NULL,
                    user_id VARCHAR(36) NOT NULL,
                    feature_name VARCHAR(255) NOT NULL,
                    scenario_name VARCHAR(255) NOT NULL,
                    description TEXT,
                    tags {json_type},
                    gherkin_content TEXT NOT NULL,
                    file_path VARCHAR(500),
                    model VARCHAR(100) DEFAULT 'gpt-5',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (execution_id) REFERENCES virtual_test_executions(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """))
            db.session.commit()
            print("✅ generated_bdd_scenarios table created successfully!")
        else:
            print("✅ generated_bdd_scenarios table already exists.")

        # Check if generated_manual_tests table exists
        if 'generated_manual_tests' not in inspector.get_table_names():
            print("🔧 Creating generated_manual_tests table...")

            json_type = 'JSONB' if is_postgres else 'TEXT'
            db.session.execute(text(f"""
                CREATE TABLE generated_manual_tests (
                    id VARCHAR(36) PRIMARY KEY,
                    execution_id VARCHAR(36) NOT NULL,
                    user_id VARCHAR(36) NOT NULL,
                    test_id VARCHAR(100) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    objective TEXT,
                    priority VARCHAR(20),
                    severity VARCHAR(20),
                    test_type VARCHAR(50),
                    markdown_content TEXT NOT NULL,
                    json_content {json_type},
                    markdown_file_path VARCHAR(500),
                    json_file_path VARCHAR(500),
                    model VARCHAR(100) DEFAULT 'gpt-5',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (execution_id) REFERENCES virtual_test_executions(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """))
            db.session.commit()
            print("✅ generated_manual_tests table created successfully!")
        else:
            print("✅ generated_manual_tests table already exists.")

        # Check if generated_automation_tests table exists
        if 'generated_automation_tests' not in inspector.get_table_names():
            print("🔧 Creating generated_automation_tests table...")

            json_type = 'JSONB' if is_postgres else 'TEXT'
            db.session.execute(text(f"""
                CREATE TABLE generated_automation_tests (
                    id VARCHAR(36) PRIMARY KEY,
                    execution_id VARCHAR(36) NOT NULL,
                    user_id VARCHAR(36) NOT NULL,
                    test_id VARCHAR(100) NOT NULL,
                    test_name VARCHAR(255) NOT NULL,
                    description TEXT,
                    framework VARCHAR(50) NOT NULL,
                    language VARCHAR(50) NOT NULL,
                    pattern VARCHAR(50),
                    test_code TEXT NOT NULL,
                    dependencies {json_type},
                    tags {json_type},
                    priority VARCHAR(20),
                    usage_instructions TEXT,
                    output_path VARCHAR(500),
                    files {json_type},
                    model VARCHAR(100) DEFAULT 'gpt-5',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (execution_id) REFERENCES virtual_test_executions(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """))
            db.session.commit()
            print("✅ generated_automation_tests table created successfully!")
        else:
            print("✅ generated_automation_tests table already exists.")

        # Check if test_execution_comparisons table exists
        if 'test_execution_comparisons' not in inspector.get_table_names():
            print("🔧 Creating test_execution_comparisons table...")

            json_type = 'JSONB' if is_postgres else 'TEXT'
            db.session.execute(text(f"""
                CREATE TABLE test_execution_comparisons (
                    id VARCHAR(36) PRIMARY KEY,
                    baseline_execution_id VARCHAR(36) NOT NULL,
                    compared_execution_id VARCHAR(36) NOT NULL,
                    user_id VARCHAR(36) NOT NULL,
                    comparison_type VARCHAR(50) DEFAULT 'version_comparison',
                    ai_model VARCHAR(100),
                    summary TEXT,
                    regressions {json_type},
                    enhancements {json_type},
                    neutral_changes {json_type},
                    screenshot_differences {json_type},
                    step_differences {json_type},
                    performance_comparison {json_type},
                    overall_status VARCHAR(50),
                    regression_count INTEGER DEFAULT 0,
                    enhancement_count INTEGER DEFAULT 0,
                    neutral_count INTEGER DEFAULT 0,
                    recommendations {json_type},
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (baseline_execution_id) REFERENCES virtual_test_executions(id),
                    FOREIGN KEY (compared_execution_id) REFERENCES virtual_test_executions(id),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """))
            db.session.commit()
            print("✅ test_execution_comparisons table created successfully!")
        else:
            print("✅ test_execution_comparisons table already exists.")

        return True

    except Exception as e:
        print(f"❌ Error creating virtual testing tables: {e}")
        db.session.rollback()
        return False

def migrate_sdd_reviews_table():
    """Create sdd_reviews table if it doesn't exist, or add missing columns."""
    try:
        inspector = inspect(db.engine)

        # Check if the table already exists
        if 'sdd_reviews' in inspector.get_table_names():
            print("🔧 sdd_reviews table exists, checking for missing columns...")

            # Get existing columns
            existing_columns = [col['name'] for col in inspector.get_columns('sdd_reviews')]

            # Define all required columns
            required_columns = [
                'id', 'project_id', 'user_id', 'document_name', 'original_file_name',
                'overall_score', 'executive_summary', 'pain_points', 'good_points',
                'enhancements', 'architecture_analysis', 'missing_sections',
                'recommendations', 'chunks_analyzed', 'analyzed_at', 'created_at', 'updated_at'
            ]

            # Find missing columns
            missing_columns = [col for col in required_columns if col not in existing_columns]

            if missing_columns:
                print(f"🔧 Adding missing columns: {missing_columns}")

                # Determine database type
                db_url = os.environ.get('DATABASE_URL', 'postgresql://qaverse_user:qaverse_password@127.0.0.1:5432/qaverse_dev')
                is_sqlite = db_url.startswith('sqlite')

                # Add missing columns
                for col in missing_columns:
                    try:
                        if col == 'executive_summary':
                            db.session.execute(text(f"ALTER TABLE sdd_reviews ADD COLUMN {col} TEXT"))
                        elif col in ['pain_points', 'good_points', 'enhancements', 'architecture_analysis', 'missing_sections', 'recommendations']:
                            if is_sqlite:
                                db.session.execute(text(f"ALTER TABLE sdd_reviews ADD COLUMN {col} TEXT"))
                            else:
                                db.session.execute(text(f"ALTER TABLE sdd_reviews ADD COLUMN {col} JSONB"))
                        elif col == 'overall_score':
                            db.session.execute(text(f"ALTER TABLE sdd_reviews ADD COLUMN {col} REAL NOT NULL DEFAULT 0"))
                        elif col == 'chunks_analyzed':
                            db.session.execute(text(f"ALTER TABLE sdd_reviews ADD COLUMN {col} INTEGER DEFAULT 1"))
                        elif col in ['analyzed_at', 'created_at', 'updated_at']:
                            db.session.execute(text(f"ALTER TABLE sdd_reviews ADD COLUMN {col} TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                        elif col in ['document_name', 'original_file_name']:
                            db.session.execute(text(f"ALTER TABLE sdd_reviews ADD COLUMN {col} VARCHAR(255) NOT NULL DEFAULT ''"))
                        elif col in ['project_id', 'user_id', 'id']:
                            db.session.execute(text(f"ALTER TABLE sdd_reviews ADD COLUMN {col} VARCHAR(36) NOT NULL DEFAULT ''"))

                        print(f"✅ Added column: {col}")
                    except Exception as e:
                        if "already exists" not in str(e) and "duplicate column" not in str(e):
                            print(f"❌ Error adding column {col}: {e}")

                db.session.commit()
                print("✅ Missing columns added successfully.")
            else:
                print("✅ All required columns already exist.")

            return True

        print("🔧 Creating sdd_reviews table...")

        # Determine if we're using SQLite or PostgreSQL
        db_url = os.environ.get('DATABASE_URL', 'postgresql://qaverse_user:qaverse_password@127.0.0.1:5432/qaverse_dev')
        is_sqlite = db_url.startswith('sqlite')

        # Create the table
        if is_sqlite:
            # SQLite syntax
            db.session.execute(text("""
                CREATE TABLE sdd_reviews (
                    id VARCHAR(36) PRIMARY KEY,
                    project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
                    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
                    document_name VARCHAR(255) NOT NULL,
                    original_file_name VARCHAR(255) NOT NULL,
                    overall_score REAL NOT NULL,
                    executive_summary TEXT,
                    pain_points TEXT,
                    good_points TEXT,
                    enhancements TEXT,
                    architecture_analysis TEXT,
                    missing_sections TEXT,
                    recommendations TEXT,
                    chunks_analyzed INTEGER DEFAULT 1,
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
        else:
            # PostgreSQL syntax
            db.session.execute(text("""
                CREATE TABLE sdd_reviews (
                    id VARCHAR(36) PRIMARY KEY,
                    project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
                    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
                    document_name VARCHAR(255) NOT NULL,
                    original_file_name VARCHAR(255) NOT NULL,
                    overall_score REAL NOT NULL,
                    executive_summary TEXT,
                    pain_points JSONB,
                    good_points JSONB,
                    enhancements JSONB,
                    architecture_analysis JSONB,
                    missing_sections JSONB,
                    recommendations JSONB,
                    chunks_analyzed INTEGER DEFAULT 1,
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

        db.session.commit()
        print("✅ sdd_reviews table created successfully.")
        return True

    except Exception as e:
        print(f"❌ Error creating sdd_reviews table: {e}")
        db.session.rollback()
        return False


def migrate_sdd_enhancements_table():
    """Create sdd_enhancements table if it doesn't exist."""
    try:
        inspector = inspect(db.engine)

        # Check if the table already exists
        if 'sdd_enhancements' in inspector.get_table_names():
            print("✅ sdd_enhancements table already exists.")
            return True

        print("🔧 Creating sdd_enhancements table...")

        # Determine database type
        db_url = os.environ.get('DATABASE_URL', 'postgresql://qaverse_user:qaverse_password@127.0.0.1:5432/qaverse_dev')
        is_sqlite = db_url.startswith('sqlite')

        # Create the table
        if is_sqlite:
            # SQLite syntax
            db.session.execute(text("""
                CREATE TABLE sdd_enhancements (
                    id VARCHAR(36) PRIMARY KEY,
                    project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
                    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
                    sdd_review_id VARCHAR(36) REFERENCES sdd_reviews(id),
                    original_document_name VARCHAR(255) NOT NULL,
                    enhanced_content TEXT NOT NULL,
                    improvements_made TEXT,
                    enhancement_summary TEXT,
                    sections_added TEXT,
                    sections_improved TEXT,
                    chunks_processed INTEGER DEFAULT 1,
                    enhanced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
        else:
            # PostgreSQL syntax
            db.session.execute(text("""
                CREATE TABLE sdd_enhancements (
                    id VARCHAR(36) PRIMARY KEY,
                    project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
                    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
                    sdd_review_id VARCHAR(36) REFERENCES sdd_reviews(id),
                    original_document_name VARCHAR(255) NOT NULL,
                    enhanced_content TEXT NOT NULL,
                    improvements_made JSONB,
                    enhancement_summary TEXT,
                    sections_added JSONB,
                    sections_improved JSONB,
                    chunks_processed INTEGER DEFAULT 1,
                    enhanced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

        db.session.commit()
        print("✅ sdd_enhancements table created successfully.")
        return True

    except Exception as e:
        print(f"❌ Error creating sdd_enhancements table: {e}")
        db.session.rollback()
        return False


def fix_sdd_enhancements_nullable_constraint():
    """Fix the sdd_review_id column to be nullable in sdd_enhancements table."""
    try:
        inspector = inspect(db.engine)

        # Check if the table exists
        if 'sdd_enhancements' not in inspector.get_table_names():
            print("❌ sdd_enhancements table does not exist")
            return False

        print("🔧 Fixing sdd_review_id nullable constraint in sdd_enhancements table...")

        # Determine database type
        db_url = os.environ.get('DATABASE_URL', 'postgresql://qaverse_user:qaverse_password@127.0.0.1:5432/qaverse_dev')
        is_sqlite = db_url.startswith('sqlite')

        if is_sqlite:
            # SQLite doesn't support ALTER COLUMN, so we need to recreate the table
            print("🔧 SQLite detected - recreating table with nullable constraint...")
            # For SQLite, we would need to recreate the table, but for now let's just handle PostgreSQL
            pass
        else:
            # PostgreSQL syntax to make column nullable
            db.session.execute(text("ALTER TABLE sdd_enhancements ALTER COLUMN sdd_review_id DROP NOT NULL"))

        db.session.commit()
        print("✅ sdd_review_id column is now nullable in sdd_enhancements table.")
        return True

    except Exception as e:
        print(f"❌ Error fixing sdd_enhancements nullable constraint: {e}")
        db.session.rollback()
        return False


def migrate_test_management_unique_constraints():
    """Add unique constraints for test management entities to prevent duplicate names."""
    try:
        print("🔧 Adding unique constraints for test management entities...")

        # Check if constraints already exist by trying to create them
        constraints = [
            {
                'table': 'test_phases',
                'constraint': 'uq_test_phase_project_name',
                'columns': '(project_id, name)',
                'description': 'test phase names per project'
            },
            {
                'table': 'test_plans',
                'constraint': 'uq_test_plan_phase_name',
                'columns': '(test_phase_id, name)',
                'description': 'test plan names per phase'
            },
            {
                'table': 'test_packages',
                'constraint': 'uq_test_package_phase_name',
                'columns': '(test_phase_id, name)',
                'description': 'test package names per phase'
            }
        ]

        for constraint_info in constraints:
            try:
                # Check if table exists first
                inspector = inspect(db.engine)
                if constraint_info['table'] not in inspector.get_table_names():
                    print(f"⚠️  Table '{constraint_info['table']}' does not exist, skipping constraint...")
                    continue

                # Try to add the constraint
                sql = f"ALTER TABLE {constraint_info['table']} ADD CONSTRAINT {constraint_info['constraint']} UNIQUE {constraint_info['columns']}"
                db.session.execute(text(sql))
                db.session.commit()
                print(f"✅ Added unique constraint for {constraint_info['description']}")

            except Exception as constraint_error:
                # If constraint already exists or there's a conflict, that's okay
                if "already exists" in str(constraint_error).lower() or "duplicate" in str(constraint_error).lower():
                    print(f"✅ Unique constraint for {constraint_info['description']} already exists")
                    db.session.rollback()
                else:
                    print(f"⚠️  Could not add constraint for {constraint_info['description']}: {constraint_error}")
                    db.session.rollback()

    except Exception as e:
        print(f"❌ Error in unique constraints migration: {e}")
        db.session.rollback()


def migrate_project_unit_tests_table():
    """Create project_unit_tests table if it doesn't exist."""
    try:
        inspector = inspect(db.engine)

        # Check if the table already exists
        if 'project_unit_tests' in inspector.get_table_names():
            print("✅ project_unit_tests table already exists.")
            return True

        print("🔧 Creating project_unit_tests table...")

        # Determine database type
        db_url = app.config['SQLALCHEMY_DATABASE_URI']
        is_postgres = db_url.startswith('postgresql')
        json_type = 'JSONB' if is_postgres else 'TEXT'

        # Create the table
        db.session.execute(text(f"""
            CREATE TABLE project_unit_tests (
                id VARCHAR(36) PRIMARY KEY,
                project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
                user_id VARCHAR(36) NOT NULL REFERENCES users(id),
                original_file_name VARCHAR(255) NOT NULL,
                test_file_name VARCHAR(255) NOT NULL,
                full_code TEXT NOT NULL,
                language VARCHAR(50),
                testing_framework VARCHAR(100),
                analysis_data {json_type},
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        db.session.commit()
        print("✅ project_unit_tests table created successfully.")
        return True

    except Exception as e:
        print(f"❌ Error creating project_unit_tests table: {e}")
        db.session.rollback()
        return False


def migrate_workflow_tables():
    """Create workflow system tables if they don't exist."""
    try:
        inspector = inspect(db.engine)

        # Determine database type
        db_url = app.config['SQLALCHEMY_DATABASE_URI']
        is_postgres = db_url.startswith('postgresql')
        json_type = 'JSONB' if is_postgres else 'TEXT'

        # Check if workflows table exists
        if 'workflows' not in inspector.get_table_names():
            print("🔧 Creating workflows table...")

            db.session.execute(text(f"""
                CREATE TABLE workflows (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
                    project_id VARCHAR(36) REFERENCES projects(id),
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    workflow_data {json_type} NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            db.session.commit()
            print("✅ workflows table created successfully!")
        else:
            print("✅ workflows table already exists.")

        # Check if workflow_executions table exists
        if 'workflow_executions' not in inspector.get_table_names():
            print("🔧 Creating workflow_executions table...")

            db.session.execute(text(f"""
                CREATE TABLE workflow_executions (
                    id VARCHAR(36) PRIMARY KEY,
                    workflow_id VARCHAR(36) NOT NULL,
                    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
                    status VARCHAR(50) DEFAULT 'pending',
                    input_data {json_type},
                    execution_data {json_type},
                    error_message TEXT,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
                )
            """))
            db.session.commit()
            print("✅ workflow_executions table created successfully!")
        else:
            print("✅ workflow_executions table already exists.")

        # Check if workflow_node_executions table exists
        if 'workflow_node_executions' not in inspector.get_table_names():
            print("🔧 Creating workflow_node_executions table...")

            db.session.execute(text(f"""
                CREATE TABLE workflow_node_executions (
                    id VARCHAR(36) PRIMARY KEY,
                    execution_id VARCHAR(36) NOT NULL,
                    node_id VARCHAR(255) NOT NULL,
                    node_type VARCHAR(100) NOT NULL,
                    status VARCHAR(50) DEFAULT 'pending',
                    input_data {json_type},
                    output_data {json_type},
                    error_message TEXT,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (execution_id) REFERENCES workflow_executions(id) ON DELETE CASCADE
                )
            """))
            db.session.commit()
            print("✅ workflow_node_executions table created successfully!")
        else:
            print("✅ workflow_node_executions table already exists.")
    except Exception as e:
        print(f"❌ Error creating project_unit_tests table: {e}")
        db.session.rollback()
        return False

def migrate_project_archive_columns():
    """Add archived_at, archive_reason, and last_activity_at columns to projects table if they don't exist."""
    try:
        columns_to_add = [
            ('archived_at', 'TIMESTAMP', 'archived_at column'),
            ('archive_reason', 'TEXT', 'archive_reason column'),
            ('last_activity_at', 'TIMESTAMP', 'last_activity_at column')
        ]

        # Determine the database type
        db_url = app.config['SQLALCHEMY_DATABASE_URI']
        is_sqlite = db_url.startswith('sqlite')

        for column_name, column_type, description in columns_to_add:
            # Check if the column already exists
            if check_column_exists('projects', column_name):
                print(f"✅ {description} already exists in projects table.")
                continue

            print(f"🔧 Adding {description} to projects table...")

            # Add the column
            if is_sqlite:
                # SQLite syntax
                if column_type == 'TIMESTAMP':
                    db.session.execute(text(f"ALTER TABLE projects ADD COLUMN {column_name} DATETIME"))
                else:
                    db.session.execute(text(f"ALTER TABLE projects ADD COLUMN {column_name} {column_type}"))
            else:
                # PostgreSQL or MySQL
                db.session.execute(text(f"ALTER TABLE projects ADD COLUMN {column_name} {column_type}"))

            db.session.commit()
            print(f"✅ {description} added to projects table successfully!")


        return True

    except Exception as e:

        print(f"❌ Error creating workflow tables: {e}")
        db.session.rollback()
        return False



        print(f"❌ Error adding project archive columns: {e}")
        db.session.rollback()
        return False


def run_all_migrations():
    """Run all database migrations without creating sample data."""
    print("🔧 Running all QAVerse database migrations...")
    print("=" * 50)

    with app.app_context():
        try:
            # Create all tables first
            db.create_all()
            print("✅ Database tables created/verified")

            # Run all migrations
            print("\n🔧 Running schema migrations...")
            remove_username_constraint()
            add_project_user_id()
            add_organization_id_to_users()
            migrate_ai_model_preference_column()
            migrate_bdd_scenarios_examples_data()
            migrate_bdd_features_content()
            migrate_bdd_steps_element_metadata()
            migrate_user_roles_content()
            migrate_document_analysis_content()
            migrate_bdd_scenario_name_length()
            migrate_test_run_user_id()
            migrate_test_management_cascade_deletes()
            migrate_test_cases_category_length()
            migrate_uploaded_code_files_table()
            migrate_user_preferences_table()
            migrate_users_email_verification()
            migrate_users_test_runs_passed()
            migrate_users_test_runs_limit()
            migrate_selenium_tests_schema()
            migrate_sdd_reviews_table()
            migrate_sdd_enhancements_table()
            migrate_project_unit_tests_table()
            migrate_virtual_testing_tables()
            migrate_workflow_tables()
            migrate_test_management_unique_constraints()
            migrate_project_archive_columns()

            print("\n✅ All database migrations completed successfully!")
            print("🎉 Database schema is now up-to-date for production deployment")

        except Exception as e:
            print(f"\n❌ Migration failed: {e}")
            import traceback
            traceback.print_exc()
            raise

def initialize_database_with_ai_models():
    """Initialize database with AI model support for production deployment."""
    print("🚀 Initializing QAVerse database with AI model selection support...")
    print("=" * 60)

    with app.app_context():
        try:
            # Create all tables
            db.create_all()
            print("✅ Database tables created")

            # Run all database migrations to ensure schema is up-to-date
            print("🔧 Running database migrations...")
            remove_username_constraint()
            add_project_user_id()
            add_organization_id_to_users()
            migrate_ai_model_preference_column()
            migrate_bdd_scenarios_examples_data()
            migrate_bdd_features_content()
            migrate_bdd_steps_element_metadata()
            migrate_user_roles_content()
            migrate_document_analysis_content()
            migrate_bdd_scenario_name_length()
            migrate_test_run_user_id()
            migrate_test_management_cascade_deletes()
            migrate_test_cases_category_length()
            migrate_uploaded_code_files_table()
            migrate_user_preferences_table()
            migrate_users_email_verification()
            migrate_users_test_runs_passed()
            migrate_users_test_runs_limit()
            migrate_selenium_tests_schema()
            migrate_sdd_reviews_table()
            migrate_sdd_enhancements_table()
            migrate_project_unit_tests_table()
            migrate_virtual_testing_tables()
            migrate_workflow_tables()
            migrate_test_management_unique_constraints()
            migrate_test_management_unique_constraints()
            migrate_project_archive_columns()
            print("✅ Database migrations completed")

            # Create default users with AI model preferences
            admin_id = create_default_users()

            # Create sample data if needed
            create_sample_data()

            # Create test management structures
            create_test_management_structures(admin_id)

            print("\n" + "=" * 60)
            print("🎉 Database initialization completed successfully!")
            print("✅ AI model selection feature is ready for production")
            print("\nDefault users created:")
            print("  - admin@qaverse.com (password: admin)")
            print("  - miriam.dahmoun@gmail.com (password: password123)")
            print("\nBoth users have default AI model preference set to 'gpt-5'")

        except Exception as e:
            print(f"\n❌ Database initialization failed: {e}")
            import traceback
            traceback.print_exc()
            raise

if __name__ == '__main__':
    # Check command line arguments for different modes
    import sys

    if len(sys.argv) > 1:
        mode = sys.argv[1]

        if mode == '--full-init':
            # Full initialization with sample data
            initialize_database_with_ai_models()
        elif mode == '--migrate-only':
            # Run migrations only (for production updates)
            run_all_migrations()
        elif mode == '--sample-data':
            # Create sample data only
            create_sample_data()
        else:
            print("Usage:")
            print("  python init_db.py --full-init     # Full initialization with sample data")
            print("  python init_db.py --migrate-only  # Run migrations only (production)")
            print("  python init_db.py --sample-data   # Create sample data only")
            print("  python init_db.py                 # Default: create sample data")
            sys.exit(1)
    else:
        # Default: create sample data
        create_sample_data()
