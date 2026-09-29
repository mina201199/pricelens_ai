from dataclasses import dataclass

from sqlglot import exp, parse
from sqlglot.errors import ParseError

ALLOWED_VIEWS = frozenset(
    {
        "v_product_daily",
        "v_latest_product_status",
        "v_weekly_movers",
        "v_market_product_daily",
    }
)
FORBIDDEN_FUNCTIONS = frozenset(
    {
        "current_setting",
        "dblink",
        "dblink_connect",
        "exploding_generate_series",
        "generate_series",
        "lo_export",
        "lo_import",
        "pg_ls_dir",
        "pg_read_binary_file",
        "pg_read_file",
        "pg_sleep",
        "set_config",
    }
)
FORBIDDEN_NODES = (
    exp.Alter,
    exp.Command,
    exp.Copy,
    exp.Create,
    exp.Delete,
    exp.Drop,
    exp.Insert,
    exp.Into,
    exp.Merge,
    exp.Transaction,
    exp.TruncateTable,
    exp.Update,
)


class SqlValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedQuery:
    sql: str
    relations: tuple[str, ...]
    row_limit: int


class SqlValidator:
    def __init__(self, *, max_rows: int = 100, max_sql_chars: int = 5000) -> None:
        self.max_rows = max_rows
        self.max_sql_chars = max_sql_chars

    def validate(self, sql: str) -> ValidatedQuery:
        if len(sql) > self.max_sql_chars:
            raise SqlValidationError("SQL exceeds the configured length limit")
        try:
            statements = [statement for statement in parse(sql, dialect="postgres") if statement]
        except ParseError as exc:
            raise SqlValidationError("SQL could not be parsed") from exc
        if len(statements) != 1:
            raise SqlValidationError("Exactly one SQL statement is required")
        tree = statements[0]
        if not isinstance(tree, exp.Query):
            raise SqlValidationError("Only SELECT queries are allowed")
        forbidden = next((node for node in tree.walk() if isinstance(node, FORBIDDEN_NODES)), None)
        if forbidden is not None:
            raise SqlValidationError(f"Forbidden SQL operation: {forbidden.key}")

        cte_names = {cte.alias_or_name.casefold() for cte in tree.find_all(exp.CTE)}
        relations: set[str] = set()
        for table in tree.find_all(exp.Table):
            name = table.name.casefold()
            schema = table.db.casefold() if table.db else ""
            catalog = table.catalog.casefold() if table.catalog else ""
            if name in cte_names and not schema and not catalog:
                continue
            if catalog or schema not in {"", "analytics"} or name not in ALLOWED_VIEWS:
                raise SqlValidationError(f"Relation is not allowlisted: {table.sql()}")
            relations.add(name)
        if not relations:
            raise SqlValidationError("Query must read at least one allowlisted analytics view")

        for function in tree.find_all(exp.Func):
            names = {
                function.sql_name().casefold(),
                str(getattr(function, "name", "")).casefold(),
            }
            forbidden_name = next(
                (name for name in names if name in FORBIDDEN_FUNCTIONS), None
            )
            if forbidden_name:
                raise SqlValidationError(f"Function is not allowed: {forbidden_name}")

        limit = tree.args.get("limit")
        row_limit = self.max_rows
        if limit is not None:
            expression = limit.expression
            if not isinstance(expression, exp.Literal) or not expression.is_int:
                raise SqlValidationError("LIMIT must be a positive integer literal")
            requested = int(expression.this)
            if requested < 1:
                raise SqlValidationError("LIMIT must be positive")
            row_limit = min(requested, self.max_rows)
        tree = tree.limit(row_limit, copy=True)
        return ValidatedQuery(
            sql=tree.sql(dialect="postgres"),
            relations=tuple(sorted(relations)),
            row_limit=row_limit,
        )
