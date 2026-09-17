from logging.config import fileConfig

from alembic import context

import app.models  # noqa: F401  (registers tables)
from app.config import Settings
from app.db import Base, make_engine

config = context.config
if config.config_file_name and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name)

url = config.get_main_option("sqlalchemy.url") or Settings().database_url
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
