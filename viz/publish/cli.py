"""The viz command line. Every subcommand is a thin function that calls one module."""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .. import __version__
from ..config import Settings
from .errors import CliError
from .identity import resolve_author
from .infer import UnsupportedColumn, table_from_file
from .pii import drop_columns, parse_drop_list, pii_warning
from .staging import LaneError, column_summary, write_staged_chart


def _debug_raise(args) -> int:
    """Hidden subcommand used only by tests to exercise error printing."""
    return _DEBUG_HANDLER(args)


def _no_debug(args) -> int:
    return 0


_DEBUG_HANDLER = _no_debug


def _staging_root(args, settings: Settings) -> Path:
    return Path(args.staging) if getattr(args, "staging", None) else settings.staging_dir


def _stage_table(table, chart_id: str, settings: Settings, args, *, author: str, source: dict | None = None) -> int:
    """Shared tail of `stage` and `query`: PII warning, --drop-columns, write, summary."""
    try:
        warning = pii_warning(table.column_names, settings.pii_pattern)
    except ValueError as err:
        raise CliError(str(err), code=2) from err
    if warning:
        print(warning, file=sys.stderr)
    try:
        table = drop_columns(table, parse_drop_list(getattr(args, "drop_columns", None)))
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
    except UnsupportedColumn as err:
        raise CliError(str(err), code=2) from err
    return _stage_table(table, args.id, settings, args, author=resolve_author(settings))


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
