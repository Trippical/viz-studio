from pathlib import Path

import yaml

CHART = Path(__file__).resolve().parents[2] / "deploy" / "helm" / "viz-site"


def _values() -> dict:
    return yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))


def _template(name: str) -> str:
    return (CHART / "templates" / name).read_text(encoding="utf-8")


def test_chart_metadata():
    chart = yaml.safe_load((CHART / "Chart.yaml").read_text(encoding="utf-8"))
    assert chart["apiVersion"] == "v2"
    assert chart["name"] == "viz-site"


def test_values_hold_placeholders_only():
    values = _values()
    assert "REPLACE_ME" in values["image"]["repository"]
    assert "REPLACE_ME" in values["bucket"]["name"]
    assert values["serviceAccount"]["roleArn"].startswith("arn:aws:iam::123456789012:role/")
    assert values["allowedHosts"].endswith("example.com")


def test_pod_is_locked_down():
    text = _template("deployment.yaml")
    for fragment in (
        "automountServiceAccountToken: false",
        "runAsNonRoot: true",
        "runAsUser: 10001",
        "readOnlyRootFilesystem: true",
        "allowPrivilegeEscalation: false",
        "- ALL",
        "type: RuntimeDefault",
        "emptyDir: {}",
        "mountPath: /tmp",
        "resources:",
    ):
        assert fragment in text, fragment


def test_probes_send_an_allowed_host_header():
    text = _template("deployment.yaml")
    assert text.count("path: /api/health") == 2
    assert text.count("name: Host") == 2


def test_server_reads_s3_and_the_allow_list_from_values():
    text = _template("deployment.yaml")
    for name in ("VIZ_STORAGE", "VIZ_S3_BUCKET", "VIZ_ROOT_PREFIX", "VIZ_ALLOWED_HOSTS", "VIZ_AUTH_HEADER", "AWS_REGION"):
        assert f"name: {name}" in text, name
    assert 'value: "s3"' in text


def test_service_is_cluster_internal():
    assert "type: ClusterIP" in _template("service.yaml")


def test_service_account_uses_irsa_not_the_node_role():
    text = _template("serviceaccount.yaml")
    assert "eks.amazonaws.com/role-arn" in text
    assert "automountServiceAccountToken: false" in text


def test_ingress_is_internal_and_rate_limited():
    text = _template("ingress.yaml")
    assert "nginx.ingress.kubernetes.io/limit-rps" in text
    assert "alb.ingress.kubernetes.io/scheme: internal" in text
    assert "internal" in text.lower()


def test_network_policy_limits_ingress_and_egress():
    text = _template("networkpolicy.yaml")
    assert "- Ingress" in text and "- Egress" in text
    assert "port: 53" in text
    assert "port: 443" in text
    assert "ipBlock" in text


def test_no_databricks_anywhere_in_the_chart():
    for path in CHART.rglob("*"):
        if path.is_file():
            assert "DATABRICKS" not in path.read_text(encoding="utf-8"), path.name
