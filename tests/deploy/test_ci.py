import re
from pathlib import Path

import yaml
from viz.config import Settings

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _runs(job: dict) -> str:
    return "\n".join(step.get("run", "") for step in job["steps"])


def test_triggers():
    wf = _workflow()
    # PyYAML reads the bare key `on` as the boolean True.
    triggers = wf.get("on", wf.get(True))
    assert triggers["push"]["branches"] == ["main"]
    assert "pull_request" in triggers


def test_all_jobs_exist():
    assert set(_workflow()["jobs"]) == {"python", "web", "docker", "helm", "gitleaks"}


def test_python_job_runs_the_suite():
    assert "python -m pytest" in _runs(_workflow()["jobs"]["python"])


def test_web_job_creates_the_repo_venv():
    runs = _runs(_workflow()["jobs"]["web"])
    assert "python -m venv .venv" in runs
    assert '.venv/bin/python -m pip install -e ".[dev]"' in runs


def test_web_job_handles_esbuild_and_chromium():
    runs = _runs(_workflow()["jobs"]["web"])
    assert "node node_modules/esbuild/install.js" in runs
    assert "npx playwright install --with-deps chromium" in runs
    for script in ("npm run typecheck", "npm test", "npm run e2e"):
        assert script in runs, script


def test_docker_and_helm_jobs():
    jobs = _workflow()["jobs"]
    assert "docker build" in _runs(jobs["docker"])
    helm = _runs(jobs["helm"])
    assert "helm lint deploy/helm/viz-site" in helm
    assert "helm template" in helm


def test_docker_job_smoke_tests_the_image():
    docker = _runs(_workflow()["jobs"]["docker"])
    for fragment in (
        "docker run",
        "--read-only",
        '-v "$PWD/sample-bucket:/data:ro"',
        "-e VIZ_STORAGE=local",
        "-e VIZ_LOCAL_DIR=/data",
        "-e VIZ_ROOT_PREFIX=viz/",
        "python3 .github/scripts/docker_smoke.py http://localhost:8000",
        'test "$(docker exec viz id -u)" = "10001"',
    ):
        assert fragment in docker, fragment
    # The old check fetched the wasm with curl -o /dev/null and passed on the index.html fallback.
    assert "curl -fsS -o /dev/null" not in docker


def test_docker_job_env_names_are_real_settings():
    docker = _runs(_workflow()["jobs"]["docker"])
    names = re.findall(r"-e (VIZ_[A-Z_]+)=", docker)
    assert {"VIZ_STORAGE", "VIZ_LOCAL_DIR", "VIZ_ROOT_PREFIX", "VIZ_ALLOWED_HOSTS"} <= set(names)
    for name in names:
        assert name.removeprefix("VIZ_").lower() in Settings.model_fields, name


def test_docker_job_always_removes_the_container():
    steps = _workflow()["jobs"]["docker"]["steps"]
    cleanup = [step for step in steps if step.get("if") == "always()"]
    assert cleanup and "docker rm -f viz" in cleanup[0]["run"]


def test_helm_job_runs_the_render_checks():
    job = _workflow()["jobs"]["helm"]
    helm = _runs(job)
    assert 'python -m pip install "pyyaml>=6"' in helm
    assert "python .github/scripts/helm_checks.py" in helm
    assert any(step.get("uses", "").startswith("actions/setup-python") for step in job["steps"])
    # A28: the old inline check passed on any failure; the script checks the message.
    assert "> /dev/null 2>&1" not in helm


def test_gitleaks_scans_full_history():
    job = _workflow()["jobs"]["gitleaks"]
    checkout = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout"))
    assert checkout["with"]["fetch-depth"] == 0
    assert any(step.get("uses", "").startswith("gitleaks/gitleaks-action") for step in job["steps"])


def test_integration_tests_never_run_in_ci():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "VIZ_INTEGRATION" not in text
    assert "DATABRICKS" not in text


def test_workflow_token_is_read_only():
    assert _workflow()["permissions"] == {"contents": "read"}


def test_gitleaks_can_read_pull_request_commits():
    job = _workflow()["jobs"]["gitleaks"]
    assert job["permissions"] == {"contents": "read", "pull-requests": "read"}
