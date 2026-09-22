"""Id validation and bucket key derivation. Ids are slash-separated slugs."""
import re

ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)*$")
MAX_ID_LENGTH = 512
DATA_FORMATS = ("json", "parquet")
KINDS = ("charts", "dashboards")


class InvalidId(ValueError):
    pass


def validate_id(value: str) -> str:
    if not isinstance(value, str) or len(value) > MAX_ID_LENGTH or not ID_PATTERN.fullmatch(value):
        raise InvalidId(f"invalid id: {value!r}")
    return value


def normalize_root(prefix: str) -> str:
    prefix = prefix.strip("/")
    return f"{prefix}/" if prefix else ""


def chart_key(root: str, chart_id: str) -> str:
    return f"{root}charts/{chart_id}/chart.json"


def data_key(root: str, chart_id: str, fmt: str) -> str:
    if fmt not in DATA_FORMATS:
        raise ValueError(f"unknown data format: {fmt!r}")
    return f"{root}charts/{chart_id}/data.{fmt}"


def dashboard_key(root: str, dashboard_id: str) -> str:
    return f"{root}dashboards/{dashboard_id}.json"


def folder_key(root: str, kind: str, folder: str) -> str:
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind!r}")
    return f"{root}{kind}/{folder}/_folder.json" if folder else f"{root}{kind}/_folder.json"


def is_ancestor(a: str, b: str) -> bool:
    return b.startswith(a + "/")
