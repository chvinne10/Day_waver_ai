"""Persist custom OpenAI-compatible API endpoint and auth settings."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision="0004_custom_provider_endpoints"
down_revision="0003_cloud_ai_settings"
branch_labels=None
depends_on=None

def upgrade():
    columns={column["name"] for column in inspect(op.get_bind()).get_columns("user_cloud_ai_settings")}
    for name,default in (("model_list_path","/models"),("chat_completion_path","/chat/completions"),("auth_header","Authorization"),("auth_scheme","Bearer")):
        if name not in columns:
            op.add_column("user_cloud_ai_settings",sa.Column(name,sa.Text(),nullable=False,server_default=default))

def downgrade():
    # Preserve settings when rolling back an application deployment.
    pass
