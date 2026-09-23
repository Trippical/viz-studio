"""The viz command line. Every subcommand is a thin function that calls one module."""
import argparse
import sys

from .. import __version__
from .errors import CliError


def _debug_raise(args) -> int:
    """Hidden subcommand used only by tests to exercise error printing."""
    return _DEBUG_HANDLER(args)


def _no_debug(args) -> int:
    return 0


_DEBUG_HANDLER = _no_debug


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="viz", description="Stage, validate and publish charts and dashboards.")
    parser.add_argument("--version", action="version", version=f"viz {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    debug = sub.add_parser("debug-raise", help=argparse.SUPPRESS)
    debug.set_defaults(func=_debug_raise)

    # Later tasks add their subcommands below this line, each as:
    #   p = sub.add_parser("name", help="...")
    #   p.add_argument(...)
    #   p.set_defaults(func=_cmd_name)

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
