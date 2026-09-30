import re
from pathlib import Path

import yaml
from viz.config import Settings

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
    assert values["networkPolicy"]["egressCidrs"] == ["192.0.2.0/24"]


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


def test_empty_egress_list_fails_the_render():
    text = _template("networkpolicy.yaml")
    assert "fail" in text and "egressCidrs" in text


def test_sts_uses_the_regional_endpoint():
    assert "name: AWS_STS_REGIONAL_ENDPOINTS" in _template("deployment.yaml")


def test_values_explain_gateway_endpoints_and_policy_enforcement():
    text = (CHART / "values.yaml").read_text(encoding="utf-8")
    assert "prefix-list" in text
    assert "enableNetworkPolicy" in text


def test_ingress_cidrs_are_supported_for_alb():
    assert "ingressCidrs" in (CHART / "values.yaml").read_text(encoding="utf-8")
    assert "ingressCidrs" in _template("networkpolicy.yaml")


def test_fullname_is_the_release_name_when_it_contains_the_chart_name():
    text = _template("_helpers.tpl")
    assert "contains .Chart.Name .Release.Name" in text
    assert '{{- .Release.Name | trunc 63 | trimSuffix "-" -}}' in text
    assert '{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}' in text


def test_service_account_name_defaults_to_the_fullname():
    helpers = _template("_helpers.tpl")
    assert 'define "viz-site.serviceAccountName"' in helpers
    assert 'default (include "viz-site.fullname" .) .Values.serviceAccount.name' in helpers
    assert _values()["serviceAccount"]["name"] == ""
    assert 'name: {{ include "viz-site.serviceAccountName" . }}' in _template("serviceaccount.yaml")
    assert 'serviceAccountName: {{ include "viz-site.serviceAccountName" . }}' in _template("deployment.yaml")
    for name in ("serviceaccount.yaml", "deployment.yaml"):
        assert ".Values.serviceAccount.name" not in _template(name), name


def test_identity_gate_is_on_by_default():
    assert _values()["requireIdentity"] is True
    text = _template("deployment.yaml")
    assert "- name: VIZ_REQUIRE_IDENTITY\n              value: {{ .Values.requireIdentity | quote }}" in text


def test_require_identity_env_matches_a_setting():
    # The env var only works if it maps to a real field (plan 5a adds require_identity).
    assert "require_identity" in Settings.model_fields
    assert Settings(require_identity="true").require_identity is True


def _probe(text: str, start: str, end: str) -> dict[str, int]:
    block = text.split(start, 1)[1].split(end, 1)[0]
    return {key: int(value) for key, value in re.findall(r"(\w+Seconds|failureThreshold): (\d+)", block)}


def test_readiness_and_liveness_differ_and_liveness_is_more_lenient():
    text = _template("deployment.yaml")
    ready = _probe(text, "readinessProbe:", "livenessProbe:")
    live = _probe(text, "livenessProbe:", "lifecycle:")
    assert ready == {"periodSeconds": 5, "timeoutSeconds": 2, "failureThreshold": 3}
    assert live == {"initialDelaySeconds": 10, "periodSeconds": 20, "timeoutSeconds": 5, "failureThreshold": 6}
    assert live["periodSeconds"] * live["failureThreshold"] > ready["periodSeconds"] * ready["failureThreshold"]
    assert live["timeoutSeconds"] > ready["timeoutSeconds"]


def test_pods_shut_down_gracefully():
    text = _template("deployment.yaml")
    assert "      terminationGracePeriodSeconds: 30\n" in text
    assert 'preStop:\n              exec:\n                command: ["sleep", "5"]' in text


def test_disruption_budget_only_with_more_than_one_replica():
    text = _template("pdb.yaml")
    assert text.startswith("{{- if gt (int .Values.replicaCount) 1 }}")
    assert "apiVersion: policy/v1" in text
    assert "kind: PodDisruptionBudget" in text
    assert "  minAvailable: 1" in text
    assert 'include "viz-site.selectorLabels" .' in text
    assert text.rstrip().endswith("{{- end }}")


def test_alb_annotations_render_only_for_the_alb_class():
    text = _template("ingress.yaml")
    start = text.index('{{- if eq .Values.ingress.className "alb" }}')
    middle = text.index("{{- else }}", start)
    alb_block, nginx_block = text[start:middle], text[middle:]
    for line in (
        "alb.ingress.kubernetes.io/scheme: internal",
        "alb.ingress.kubernetes.io/target-type: ip",
        """alb.ingress.kubernetes.io/listen-ports: '[{"HTTPS":443}]'""",
        "alb.ingress.kubernetes.io/certificate-arn: {{ .Values.ingress.alb.certificateArn | quote }}",
        "alb.ingress.kubernetes.io/healthcheck-path: /api/health",
    ):
        assert line in alb_block, line
    assert "nginx.ingress.kubernetes.io" not in alb_block
    assert "alb.ingress.kubernetes.io" not in nginx_block.split("{{- with .Values.ingress.annotations }}")[0]


def test_nginx_rate_limit_can_be_switched_off():
    text = _template("ingress.yaml")
    nginx_block = text[text.index("{{- else }}"):]
    assert "{{- if .Values.ingress.rateLimit.enabled }}" in nginx_block
    assert "nginx.ingress.kubernetes.io/limit-rps: {{ .Values.ingress.rateLimit.perSecond | quote }}" in nginx_block
    ingress = _values()["ingress"]
    assert ingress["rateLimit"] == {"enabled": True, "perSecond": 10}
    assert "rateLimitPerSecond" not in ingress
    values_text = (CHART / "values.yaml").read_text(encoding="utf-8")
    assert "SSO proxy" in values_text.split("rateLimit:")[0].rsplit("host:", 1)[1]


def test_alb_certificate_is_a_placeholder():
    arn = _values()["ingress"]["alb"]["certificateArn"]
    assert arn.startswith("arn:aws:acm:REPLACE_ME-region:123456789012:certificate/")
    assert "REPLACE_ME" in arn.rsplit("/", 1)[1]


def test_extra_dns_resolvers_are_allowed_on_udp_and_tcp_53():
    assert _values()["networkPolicy"]["dnsCidrs"] == []
    text = _template("networkpolicy.yaml")
    # The block runs from the `with` to the S3 rule's comment (its first `{{- end }}` closes the inner range).
    block = text.split("{{- with .Values.networkPolicy.dnsCidrs }}", 1)[1].split("# S3 and STS over HTTPS only.", 1)[0]
    assert "- ipBlock:\n            cidr: {{ . }}" in block
    assert "- port: 53\n          protocol: UDP\n        - port: 53\n          protocol: TCP" in block
    # The kube-dns rule is still there.
    assert "kubernetes.io/metadata.name: kube-system" in text
    assert text.count("port: 53") == 4
    values_text = (CHART / "values.yaml").read_text(encoding="utf-8")
    assert "NodeLocal DNSCache" in values_text.split("dnsCidrs:")[0].rsplit("egressCidrs:", 1)[1]
