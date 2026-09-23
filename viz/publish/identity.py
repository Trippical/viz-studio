"""Who is publishing. The CLI stamps `author`; a hand-set value that disagrees fails validation."""
import getpass

from ..config import Settings


def resolve_author(settings: Settings, databricks_user: str | None = None) -> str:
    if databricks_user:
        return databricks_user
    if settings.author:
        return settings.author
    if settings.storage == "s3":
        import boto3  # local import keeps the local path free of AWS calls

        return boto3.client("sts").get_caller_identity()["Arn"]
    return f"{getpass.getuser()}@local"


def check_author(doc: dict, settings: Settings, databricks_user: str | None = None) -> list[str]:
    expected = resolve_author(settings, databricks_user)
    actual = doc.get("author")
    if actual is None:
        return [f"author is missing; the CLI stamps it as '{expected}'"]
    if actual != expected:
        return [f"author '{actual}' does not match the resolved identity '{expected}'"]
    return []
