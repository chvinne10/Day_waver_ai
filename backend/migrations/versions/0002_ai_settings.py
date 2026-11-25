"""Persist per-user AI provider settings and encrypted credentials."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
revision="0002_ai_settings"
down_revision="0001_workspace_auth"
branch_labels=None
depends_on=None
def upgrade():
    if "user_ai_settings" in inspect(op.get_bind()).get_table_names():return
    op.create_table("user_ai_settings",
        sa.Column("user_id",sa.Text(),primary_key=True),
        sa.Column("provider",sa.Text(),nullable=False),
        sa.Column("base_url",sa.Text(),nullable=False),
        sa.Column("model",sa.Text(),nullable=False),
        sa.Column("encrypted_api_key",sa.Text(),nullable=True),
        sa.Column("low_token_usage",sa.Integer(),nullable=False,server_default="1"),
        sa.Column("max_output_tokens",sa.Integer(),nullable=False,server_default="350"),
        sa.Column("context_items",sa.Integer(),nullable=False,server_default="5"),
        sa.Column("updated_at",sa.Text(),nullable=False))
def downgrade():
    # Do not drop encrypted provider configuration automatically on downgrade.
    pass
