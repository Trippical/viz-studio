"""Render the Helm chart in several configurations and check what comes out.

Runs in the CI helm job, which has the helm binary and PyYAML. Each check
renders the chart with `helm template`, parses the manifests and raises
AssertionError with a readable message when the chart is wrong.

Usage, from the repo root:
    python .github/scripts/helm_checks.py
"""
import subprocess
import sys

import yaml

CHART = "deploy/helm/viz-site"
EGRESS_ERROR = "networkPolicy.egressCidrs must list at least one CIDR"
# boto3 reads AWS_DEFAULT_REGION; other AWS SDKs read AWS_REGION. Both come from bucket.region.
REGION_ENV = ("AWS_REGION", "AWS_DEFAULT_REGION")


def render(release: str, *args: str) -> list[dict]:
    """The manifests `helm template <release> <chart> <args>` prints, empty documents dropped."""
    result = subprocess.run(["helm", "template", release, CHART, *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"helm template {release} {' '.join(args)} failed:\n{result.stderr}")
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def render_error(*args: str) -> str:
    """The error output of a `helm template` run that must fail."""
    result = subprocess.run(["helm", "template", "ci", CHART, *args], capture_output=True, text=True)
    if result.returncode == 0:
        raise AssertionError(f"helm template {' '.join(args)} succeeded but must fail")
    return result.stderr


def one(docs: list[dict], kind: str) -> dict:
    found = [doc for doc in docs if doc.get("kind") == kind]
    if len(found) != 1:
        raise AssertionError(f"expected exactly one {kind}, found {len(found)}")
    return found[0]


def pod_spec(docs: list[dict]) -> dict:
    return one(docs, "Deployment")["spec"]["template"]["spec"]


def env_of(docs: list[dict]) -> dict:
    return {item["name"]: item.get("value") for item in pod_spec(docs)["containers"][0]["env"]}


def annotations_of(docs: list[dict]) -> dict:
    return one(docs, "Ingress")["metadata"].get("annotations") or {}


def dns_ports_ok(rule: dict) -> bool:
    ports = sorted((port["protocol"], port["port"]) for port in rule.get("ports", []))
    return ports == [("TCP", 53), ("UDP", 53)]


def check_empty_egress_fails_with_its_message() -> None:
    """A28: an empty egress list must fail the render with the chart's own message."""
    stderr = render_error("--set-json", "networkPolicy.egressCidrs=[]")
    if EGRESS_ERROR not in stderr:
        raise AssertionError(f"the render failed, but not with {EGRESS_ERROR!r}:\n{stderr}")


def check_names() -> None:
    """A31: fullname and ServiceAccount name follow the release; serviceAccount.name overrides."""
    cases = [
        (("viz-site",), "viz-site", "viz-site"),
        (("prod",), "prod-viz-site", "prod-viz-site"),
        (("viz-site", "--set", "serviceAccount.name=custom-sa"), "viz-site", "custom-sa"),
    ]
    for args, fullname, account in cases:
        docs = render(*args)
        name = one(docs, "Deployment")["metadata"]["name"]
        if name != fullname:
            raise AssertionError(f"{args}: Deployment is named {name!r}, expected {fullname!r}")
        sa = one(docs, "ServiceAccount")["metadata"]["name"]
        if sa != account:
            raise AssertionError(f"{args}: ServiceAccount is named {sa!r}, expected {account!r}")
        used = pod_spec(docs)["serviceAccountName"]
        if used != account:
            raise AssertionError(f"{args}: pods use service account {used!r}, expected {account!r}")


def check_identity_gate() -> None:
    """B1: VIZ_REQUIRE_IDENTITY is "true" by default and can be turned off."""
    value = env_of(render("ci")).get("VIZ_REQUIRE_IDENTITY")
    if value != "true":
        raise AssertionError(f"VIZ_REQUIRE_IDENTITY is {value!r} by default, expected 'true'")
    value = env_of(render("ci", "--set", "requireIdentity=false")).get("VIZ_REQUIRE_IDENTITY")
    if value != "false":
        raise AssertionError(f"VIZ_REQUIRE_IDENTITY is {value!r} with requireIdentity=false, expected 'false'")


def check_region() -> None:
    """C4: AWS_REGION and AWS_DEFAULT_REGION both carry bucket.region."""
    env = env_of(render("ci", "--set", "bucket.region=eu-west-1"))
    for name in REGION_ENV:
        if env.get(name) != "eu-west-1":
            raise AssertionError(f"{name} is {env.get(name)!r} with bucket.region=eu-west-1")


def check_probes_and_shutdown() -> None:
    """A33: grace period, preStop, separate probes with timeouts, PDB only above one replica."""
    docs = render("ci")
    spec = pod_spec(docs)
    container = spec["containers"][0]
    if spec.get("terminationGracePeriodSeconds") != 30:
        raise AssertionError(f"terminationGracePeriodSeconds is {spec.get('terminationGracePeriodSeconds')!r}")
    command = container.get("lifecycle", {}).get("preStop", {}).get("exec", {}).get("command")
    if command != ["sleep", "5"]:
        raise AssertionError(f"preStop command is {command!r}")
    ready, live = container["readinessProbe"], container["livenessProbe"]
    if ready == live:
        raise AssertionError("readiness and liveness probes are identical")
    for label, probe in (("readiness", ready), ("liveness", live)):
        if "timeoutSeconds" not in probe:
            raise AssertionError(f"the {label} probe has no timeoutSeconds")
    if live["periodSeconds"] * live["failureThreshold"] <= ready["periodSeconds"] * ready["failureThreshold"]:
        raise AssertionError("the liveness probe is not more lenient than the readiness probe")
    pdb = one(docs, "PodDisruptionBudget")
    if pdb["spec"].get("minAvailable") != 1:
        raise AssertionError(f"PodDisruptionBudget minAvailable is {pdb['spec'].get('minAvailable')!r}")
    if pdb["spec"]["selector"]["matchLabels"] != one(docs, "Deployment")["spec"]["selector"]["matchLabels"]:
        raise AssertionError("the PodDisruptionBudget does not select the Deployment's pods")
    single = render("ci", "--set", "replicaCount=1")
    if [doc for doc in single if doc.get("kind") == "PodDisruptionBudget"]:
        raise AssertionError("a PodDisruptionBudget is rendered for a single replica")


def check_ingress() -> None:
    """A30 and A36: ALB annotations only for className alb; nginx rate limit behind a flag."""
    nginx = annotations_of(render("ci"))
    if nginx.get("nginx.ingress.kubernetes.io/limit-rps") != "10":
        raise AssertionError(f"default nginx annotations lack limit-rps 10: {nginx}")
    if any(key.startswith("alb.ingress.kubernetes.io/") for key in nginx):
        raise AssertionError(f"ALB annotations rendered for className nginx: {nginx}")
    off = annotations_of(render("ci", "--set", "ingress.rateLimit.enabled=false"))
    if "nginx.ingress.kubernetes.io/limit-rps" in off:
        raise AssertionError("limit-rps rendered with ingress.rateLimit.enabled=false")
    alb = annotations_of(render("ci", "--set", "ingress.className=alb"))
    expected = {
        "alb.ingress.kubernetes.io/scheme": "internal",
        "alb.ingress.kubernetes.io/target-type": "ip",
        "alb.ingress.kubernetes.io/listen-ports": '[{"HTTPS":443}]',
        "alb.ingress.kubernetes.io/healthcheck-path": "/api/health",
    }
    for key, value in expected.items():
        if alb.get(key) != value:
            raise AssertionError(f"className alb: {key} is {alb.get(key)!r}, expected {value!r}")
    if not str(alb.get("alb.ingress.kubernetes.io/certificate-arn", "")).startswith("arn:aws:acm:"):
        raise AssertionError(f"className alb: no certificate-arn annotation: {alb}")
    if "nginx.ingress.kubernetes.io/limit-rps" in alb:
        raise AssertionError("className alb: the nginx limit-rps annotation is rendered")


def check_dns() -> None:
    """A32: dnsCidrs adds an ipBlock rule on UDP and TCP 53; the kube-dns rule stays."""
    rules = one(render("ci"), "NetworkPolicy")["spec"]["egress"]
    if len(rules) != 2:
        raise AssertionError(f"expected 2 egress rules by default (kube-dns, 443), found {len(rules)}")
    kube_dns = rules[0]
    if "namespaceSelector" not in kube_dns["to"][0] or not dns_ports_ok(kube_dns):
        raise AssertionError(f"the first egress rule is not the kube-dns rule: {kube_dns}")
    rules = one(render("ci", "--set-json", 'networkPolicy.dnsCidrs=["169.254.20.10/32"]'), "NetworkPolicy")["spec"]["egress"]
    if len(rules) != 3:
        raise AssertionError(f"expected 3 egress rules with one dnsCidr, found {len(rules)}")
    extra = [rule for rule in rules if any(peer.get("ipBlock", {}).get("cidr") == "169.254.20.10/32" for peer in rule["to"])]
    if len(extra) != 1 or not dns_ports_ok(extra[0]):
        raise AssertionError(f"no egress rule for 169.254.20.10/32 on UDP and TCP 53: {rules}")
    if rules[0] != kube_dns:
        raise AssertionError("the kube-dns rule changed when dnsCidrs was set")


CHECKS = [
    check_empty_egress_fails_with_its_message,
    check_names,
    check_identity_gate,
    check_region,
    check_probes_and_shutdown,
    check_ingress,
    check_dns,
]


def main() -> int:
    failed = 0
    for check in CHECKS:
        try:
            check()
        except AssertionError as err:
            failed += 1
            print(f"FAIL {check.__name__}: {err}")
        else:
            print(f"ok   {check.__name__}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
