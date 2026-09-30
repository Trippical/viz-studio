"""docs/work-setup.md must stay true to the code: every setting, every command, every file it names."""
import argparse
import re
from pathlib import Path

from viz.config import Settings
from viz.publish.cli import build_parser

REPO = Path(__file__).resolve().parents[1]
GUIDE = REPO / "docs" / "work-setup.md"


def _text() -> str:
    return GUIDE.read_text(encoding="utf-8")


def test_every_setting_is_documented():
    text = _text()
    for field in Settings.model_fields:
        assert f"VIZ_{field.upper()}" in text, f"VIZ_{field.upper()} is not documented"


def test_databricks_variables_are_documented():
    text = _text()
    for name in ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID"):
        assert name in text, name


def test_every_viz_command_named_exists():
    parser = build_parser()
    commands = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction)).choices
    for name in re.findall(r"\bviz ([a-z][a-z-]*)", _text()):
        assert name in commands, f"docs/work-setup.md names `viz {name}`"


def test_every_repo_path_named_exists():
    # web/ is left out on purpose: web/dist only exists after a build.
    for path in re.findall(r"`((?:deploy|docs|skills|tests)/[A-Za-z0-9_./-]+)`", _text()):
        assert (REPO / path).exists(), path


def test_the_guide_covers_the_real_infrastructure_checks():
    text = _text()
    for phrase in ("VIZ_INTEGRATION=1", "VIZ_IT_S3_BUCKET", "tests/publish/test_query_integration.py",
                   "tests/storage/test_s3_integration.py", "viz install-skill", "helm install", "Genie Code",
                   "AWS_REGION", "docker push <registry>/viz-site:0.1.0", "123456789012", "VIZ_IT_S3_PREFIX",
                   "AWS_PROFILE", "role_session_name", "egressCidrs", "VIZ_AUTHOR"):
        assert phrase in text, phrase


def test_the_guide_covers_the_hardening_steps():
    text = _text()
    for phrase in (
        "kubectl create namespace viz",
        "create-vpc-endpoint",
        "system:serviceaccount:",
        "VIZ_IT_S3_PREFIX=viz/_scratch/",
        "VIZ_ROOT_PREFIX=viz/_scratch/",
        "aws s3 rm s3://your-viz-bucket/viz/_scratch/ --recursive",
        "VIZ_REQUIRE_IDENTITY",
        "requireIdentity",
        "401",
        "ingress.rateLimit.enabled",
        "Pods never call KMS",
        "helm install viz-site deploy/helm/viz-site -f my-values.yaml -n viz",
        "check that the folder tree loads",
    ):
        assert phrase in text, phrase
    # A35: the dead cross-reference is gone, and the steps are in dependency order.
    assert "Author on S3" not in text
    assert text.index("kubectl create namespace viz") < text.index("create-vpc-endpoint") < text.index("vpce-REPLACE_ME")
    assert text.index("viz publish .viz-staging/charts/smoke/first-chart") < text.index("aws s3 rm")
    # The smoke chart lives under the scratch prefix now, never on the real site.
    assert "/c/smoke/first-chart" not in text


def test_the_guide_exports_both_region_variables():
    # C4: boto3 reads AWS_DEFAULT_REGION; the guide sets it next to AWS_REGION everywhere it sets a region.
    text = _text()
    exports = [line for line in text.splitlines() if line.startswith("export ") and "AWS_REGION=" in line]
    assert exports
    for line in exports:
        assert "AWS_DEFAULT_REGION=" in line, line


def _section(text: str, heading: str) -> str:
    """The body of one "## " section, up to the next "## " heading."""
    start = text.index(f"\n## {heading}\n")
    end = text.find("\n## ", start + 1)
    return text[start:] if end == -1 else text[start:end]


def test_deploy_decides_every_setting_before_the_install():
    # C2 and C3: everything the install needs is decided in the step that runs it; later steps upgrade with -f.
    deploy = _section(_text(), "7. Deploy")
    install = deploy.index("helm install viz-site deploy/helm/viz-site -f my-values.yaml -n viz")
    for phrase in (
        "networkPolicy.ingressCidrs",
        "kubernetes.io/role/internal-elb",
        "networkPolicy.ingressControllerNamespace",
        "ingress.rateLimit.enabled: false",
        "requireIdentity: false",
        "ingress.allowedSourceCidrs",
    ):
        assert phrase in deploy[:install], phrase
    assert "--set requireIdentity=false" not in deploy
    upgrade = deploy.index("helm upgrade viz-site deploy/helm/viz-site -f my-values.yaml -n viz")
    assert install < upgrade
    assert deploy.count("helm install") == 1
    # requireIdentity is already true at install; the later step only undoes the smoke-test choice.
    assert "Turn the identity gate on." not in deploy
    assert "requireIdentity: true" in deploy[install:upgrade]


def test_deploy_locks_the_load_balancer_before_the_install():
    # C1: a forged identity header is only stopped if nobody but the SSO proxy reaches the load balancer.
    deploy = _section(_text(), "7. Deploy")
    install = deploy.index("helm install viz-site deploy/helm/viz-site -f my-values.yaml -n viz")
    flat = " ".join(deploy[:install].split())
    for phrase in (
        "overwrite",
        "internal load balancer",
        "nginx.ingress.kubernetes.io/auth-url",
        "nginx.ingress.kubernetes.io/auth-response-headers",
        "oauth2-proxy",
        "security group",
    ):
        assert phrase in flat, phrase


def test_deploy_keeps_the_client_ip_for_the_nginx_source_range():
    # Fix round 1, item 2: externalTrafficPolicy Local alone does not keep the client IP on AWS.
    deploy = " ".join(_section(_text(), "7. Deploy").split())
    for phrase in (
        "externalTrafficPolicy: Local",
        "Network Load Balancer",
        "Classic Load Balancer",
        "preserve_client_ip.enabled=true",
        "proxy protocol",
        "controller.service.loadBalancerSourceRanges",
        "Never widen `ingress.allowedSourceCidrs` to the VPC",
    ):
        assert phrase in deploy, phrase


def test_deploy_keeps_other_pods_off_the_alb_subnets():
    # Fix round 1, item 1: ALB subnets shared with pods would let any pod reach viz-site on 8000.
    deploy = " ".join(_section(_text(), "7. Deploy").split())
    for phrase in (
        "dedicated subnets",
        "alb.ingress.kubernetes.io/subnets",
        "Security Groups for Pods",
    ):
        assert phrase in deploy, phrase


def test_deploy_checks_a_forged_header_sent_straight_to_a_pod():
    deploy = _section(_text(), "7. Deploy")
    check = deploy.index("kubectl run forge-test")
    assert deploy.index("helm upgrade viz-site deploy/helm/viz-site -f my-values.yaml -n viz") < check
    tail = deploy[check:]
    assert 'http://<pod ip>:8000/api/tree' in tail
    assert '-H "X-Forwarded-Email: someone@example.com"' in tail
    assert "kubectl get pods -n viz -o wide" in deploy


def test_what_you_need_names_the_cluster_prerequisites():
    # C6
    need = " ".join(_section(_text(), "What you need").split())
    for phrase in (
        "AWS CLI v2",
        "ingress-nginx",
        "AWS Load Balancer Controller",
        "kubernetes.io/role/internal-elb",
        "enableNetworkPolicy=true",
        "Calico",
        "Cilium",
        "OIDC provider",
        "same region as the cluster",
    ):
        assert phrase in need, phrase


def test_step_5_creates_every_aws_prerequisite_in_order():
    # C5
    step = _section(_text(), "5. Create the AWS resources")
    order = [
        "kubectl create namespace viz",
        "aws eks describe-cluster --name <cluster> --query cluster.identity.oidc.issuer --output text",
        "eksctl utils associate-iam-oidc-provider",
        "create-vpc-endpoint --vpc-endpoint-type Gateway",
        "aws ec2 get-managed-prefix-list-entries --prefix-list-id pl-",
        "--service-name com.amazonaws.<region>.sts",
        "--private-dns-enabled",
        "aws ecr create-repository --repository-name viz-site",
        "deploy/aws/README.md",
        "role_session_name = viz-publisher",
    ]
    positions = [step.index(phrase) for phrase in order]
    assert positions == sorted(positions), order


def test_viz_local_dir_row_says_publish_and_move_refuse_without_it():
    # C9: the server still defaults to ./sample-bucket; publish and move do not.
    [row] = [line for line in _text().splitlines() if line.startswith("| `VIZ_LOCAL_DIR` |")]
    assert "`./sample-bucket` for the server" in row
    assert "`viz publish` and `viz move` refuse to run without it" in row


def test_step_7_logs_in_to_ecr_before_the_push():
    deploy = _section(_text(), "7. Deploy")
    login = deploy.index("aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin")
    assert login < deploy.index("docker push <registry>/viz-site:0.1.0")
