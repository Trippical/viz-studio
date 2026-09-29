from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]


def _dockerfile() -> str:
    return (REPO / "Dockerfile").read_text(encoding="utf-8")


def test_image_runs_as_a_non_root_user():
    text = _dockerfile()
    assert "useradd --uid 10001" in text
    assert "\nUSER 10001\n" in text


def test_image_ships_the_whole_front_end_build():
    text = _dockerfile()
    # The whole dist, so dist/duckdb/** (the self-hosted parquet extension) comes along.
    assert "COPY --from=web /src/web/dist /app/web/dist" in text
    assert "VIZ_WEB_DIST=/app/web/dist" in text


def test_image_works_around_skipped_esbuild_postinstall():
    assert "node node_modules/esbuild/install.js" in _dockerfile()


def test_image_serves_on_all_interfaces_and_runs_only_the_server():
    text = _dockerfile()
    assert "VIZ_HOST=0.0.0.0" in text
    assert 'CMD ["viz-server"]' in text


def test_no_databricks_settings_in_container_files():
    for name in ("Dockerfile", "docker-compose.yml", ".dockerignore"):
        assert "DATABRICKS" not in (REPO / name).read_text(encoding="utf-8"), name


def test_dockerignore_keeps_local_state_out_of_the_build_context():
    lines = (REPO / ".dockerignore").read_text(encoding="utf-8").split()
    for entry in (".venv", "web/node_modules", "web/dist", ".viz-staging", ".env*", ".superpowers", ".worktrees", ".git"):
        assert entry in lines, entry


def test_compose_runs_locked_down_on_loopback():
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
    service = compose["services"]["viz-site"]
    assert service["ports"] == ["127.0.0.1:8000:8000"]
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert service["environment"]["VIZ_STORAGE"] == "local"
    assert service["environment"]["VIZ_ALLOWED_HOSTS"] == "localhost,127.0.0.1"
    assert "./sample-bucket:/data:ro" in service["volumes"]
