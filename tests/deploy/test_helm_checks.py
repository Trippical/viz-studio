"""The CI helm render checks. The checks themselves need helm and run in the CI
helm job; here we test the pieces that do not need helm."""
import importlib.util
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / ".github" / "scripts" / "helm_checks.py"
NETWORKPOLICY = REPO / "deploy" / "helm" / "viz-site" / "templates" / "networkpolicy.yaml"


@pytest.fixture
def checks():
    spec = importlib.util.spec_from_file_location("helm_checks", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_negative_check_expects_the_templates_own_message(checks):
    # A28: the CI check must fail on any other error, so it looks for this exact text.
    assert checks.EGRESS_ERROR in NETWORKPOLICY.read_text(encoding="utf-8")


def test_every_check_is_registered(checks):
    assert [check.__name__ for check in checks.CHECKS] == [
        "check_empty_egress_fails_with_its_message",
        "check_names",
        "check_identity_gate",
        "check_probes_and_shutdown",
        "check_ingress",
        "check_dns",
    ]


def test_dns_ports_ok(checks):
    assert checks.dns_ports_ok({"ports": [{"port": 53, "protocol": "UDP"}, {"port": 53, "protocol": "TCP"}]})
    assert not checks.dns_ports_ok({"ports": [{"port": 53, "protocol": "UDP"}]})
    assert not checks.dns_ports_ok({"ports": [{"port": 443, "protocol": "TCP"}]})


def test_one_refuses_zero_or_two_matches(checks):
    with pytest.raises(AssertionError):
        checks.one([], "Deployment")
    with pytest.raises(AssertionError):
        checks.one([{"kind": "Deployment"}, {"kind": "Deployment"}], "Deployment")
    assert checks.one([{"kind": "Service"}, {"kind": "Deployment", "x": 1}], "Deployment") == {"kind": "Deployment", "x": 1}


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed; the CI helm job runs these checks")
def test_chart_passes_every_check(checks, monkeypatch):
    monkeypatch.chdir(REPO)
    assert checks.main() == 0
