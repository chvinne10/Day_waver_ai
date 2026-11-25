"""Add durable file metadata, folders, and memory update timestamps."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision="0005_inbox_file_manager"
down_revision="0004_custom_provider_endpoints"
branch_labels=None
depends_on=None

def upgrade():
    inspector=inspect(op.get_bind());tables=set(inspector.get_table_names())
    if "updated_at" not in {col["name"] for col in inspector.get_columns("memories")}:
        op.add_column("memories",sa.Column("updated_at",sa.Text(),nullable=True))
        op.execute("UPDATE memories SET updated_at=created_at WHERE updated_at IS NULL")
    if "inbox_folders" not in tables:
        op.create_table("inbox_folders",
            sa.Column("id",sa.Text(),primary_key=True),sa.Column("user_id",sa.Text(),nullable=False),
            sa.Column("parent_id",sa.Text(),nullable=True),sa.Column("name",sa.Text(),nullable=False),
            sa.Column("created_at",sa.Text(),nullable=False),sa.Column("updated_at",sa.Text(),nullable=False))
    if "inbox_files" not in tables:
        op.create_table("inbox_files",
            sa.Column("id",sa.Text(),primary_key=True),sa.Column("user_id",sa.Text(),nullable=False),
            sa.Column("folder_id",sa.Text(),nullable=True),sa.Column("name",sa.Text(),nullable=False),
            sa.Column("original_name",sa.Text(),nullable=False),sa.Column("extension",sa.Text(),nullable=False),
            sa.Column("mime_type",sa.Text(),nullable=False),sa.Column("size_bytes",sa.BigInteger(),nullable=False),
            sa.Column("storage_key",sa.Text(),nullable=False,unique=True),sa.Column("created_at",sa.Text(),nullable=False),
            sa.Column("updated_at",sa.Text(),nullable=False))
    indexes={index["name"] for index in inspect(op.get_bind()).get_indexes("inbox_folders")}
    if "ix_inbox_folders_user_parent" not in indexes:op.create_index("ix_inbox_folders_user_parent","inbox_folders",["user_id","parent_id"])
    indexes={index["name"] for index in inspect(op.get_bind()).get_indexes("inbox_files")}
    if "ix_inbox_files_user_folder" not in indexes:op.create_index("ix_inbox_files_user_folder","inbox_files",["user_id","folder_id"])
    indexes={index["name"] for index in inspect(op.get_bind()).get_indexes("memories")}
    if "ix_memories_user_updated" not in indexes:op.create_index("ix_memories_user_updated","memories",["user_id","updated_at"])

def downgrade():
    # Keep user files and metadata intact during rollback.
    pass
