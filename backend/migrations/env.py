from logging.config import fileConfig
import os
from alembic import context
from sqlalchemy import create_engine, pool

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)


def database_url() -> str:
    """Return a SQLAlchemy URL without exposing credentials in logs."""
    url = (os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url") or "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL must be set before running migrations.")
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


url = database_url()
# Keep Alembic's effective configuration correct for commands that inspect it.
# ConfigParser treats '%' as interpolation syntax, so escape it only in config;
# create_engine below always receives the original URL.
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
def run_migrations_offline():
    context.configure(url=url,literal_binds=True,dialect_opts={"paramstyle":"named"},compare_type=True)
    with context.begin_transaction():context.run_migrations()
def run_migrations_online():
    # Do not round-trip the URL through ConfigParser: Aiven passwords are often
    # URL-encoded and '%' then causes "Could not parse SQLAlchemy URL" here.
    connectable = create_engine(url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection,compare_type=True)
        with context.begin_transaction():context.run_migrations()
if context.is_offline_mode():run_migrations_offline()
else:run_migrations_online()
