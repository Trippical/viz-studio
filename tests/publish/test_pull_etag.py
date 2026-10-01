"""pull-dashboard remembers the version it pulled; publish refuses to overwrite a newer
one (finding A25)."""
import json

import viz.publish.cli as cli
from viz.publish.cli import main
from viz.publish.dashboards import pulled_etag_path, read_pulled_etag
from viz.storage.local import LocalStorage

KEY = "viz/dashboards/sales/overview.json"


def _path(staging_root):
    return staging_root / "dashboards" / "sales" / "overview.json"


class RecordingStorage(LocalStorage):
    """Records the keyword arguments of every put."""

    def __init__(self, root):
        super().__init__(root)
        self.put_kwargs = {}

    def put(self, key, data, content_type, **kwargs):
        self.put_kwargs[key] = kwargs
        super().put(key, data, content_type, **kwargs)


def test_sidecar_sits_next_to_the_staged_file(staging_root):
    assert pulled_etag_path(_path(staging_root)) == staging_root / "dashboards" / "sales" / "overview.json.pulled-etag"


def test_pull_records_the_published_etag(env, staging_root, storage):
    assert main(["pull-dashboard", "sales/overview"]) == 0
    assert read_pulled_etag(_path(staging_root)) == storage.head(KEY).etag


def test_sidecar_is_removed_after_a_successful_publish(env, staging_root, storage, capsys):
    assert main(["pull-dashboard", "sales/overview"]) == 0
    assert main(["publish", str(_path(staging_root)), "--force"]) == 0
    assert not pulled_etag_path(_path(staging_root)).exists()
    assert json.loads(storage.get(KEY))["author"] == "tester@example.com"


def test_colleague_edit_after_pull_is_refused(env, staging_root, storage, capsys):
    assert main(["pull-dashboard", "sales/overview"]) == 0
    colleague = json.loads(storage.get(KEY))
    colleague["title"] = "Colleague's title"
    storage.put(KEY, json.dumps(colleague).encode("utf-8"), "application/json")
    capsys.readouterr()
    assert main(["publish", str(_path(staging_root)), "--force"]) == 1
    err = capsys.readouterr().err
    assert "published again by someone else after you pulled it" in err
    assert "ask the user" in err
    assert json.loads(storage.get(KEY))["title"] == "Colleague's title"
    assert pulled_etag_path(_path(staging_root)).exists()


def test_dashboard_deleted_after_pull_is_refused(env, staging_root, storage, capsys):
    assert main(["pull-dashboard", "sales/overview"]) == 0
    storage.delete(KEY)
    capsys.readouterr()
    assert main(["publish", str(_path(staging_root)), "--force"]) == 1
    assert "was deleted after you pulled it" in capsys.readouterr().err


def test_publish_passes_the_pulled_etag_as_if_match(env, bucket, staging_root, monkeypatch):
    assert main(["pull-dashboard", "sales/overview"]) == 0
    pulled = read_pulled_etag(_path(staging_root))
    recording = RecordingStorage(bucket)
    monkeypatch.setattr(cli, "get_storage", lambda settings: recording)
    assert main(["publish", str(_path(staging_root)), "--force"]) == 0
    assert recording.put_kwargs[KEY].get("if_match") == pulled


def test_new_dashboard_removes_a_stale_sidecar(env, staging_root):
    assert main(["pull-dashboard", "sales/overview"]) == 0
    assert main(["new-dashboard", "sales/overview", "--force"]) == 0
    assert not pulled_etag_path(_path(staging_root)).exists()
