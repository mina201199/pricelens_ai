from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from price_lens.ai.text2sql.validator import ValidatedQuery


class Text2SqlExecutionError(RuntimeError):
    pass


class QueryCostExceededError(Text2SqlExecutionError):
    pass


@dataclass(frozen=True)
class QueryResult:
    rows: list[dict[str, Any]]
    total_cost: float


class Text2SqlExecutor:
    def __init__(
        self,
        database_url: str,
        *,
        statement_timeout_ms: int,
        lock_timeout_ms: int,
        max_explain_cost: float,
        engine: Engine | None = None,
    ) -> None:
        self.engine = engine or create_engine(
            database_url,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=0,
        )
        self.statement_timeout_ms = statement_timeout_ms
        self.lock_timeout_ms = lock_timeout_ms
        self.max_explain_cost = max_explain_cost

    def execute(self, query: ValidatedQuery) -> QueryResult:
        try:
            with self.engine.connect() as connection, connection.begin():
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                connection.exec_driver_sql(
                    f"SET LOCAL statement_timeout = {self.statement_timeout_ms}"
                )
                connection.exec_driver_sql(
                    f"SET LOCAL lock_timeout = {self.lock_timeout_ms}"
                )
                plan = connection.exec_driver_sql(
                    f"EXPLAIN (FORMAT JSON) {query.sql}"
                ).scalar_one()
                total_cost = float(plan[0]["Plan"]["Total Cost"])
                if total_cost > self.max_explain_cost:
                    raise QueryCostExceededError("Query plan exceeds the configured cost limit")
                rows = [dict(row) for row in connection.execute(text(query.sql)).mappings()]
                return QueryResult(rows=rows, total_cost=total_cost)
        except QueryCostExceededError:
            raise
        except SQLAlchemyError as exc:
            raise Text2SqlExecutionError("Read-only analytics query failed") from exc
