# viz/publish/__init__.py
"""The publisher: staging, validation and publishing. The command line is viz.publish.cli."""
import sys
from pathlib import Path


def stage(df, chart_id: str, staging_root: Path | str | None = None) -> Path:
    """Stage a pandas DataFrame or a pyarrow Table as chart `chart_id`.
    Returns the staged chart directory. Author comes from the same rules as the CLI."""
    from datetime import datetime, timezone

    import pyarrow as pa

    from ..config import Settings
    from .identity import publisher_author
    from .pii import pii_warning
    from .staging import write_staged_chart

    if isinstance(df, pa.Table):
        table = df
    elif hasattr(df, "to_dict"):  # a pandas DataFrame; pandas itself is not a dependency
        table = pa.Table.from_pandas(df, preserve_index=False)
    else:
        raise TypeError("stage() takes a pandas DataFrame or a pyarrow Table")
    settings = Settings()
    root = Path(staging_root) if staging_root is not None else settings.staging_dir
    try:
        author = publisher_author(settings)
    except Exception as err:
        raise RuntimeError(f"could not resolve the author identity: {err}") from err
    warning = pii_warning(table.column_names, settings.pii_pattern)
    if warning:
        print(warning, file=sys.stderr)
    staged = write_staged_chart(table, chart_id, root, author=author, now=datetime.now(timezone.utc))
    return staged.dir
