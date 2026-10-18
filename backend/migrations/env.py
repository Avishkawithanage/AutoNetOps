from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.db.session import Base
import app.models  # noqa: F401  (register tables)

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.",
                                     poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          render_as_batch=connection.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
