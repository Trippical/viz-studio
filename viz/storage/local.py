"""Filesystem backend. The root directory is the bucket."""
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .base import NotFound, ObjectInfo

CHUNK = 1024 * 1024
_log = logging.getLogger("viz.storage")


class LocalStorage:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._resolved_root = self.root.resolve()
        if not self.root.exists():
            _log.warning("local storage root does not exist: %s", self.root)

    def _path(self, key: str) -> Path:
        if key.startswith("/") or ".." in key.split("/"):
            raise NotFound(key)
        path = (self.root / key)
        # Refuse anything that resolves outside the root, including symlinks that escape.
        resolved = path.resolve()
        if resolved != self._resolved_root and self._resolved_root not in resolved.parents:
            raise NotFound(key)
        return path

    def _info(self, key: str, path: Path) -> ObjectInfo:
        st = path.stat()
        return ObjectInfo(
            key=key,
            size=st.st_size,
            etag=f"{st.st_size:x}-{st.st_mtime_ns:x}",
            last_modified=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
        )

    def list(self, prefix: str) -> list[ObjectInfo]:
        out = []
        for dirpath, _dirnames, filenames in os.walk(self.root):
            for name in filenames:
                path = Path(dirpath) / name
                key = path.relative_to(self.root).as_posix()
                if not key.startswith(prefix):
                    continue
                try:
                    self._path(key)
                except NotFound:
                    continue
                try:
                    out.append(self._info(key, path))
                except FileNotFoundError:
                    continue
        return sorted(out, key=lambda o: o.key)

    def head(self, key: str) -> ObjectInfo:
        path = self._path(key)
        if not path.is_file():
            raise NotFound(key)
        return self._info(key, path)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise NotFound(key)
        return path.read_bytes()

    def open(self, key: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        path = self._path(key)
        if not path.is_file():
            raise NotFound(key)
        size = path.stat().st_size
        stop = size - 1 if end is None else min(end, size - 1)
        remaining = stop - start + 1
        with path.open("rb") as f:
            f.seek(start)
            while remaining > 0:
                chunk = f.read(min(CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()

    def copy(self, src: str, dst: str) -> None:
        src_path = self._path(src)
        if not src_path.is_file():
            raise NotFound(src)
        dst_path = self._path(dst)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_path, dst_path)
