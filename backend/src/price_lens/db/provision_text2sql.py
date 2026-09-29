import logging

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from price_lens.config import get_settings
from price_lens.logging_config import configure_logging

logger = logging.getLogger(__name__)


def provision_text2sql_login() -> None:
    settings = get_settings()
    admin = make_url(settings.database_url)
    readonly = make_url(settings.text2sql_database_url)
    if readonly.username != settings.text2sql_role_name:
        raise RuntimeError("TEXT2SQL_DATABASE_URL user must match TEXT2SQL_ROLE_NAME")
    if not readonly.password:
        raise RuntimeError("TEXT2SQL_DATABASE_URL must include a password")

    with psycopg.connect(
        host=admin.host,
        port=admin.port,
        dbname=admin.database,
        user=admin.username,
        password=admin.password,
        autocommit=True,
    ) as connection:
        connection.execute(
            sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                sql.Identifier(settings.text2sql_role_name),
                sql.Literal(readonly.password),
            )
        )
    logger.info("text2sql_login_provisioned", extra={"role": settings.text2sql_role_name})


if __name__ == "__main__":
    configure_logging(get_settings().log_level)
    provision_text2sql_login()
