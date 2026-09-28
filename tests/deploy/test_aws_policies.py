import json
import re
from pathlib import Path

AWS = Path(__file__).resolve().parents[2] / "deploy" / "aws"


def _policy(name: str) -> dict:
    return json.loads((AWS / name).read_text(encoding="utf-8"))


def _actions(policy: dict) -> set[str]:
    out = set()
    for statement in policy["Statement"]:
        if statement["Effect"] == "Allow":
            actions = statement["Action"]
            out.update([actions] if isinstance(actions, str) else actions)
    return out


def test_server_policy_is_read_only():
    assert _actions(_policy("server-policy.json")) == {"s3:ListBucket", "s3:GetObject", "kms:Decrypt"}


def test_publisher_policy_can_write_but_not_administer():
    actions = _actions(_policy("publisher-policy.json"))
    assert actions == {"s3:ListBucket", "s3:GetObject", "s3:PutObject", "s3:DeleteObject", "kms:Decrypt", "kms:GenerateDataKey"}
    assert not any(a.endswith("*") for a in actions)


def test_object_access_is_limited_to_the_root_prefix():
    for name in ("server-policy.json", "publisher-policy.json"):
        for statement in _policy(name)["Statement"]:
            actions = statement["Action"]
            actions = [actions] if isinstance(actions, str) else actions
            if any(a in ("s3:GetObject", "s3:PutObject", "s3:DeleteObject") for a in actions):
                assert statement["Resource"] == "arn:aws:s3:::REPLACE_ME-viz-bucket/viz/*", name
            if "s3:ListBucket" in actions:
                assert statement["Condition"]["StringLike"]["s3:prefix"] == ["viz/", "viz/*"], name


def test_bucket_policy_denies_plain_http():
    statements = _policy("bucket-policy.json")["Statement"]
    deny = [s for s in statements if s["Effect"] == "Deny" and "aws:SecureTransport" in json.dumps(s)]
    assert deny and deny[0]["Condition"] == {"Bool": {"aws:SecureTransport": "false"}}


def test_vpce_deny_exempts_the_publisher_role():
    statements = _policy("bucket-policy.json")["Statement"]
    vpce = [s for s in statements if "aws:SourceVpce" in json.dumps(s)]
    assert len(vpce) == 1
    condition = vpce[0]["Condition"]
    assert condition["StringNotEquals"]["aws:SourceVpce"] == "vpce-REPLACE_ME"
    assert condition["ArnNotLike"]["aws:PrincipalArn"] == ["arn:aws:iam::123456789012:role/viz-site-publisher"]


def test_only_placeholder_accounts_and_names():
    for path in AWS.glob("*"):
        text = path.read_text(encoding="utf-8")
        for account in re.findall(r"\b\d{12}\b", text):
            assert account == "123456789012", f"{path.name}: {account}"
        assert "DATABRICKS" not in text


def test_readme_covers_the_bucket_baseline():
    text = (AWS / "README.md").read_text(encoding="utf-8")
    for phrase in ("Block Public Access", "SSE-KMS", "Versioning", "NoncurrentVersionExpiration", "CloudTrail", "IRSA", "node role"):
        assert phrase in text, phrase
