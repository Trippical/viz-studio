"""Pick a storage backend from settings."""
from ..config import Settings
from .base import NotFound, ObjectInfo, Storage
from .local import LocalStorage
from .s3 import S3Storage

__all__ = ["NotFound", "ObjectInfo", "Storage", "get_storage"]


def get_storage(settings: Settings) -> Storage:
    if settings.storage == "local":
        return LocalStorage(settings.local_dir)
    if not settings.s3_bucket:
        raise ValueError("VIZ_S3_BUCKET is required when VIZ_STORAGE=s3")
    return S3Storage(settings.s3_bucket)
