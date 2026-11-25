"""Create the Dayweave workspace schema and add ownership columns safely."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision="0001_workspace_auth"
down_revision=None
branch_labels=None
depends_on=None

TABLES=(
    "tasks","sources","memories","focus_sessions","activities"
)

def upgrade():
    statements=(
        "CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT NOT NULL UNIQUE,name TEXT NOT NULL,password_hash TEXT NOT NULL,created_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,token_hash TEXT NOT NULL UNIQUE,csrf_token TEXT NOT NULL,expires_at TEXT NOT NULL,created_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS login_attempts(id TEXT PRIMARY KEY,ip_hash TEXT NOT NULL,created_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,title TEXT NOT NULL,description TEXT DEFAULT '',status TEXT DEFAULT 'Todo',priority TEXT DEFAULT 'Medium',due_date TEXT,category TEXT DEFAULT 'Personal',source_id TEXT,created_at TEXT NOT NULL,user_id TEXT)",
        "CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,title TEXT NOT NULL,kind TEXT NOT NULL,content TEXT DEFAULT '',summary TEXT DEFAULT '',status TEXT DEFAULT 'Completed',created_at TEXT NOT NULL,user_id TEXT)",
        "CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,title TEXT NOT NULL,content TEXT NOT NULL,category TEXT DEFAULT 'Preference',source TEXT DEFAULT '',created_at TEXT NOT NULL,user_id TEXT)",
        "CREATE TABLE IF NOT EXISTS focus_sessions(id TEXT PRIMARY KEY,task_id TEXT,duration INTEGER NOT NULL,completed_at TEXT NOT NULL,user_id TEXT)",
        "CREATE TABLE IF NOT EXISTS activities(id TEXT PRIMARY KEY,kind TEXT NOT NULL,label TEXT NOT NULL,created_at TEXT NOT NULL,user_id TEXT)",
    )
    for statement in statements:op.execute(statement)
    bind=op.get_bind();inspector=inspect(bind)
    for table in TABLES:
        if "user_id" not in {col["name"] for col in inspector.get_columns(table)}:
            op.add_column(table,sa.Column("user_id",sa.Text(),nullable=True))
        op.execute(text(f"UPDATE {table} SET user_id='legacy' WHERE user_id IS NULL"))
    for name,table,columns in (("ix_tasks_user_due","tasks",["user_id","due_date"]),("ix_sources_user_created","sources",["user_id","created_at"]),("ix_sessions_token","sessions",["token_hash"])):
        if name not in {index["name"] for index in inspector.get_indexes(table)}:op.create_index(name,table,columns,unique=False)

def downgrade():
    # Intentionally non-destructive: production user data must never be dropped by rollback.
    pass
