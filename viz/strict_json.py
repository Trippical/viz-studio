"""Parse an untrusted JSON document (from the bucket or the staging folder).

Python's json module accepts NaN, Infinity and -Infinity, which are not JSON and which
the server cannot send back (Starlette refuses to encode them). It also raises a plain
ValueError for an integer with more than 4300 digits, and RecursionError for very deep
nesting. loads() turns every one of these into InvalidJson, so each reader has one
exception to catch and one way to word the error."""
import json
from typing import Any

NON_FINITE = "NaN/Infinity is not allowed"


class InvalidJson(ValueError):
    """The text is not a JSON document the site accepts."""

    def __init__(self, reason: str, non_finite: bool = False):
        self.reason = reason
        self.non_finite = non_finite
        super().__init__(reason)

    def describe(self, where: str) -> str:
        """The error line for a document at `where`, for example '$' or 'chart.json'."""
        if self.non_finite:
            return f"{where}: not valid JSON: {NON_FINITE}"
        return f"{where}: invalid JSON ({self.reason})"


def _reject_constant(name: str) -> Any:
    raise InvalidJson(NON_FINITE, non_finite=True)


def loads(raw: str | bytes) -> Any:
    try:
        return json.loads(raw, parse_constant=_reject_constant)
    except InvalidJson:
        raise
    except RecursionError as err:
        raise InvalidJson("nested too deeply") from err
    except ValueError as err:  # JSONDecodeError, UnicodeDecodeError, too many integer digits
        raise InvalidJson(str(err)) from err
