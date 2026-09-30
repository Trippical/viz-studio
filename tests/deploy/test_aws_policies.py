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
                # Granted on the whole bucket, with no prefix condition: S3 only answers
                # 404 (rather than 403) for a missing key when the caller has an
                # unconditioned s3:ListBucket, and the bucket is dedicated to viz-site.
                assert statement["Resource"] == "arn:aws:s3:::REPLACE_ME-viz-bucket", name
                assert "Condition" not in statement, name


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


def test_readme_warns_about_the_key_policy_and_break_glass():
    text = (AWS / "README.md").read_text(encoding="utf-8")
    assert "key policy" in text
    assert "break-glass" in text


def _statement(sid: str) -> dict:
    found = [s for s in _policy("bucket-policy.json")["Statement"] if s.get("Sid") == sid]
    assert len(found) == 1, sid
    return found[0]


def test_writes_are_denied_to_everyone_but_the_publisher_role():
    deny = _statement("DenyWritesExceptThePublisherRole")
    assert deny["Effect"] == "Deny"
    assert deny["Principal"] == "*"
    # DeleteObjectVersion too: the bucket is versioned, and deleting a version is a write.
    assert sorted(deny["Action"]) == ["s3:DeleteObject", "s3:DeleteObjectVersion", "s3:PutObject"]
    assert deny["Resource"] == "arn:aws:s3:::REPLACE_ME-viz-bucket/*"
    assert deny["Condition"] == {
        "ArnNotLike": {"aws:PrincipalArn": ["arn:aws:iam::123456789012:role/viz-site-publisher"]}
    }


def test_read_deny_covers_old_versions_too():
    # C7: the bucket is versioned; without GetObjectVersion an old version could be read from anywhere.
    deny = _statement("DenyReadsOutsideTheVpcEndpointExceptPublishers")
    assert sorted(deny["Action"]) == ["s3:GetObject", "s3:GetObjectVersion", "s3:ListBucket"]


def test_write_deny_exempts_the_same_publisher_as_the_read_deny():
    write = _statement("DenyWritesExceptThePublisherRole")["Condition"]["ArnNotLike"]
    read = _statement("DenyReadsOutsideTheVpcEndpointExceptPublishers")["Condition"]["ArnNotLike"]
    assert write == read


def test_readme_explains_the_write_deny_and_endpoint_order():
    text = " ".join((AWS / "README.md").read_text(encoding="utf-8").split())
    assert ("denies `s3:PutObject`, `s3:DeleteObject` and `s3:DeleteObjectVersion` to every principal "
            "except the publisher role") in text
    assert text.index("S3 gateway VPC endpoint") < text.index("**Bucket policy**")


def test_readme_shows_the_irsa_trust_policy():
    text = (AWS / "README.md").read_text(encoding="utf-8")
    assert "system:serviceaccount:viz:viz-site" in text
    assert "sts:AssumeRoleWithWebIdentity" in text
    assert "choose the namespace and the\nHelm release name before you create the role" in text
