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
- **Bucket policy**: `bucket-policy.json`. It denies plain HTTP, and denies
  reads that do not come through the cluster's S3 VPC endpoint, except for
  the publisher role, because publishers run `viz publish` from their own
  machines. Nobody else, including administrators, can read objects from outside the VPC endpoint; for break-glass access, edit the bucket policy first.

## 2. Roles

| Role | Policy | Who uses it |
|---|---|---|
| `viz-site-server` | `server-policy.json` (list and read under `viz/`, KMS decrypt) | The pods, through IRSA. Never the node role. |
| `viz-site-publisher` | `publisher-policy.json` (also put and delete under `viz/`, KMS encrypt) | People and agents running `viz publish` and `viz move`. |

If `VIZ_ROOT_PREFIX` is not `viz/`, change `viz/` in both policies.

For IRSA, the server role's trust policy allows the cluster's OIDC provider
for the service account `viz-site` in the release namespace. Put the role
ARN in the Helm value `serviceAccount.roleArn`.

`s3:ListBucket` is granted on the whole bucket without a prefix condition:
S3 needs it to answer 404 rather than 403 for a missing key, and the bucket
holds only viz-site data. If you share the bucket, add a prefix condition
and check that missing keys still return 404.

## 3. What the site does with S3

The server only lists, heads and gets objects under the root prefix. The
`viz` CLI also puts, deletes and copies (`viz move`). Neither touches any
other prefix or bucket.
