"""Id validation and bucket key derivation. Ids are slash-separated slugs."""
import re

ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)*$")
MAX_ID_LENGTH = 512
DATA_FORMATS = ("json", "parquet")
DATA_FILE_PATTERN = re.compile(r"^data\.[0-9a-f]{16}\.(json|parquet)$")
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
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


def data_file_name(sha256_hex: str, fmt: str) -> str:
    """The content-addressed name of a data file: data.<first 16 hex of its SHA-256>.<format>."""
    if fmt not in DATA_FORMATS:
        raise ValueError(f"unknown data format: {fmt!r}")
    if not isinstance(sha256_hex, str) or not SHA256_HEX.fullmatch(sha256_hex):
        raise ValueError(f"not a SHA-256 hex digest: {sha256_hex!r}")
    return f"data.{sha256_hex[:16]}.{fmt}"


def data_key(root: str, chart_id: str, file_name: str) -> str:
    """Bucket key of the data file that chart.json names in data.file."""
    if not isinstance(file_name, str) or not DATA_FILE_PATTERN.fullmatch(file_name):
        raise ValueError(f"invalid data file name: {file_name!r}")
    return f"{root}charts/{chart_id}/{file_name}"


def dashboard_key(root: str, dashboard_id: str) -> str:
    return f"{root}dashboards/{dashboard_id}.json"


def folder_key(root: str, kind: str, folder: str) -> str:
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind!r}")
    return f"{root}{kind}/{folder}/_folder.json" if folder else f"{root}{kind}/_folder.json"


def is_ancestor(a: str, b: str) -> bool:
    return b.startswith(a + "/")
