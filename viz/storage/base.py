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


class Storage(Protocol):
    def list(self, prefix: str) -> list[ObjectInfo]:
        """All objects whose key starts with prefix, sorted by key."""

    def head(self, key: str) -> ObjectInfo: ...

    def get(self, key: str) -> bytes: ...

    def open(self, key: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        """Stream bytes from start to end inclusive. end=None means to the end."""

    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def delete(self, key: str) -> None:
        """Delete if present. Missing keys are not an error."""

    def copy(self, src: str, dst: str) -> None: ...
