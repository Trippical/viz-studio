# AWS setup for viz-site

Everything here uses placeholders: replace `REPLACE_ME-viz-bucket`, the
account id `123456789012`, `REPLACE_ME-region`, `REPLACE_ME-key-id` and
`vpce-REPLACE_ME` with your own values. Never commit real ones back to the
repo.

## 1. The bucket baseline (spec 12.5)

Create one bucket for viz-site, then set:

- **Block Public Access**: all four settings on.
- **Default encryption**: SSE-KMS with a customer-managed key, Bucket Key
  enabled. The key's own key policy must also allow the `viz-site-server` role `kms:Decrypt` and the `viz-site-publisher` role `kms:Decrypt` and `kms:GenerateDataKey`; IAM policies alone are not enough for a customer-managed key.
- **Versioning**: enabled, with a lifecycle rule
  `NoncurrentVersionExpiration` of 30 days, so an overwritten or deleted
  chart can be recovered for a month.
- **Logging**: S3 server access logging to a separate log bucket, or
  CloudTrail data events for this bucket.
- **S3 gateway VPC endpoint**: the bucket policy needs its id. Create the
  endpoint in the cluster's VPC before you apply the policy, and record its
  `vpce-...` id (`docs/work-setup.md`, step 5, has the command).
- **Bucket policy**: `bucket-policy.json`. It denies plain HTTP; denies
  reads that do not come through the cluster's S3 VPC endpoint, except for
  the publisher role, because publishers run `viz publish` from their own
  machines; and denies `s3:PutObject`, `s3:DeleteObject` and
  `s3:DeleteObjectVersion` to every principal except the publisher role, so
  no other role in the account can change what the site shows or erase an
  object's history, whatever its own IAM policy allows. Nobody
  else, including administrators, can read objects from outside the VPC
  endpoint, or write or delete objects at all; for break-glass access, edit
  the bucket policy first. If publishers sign in with a different role (for
  example an AWS SSO role), add its ARN to both exemptions.

## 2. Roles

| Role | Policy | Who uses it |
|---|---|---|
| `viz-site-server` | `server-policy.json` (list and read under `viz/`, KMS decrypt) | The pods, through IRSA. Never the node role. |
| `viz-site-publisher` | `publisher-policy.json` (also put and delete under `viz/`, KMS encrypt) | People and agents running `viz publish` and `viz move`. |

If `VIZ_ROOT_PREFIX` is not `viz/`, change `viz/` in both policies.

For IRSA, the server role's trust policy allows the cluster's OIDC provider
for one service account in one namespace, so choose the namespace and the
Helm release name before you create the role. The chart names the service
account after the release (`helm install viz-site ...` gives `viz-site`;
another release name `x` gives `x-viz-site`), or uses the Helm value
`serviceAccount.name` when you set it. With namespace `viz` and release
`viz-site` the trust policy is:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"Federated": "arn:aws:iam::123456789012:oidc-provider/oidc.eks.REPLACE_ME-region.amazonaws.com/id/REPLACE_ME"},
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "oidc.eks.REPLACE_ME-region.amazonaws.com/id/REPLACE_ME:sub": "system:serviceaccount:viz:viz-site",
          "oidc.eks.REPLACE_ME-region.amazonaws.com/id/REPLACE_ME:aud": "sts.amazonaws.com"
        }
      }
    }
  ]
}
```

Put the role ARN in the Helm value `serviceAccount.roleArn`.

`s3:ListBucket` is granted on the whole bucket without a prefix condition:
S3 needs it to answer 404 rather than 403 for a missing key, and the bucket
holds only viz-site data. If you share the bucket, add a prefix condition
and check that missing keys still return 404.

## 3. What the site does with S3

The server only lists, heads and gets objects under the root prefix. The
`viz` CLI also puts, deletes and copies (`viz move`). Neither touches any
other prefix or bucket.
