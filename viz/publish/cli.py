"""The viz command line. Every subcommand is a thin function that calls one module."""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa

from .. import __version__
from ..config import Settings
from ..ids import InvalidId
from ..storage import get_storage
from .errors import CliError
from .identity import resolve_author
from .infer import UnsupportedColumn, table_from_file
from .move import MoveError, apply_move, describe, plan_move
from .pii import drop_columns, parse_drop_list, pii_warning
from .preview import run_preview
from .publish import PublishRefused, publish_chart, publish_dashboard
from .query import QueryError, read_sql_argument, resolve_warehouse, run_query
from .staging import LaneError, column_summary, write_staged_chart
from .validate import validate_dashboard_file, validate_staged_chart


def _resolve_author(settings: Settings) -> str:
    """resolve_author() can reach out to AWS (VIZ_STORAGE=s3) or the local user
    database; any failure there is an environment problem, not a crash."""
    try:
        return resolve_author(settings)
    except Exception as err:
        raise CliError(f"could not resolve the author identity: {err}", code=2) from err


def _debug_raise(args) -> int:
    """Hidden subcommand used only by tests to exercise error printing."""
    return _DEBUG_HANDLER(args)


def _no_debug(args) -> int:
    return 0


_DEBUG_HANDLER = _no_debug


def _staging_root(args, settings: Settings) -> Path:
    return Path(args.staging) if getattr(args, "staging", None) else settings.staging_dir


def _stage_table(table, chart_id: str, settings: Settings, args, *, author: str, source: dict | None = None) -> int:
    """Shared tail of `stage` and `query`: --drop-columns, PII warning, write, summary."""
    try:
        table = drop_columns(table, parse_drop_list(getattr(args, "drop_columns", None)))
    except ValueError as err:
        raise CliError(str(err), code=1) from err
    try:
        warning = pii_warning(table.column_names, settings.pii_pattern)
    except ValueError as err:
        raise CliError(str(err), code=2) from err
    if warning:
        print(warning, file=sys.stderr)
    try:
        staged = write_staged_chart(table, chart_id, _staging_root(args, settings), author=author,
                                    now=datetime.now(timezone.utc), source=source)
    except (UnsupportedColumn, LaneError, ValueError) as err:
        raise CliError(str(err), code=1) from err
    print(column_summary(table))
    print(f"staged: {staged.dir}")
    return 0


def _cmd_stage(args) -> int:
    settings = Settings()
    path = Path(args.source_path)
    if not path.is_file():
        raise CliError(f"input file not found: {path}", code=2)
    try:
        table = table_from_file(path)
    except (UnsupportedColumn, ValueError, OSError, pa.ArrowException) as err:
        raise CliError(f"could not read {path}: {err}", code=2) from err
    return _stage_table(table, args.id, settings, args, author=_resolve_author(settings))


def _validate_path(path: Path, settings: Settings, allow_row_level: bool) -> list[str]:
    storage = get_storage(settings)
    if path.is_dir():
        return validate_staged_chart(path, settings, storage, allow_row_level=allow_row_level)
    if path.is_file():
        return validate_dashboard_file(path, settings, storage)
    raise CliError(f"path not found: {path}", code=2)


def _cmd_validate(args) -> int:
    settings = Settings()
    path = Path(args.path)
    errors = _validate_path(path, settings, args.allow_row_level)
    if errors:
        raise CliError(errors, code=1)
    print(f"ok: {path}")
    return 0


def _cmd_publish(args) -> int:
    settings = Settings()
    storage = get_storage(settings)
    path = Path(args.path)
    try:
        if path.is_dir():
            publish_chart(path, settings, storage, force=args.force, allow_row_level=args.allow_row_level)
        elif path.is_file():
            publish_dashboard(path, settings, storage, force=args.force)
        else:
            raise CliError(f"path not found: {path}", code=2)
    except PublishRefused as err:
        raise CliError(err.errors, code=1) from err
    return 0


def _cmd_move(args) -> int:
    settings = Settings()
    storage = get_storage(settings)
    try:
        plan = plan_move(args.old_id, args.new_id, settings, storage)
    except (MoveError, InvalidId) as err:
        raise CliError(str(err), code=1) from err
    print(describe(plan))
    if not args.yes:
        print("dry run: pass --yes to apply", file=sys.stderr)
        return 1
    try:
        apply_move(plan, settings, storage)
    except MoveError as err:
        raise CliError(str(err), code=1) from err
    print(f"moved: {plan.old_id} -> {plan.new_id}")
    return 0


def _cmd_preview(args) -> int:
    settings = Settings()
    run_preview(_staging_root(args, settings), args.host, args.port)
    return 0


def _cmd_query(args) -> int:
    settings = Settings()
    try:
        sql = read_sql_argument(args.sql)
        table, user = run_query(sql, settings, args.warehouse)
        warehouse = resolve_warehouse(args.warehouse)
    except QueryError as err:
        raise CliError(str(err), code=err.code) from err
    source = {"kind": "databricks-sql", "sql": sql, "warehouse_id": warehouse}
    return _stage_table(table, args.id, settings, args, author=user, source=source)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="viz", description="Stage, validate and publish charts and dashboards.")
    parser.add_argument("--version", action="version", version=f"viz {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    debug = sub.add_parser("debug-raise", help=argparse.SUPPRESS)
    debug.set_defaults(func=_debug_raise)

    stage_p = sub.add_parser("stage", help="stage a csv, json or parquet file as a chart")
    stage_p.add_argument("--from", dest="source_path", required=True, metavar="PATH")
    stage_p.add_argument("--id", required=True, help="chart id, for example sales/emea/revenue")
    stage_p.add_argument("--drop-columns", default=None, metavar="a,b")
    stage_p.add_argument("--staging", default=None, metavar="DIR", help="staging directory (default ./.viz-staging)")
    stage_p.set_defaults(func=_cmd_stage)

    validate_p = sub.add_parser("validate", help="validate a staged chart directory or a dashboard file")
    validate_p.add_argument("path", metavar="PATH")
    validate_p.add_argument("--allow-row-level", action="store_true", help="confirm publishing a large-lane (row-level) chart")
    validate_p.set_defaults(func=_cmd_validate)

    publish_p = sub.add_parser("publish", help="validate, then upload a staged chart directory or a dashboard file")
    publish_p.add_argument("path", metavar="PATH")
    publish_p.add_argument("--force", action="store_true", help="overwrite an existing id")
    publish_p.add_argument("--allow-row-level", action="store_true", help="confirm publishing a large-lane (row-level) chart")
    publish_p.set_defaults(func=_cmd_publish)

    move_p = sub.add_parser("move", help="rename a chart or dashboard id and rewrite dashboards that reference it")
    move_p.add_argument("old_id", metavar="OLD_ID")
    move_p.add_argument("new_id", metavar="NEW_ID")
    move_p.add_argument("--yes", action="store_true", help="apply the move (without it, only the plan is printed)")
    move_p.set_defaults(func=_cmd_move)

    preview_p = sub.add_parser("preview", help="serve the staging directory locally so charts can be opened before publishing")
    preview_p.add_argument("--staging", default=None, metavar="DIR", help="staging directory (default ./.viz-staging)")
    preview_p.add_argument("--host", default="127.0.0.1")
    preview_p.add_argument("--port", type=int, default=8000)
    preview_p.set_defaults(func=_cmd_preview)

    query_p = sub.add_parser("query", help="run SQL on Databricks and stage the result as a chart")
    query_p.add_argument("--sql", required=True, metavar="SQL_OR_@FILE")
    query_p.add_argument("--id", required=True, help="chart id, for example sales/emea/revenue")
    query_p.add_argument("--warehouse", default=None, metavar="ID", help="SQL warehouse id (default DATABRICKS_WAREHOUSE_ID)")
    query_p.add_argument("--drop-columns", default=None, metavar="a,b")
    query_p.add_argument("--staging", default=None, metavar="DIR", help="staging directory (default ./.viz-staging)")
    query_p.set_defaults(func=_cmd_query)

    # Later tasks add their subcommands below this line.

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2
    try:
        return func(args)
    except CliError as err:
        for line in err.messages:
            print(f"error: {line}", file=sys.stderr)
        return err.code


if __name__ == "__main__":
    sys.exit(main())
