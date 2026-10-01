"""The storage protocol every backend implements."""
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Protocol


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size: int
    etag: str
    last_modified: datetime | None


class NotFound(KeyError):
    pass


class PreconditionFailed(Exception):
    """A conditional put was refused: the key exists (if_none_match) or its ETag
    changed or it disappeared (if_match)."""


class Storage(Protocol):
    def list(self, prefix: str) -> list[ObjectInfo]:
        """All objects whose key starts with prefix, sorted by key."""

    def head(self, key: str) -> ObjectInfo:
        """Size and ETag of one object. Raises NotFound. The ETag is unquoted."""

    def get(self, key: str) -> bytes: ...

    def open(self, key: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        """Stream bytes from start to end inclusive. end=None means to the end."""

    def put(self, key: str, data: bytes, content_type: str, *, if_match: str | None = None,
            if_none_match: bool = False) -> None:
        """Write one object. if_none_match=True: only if the key does not exist.
        if_match=<etag>: only if the key exists with that ETag (unquoted, as head() returns it).
        A failed condition raises PreconditionFailed. Passing both raises ValueError."""

    def delete(self, key: str) -> None:
        """Delete if present. Missing keys are not an error."""

    def copy(self, src: str, dst: str) -> None: ...
