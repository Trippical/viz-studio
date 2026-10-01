"""Who published a chart or dashboard, for attribution. `author` tells readers whom to
ask about a chart; it is attribution, not authentication, and it grants nothing.
The CLI stamps it, and `viz validate` checks that the stamped value equals what the
CLI would stamp now, so a hand-typed author is caught as a mistake."""
import getpass

from ..config import Settings
from .query import current_user, databricks_login_available


def resolve_author(settings: Settings, databricks_user: str | None = None) -> str:
    if databricks_user:
        return databricks_user
    if settings.author:
        return settings.author
    if settings.storage == "s3":
        import boto3  # local import keeps the local path free of AWS calls

        return boto3.client("sts").get_caller_identity()["Arn"]
    return f"{getpass.getuser()}@local"


def publisher_author(settings: Settings, databricks_user: str | None = None,
                     warehouse_id: str | None = None) -> str:
    """The one author rule for every command that stamps a document (query, stage,
    new-dashboard, pull-dashboard) and for `viz validate` (finding A19):
    1. databricks_user, when the caller already read the login (`viz query` does);
    2. the Databricks login, when DATABRICKS_HOST, DATABRICKS_TOKEN and a warehouse
       (warehouse_id, else DATABRICKS_WAREHOUSE_ID) are all set;
    3. otherwise resolve_author: VIZ_AUTHOR, then the AWS caller identity, then <user>@local.
    No command needs DATABRICKS_WAREHOUSE_ID: without it, rule 3 applies.
    Raises QueryError when Databricks is configured but cannot be reached."""
    if databricks_user:
        return databricks_user
    if databricks_login_available(warehouse_id):
        return current_user(warehouse_id)
    return resolve_author(settings)


def author_errors(doc: dict, expected: str) -> list[str]:
    actual = doc.get("author")
    if actual is None:
        return [f"author is missing; the CLI stamps it as '{expected}'"]
    if actual != expected:
        return [f"author '{actual}' does not match the resolved identity '{expected}'"]
    return []


def check_author(doc: dict, settings: Settings, databricks_user: str | None = None) -> list[str]:
    return author_errors(doc, resolve_author(settings, databricks_user))
