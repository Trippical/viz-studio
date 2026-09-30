# AWS setup for viz-site

Everything here uses placeholders: replace `REPLACE_ME-viz-bucket`, the
account id `123456789012`, `REPLACE_ME-region`, `REPLACE_ME-key-id` and
`vpce-REPLACE_ME` with your own values. Never commit real ones back to the
repo.

Copy the JSON files in this folder to a working folder outside the repo,
fill in the placeholders there, and run the commands below from that folder.
Do the sections in order: later sections need values from earlier ones.

## 1. The KMS key

Create a customer-managed key for the bucket's default encryption:

```
aws kms create-key --description "viz-site bucket key" --query KeyMetadata.KeyId --output text
```

The output is the key id. Put it in place of `REPLACE_ME-key-id` in your
copies of `server-policy.json` and `publisher-policy.json`. The key's ARN is
`arn:aws:kms:<region>:<account id>:key/<key id>`. The key gets its own key
policy in section 4, once both roles exist: KMS refuses a key policy that
names a role that does not exist yet.

## 2. The bucket baseline (spec 12.5)

Create one bucket for viz-site, in the same region as the cluster, then set:

- **Block Public Access**: all four settings on.
- **Default encryption**: SSE-KMS with the key from section 1, Bucket Key
  enabled.
- **Versioning**: enabled, with a lifecycle rule
  `NoncurrentVersionExpiration` of 30 days, so an overwritten or deleted
  chart can be recovered for a month.
- **Logging**: S3 server access logging to a separate log bucket, or
  CloudTrail data events for this bucket.
- **S3 gateway VPC endpoint**: the bucket policy needs its id. Create the
  endpoint in the cluster's VPC before you apply the policy, and record its
  `vpce-...` id (`docs/work-setup.md`, step 5, has the command).
- **Bucket policy**: `bucket-policy.json`. It denies plain HTTP; denies
  reads (including reads of old versions) that do not come through the
  cluster's S3 VPC endpoint, except for the publisher role, because
  publishers run `viz publish` from their own machines; and denies
  `s3:PutObject`, `s3:DeleteObject` and `s3:DeleteObjectVersion` to every
  principal except the publisher role, so no other role in the account can
  change what the site shows or erase an object's history, whatever its own
  IAM policy allows. Nobody else, including administrators, can read objects
  from outside the VPC endpoint, or write or delete objects at all; for
  break-glass access, edit the bucket policy first. If publishers sign in
  with a different role (for example an AWS SSO role), add its ARN to both
  exemptions.

## 3. Roles

| Role | Policy | Who uses it |
|---|---|---|
| `viz-site-server` | `server-policy.json` (list and read under `viz/`, KMS decrypt) | The pods, through IRSA. Never the node role. |
| `viz-site-publisher` | `publisher-policy.json` (also put and delete under `viz/`, KMS encrypt) | People and agents running `viz publish` and `viz move`. |

If `VIZ_ROOT_PREFIX` is not `viz/`, change `viz/` in both policies.

### The server role

For IRSA, the server role's trust policy allows the cluster's OIDC provider
for one service account in one namespace, so choose the namespace and the
Helm release name before you create the role. The chart names the service
account after the release (`helm install viz-site ...` gives `viz-site`;
another release name `x` gives `x-viz-site`), or uses the Helm value
`serviceAccount.name` when you set it. With namespace `viz` and release
`viz-site` the trust policy is below. Replace
`oidc.eks.REPLACE_ME-region.amazonaws.com/id/REPLACE_ME` with the cluster's
OIDC issuer without `https://` (`docs/work-setup.md`, step 5, shows how to
find it), and save it as `server-trust-policy.json`:

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

Create the role and attach its policy:

```
aws iam create-role --role-name viz-site-server --assume-role-policy-document file://server-trust-policy.json
aws iam put-role-policy --role-name viz-site-server --policy-name viz-site-server --policy-document file://server-policy.json
```

Put the role ARN (`arn:aws:iam::<account id>:role/viz-site-server`) in the
Helm value `serviceAccount.roleArn`.

### The publisher role

`publisher-trust-policy.json` says who may assume the publisher role. It
trusts your own account, limited by `aws:PrincipalArn` to the roles or users
you list. The example lists an AWS SSO permission set named
`REPLACE_ME-publishers`; SSO roles have generated names, hence the `*`
wildcards. List the role of each group of people or agents that publishes,
for example `arn:aws:iam::123456789012:role/REPLACE_ME-analyst-role`. Those
principals also need `sts:AssumeRole` on the publisher role in their own
IAM policy.

```
aws iam create-role --role-name viz-site-publisher --assume-role-policy-document file://publisher-trust-policy.json
aws iam put-role-policy --role-name viz-site-publisher --policy-name viz-site-publisher --policy-document file://publisher-policy.json
```

`s3:ListBucket` is granted on the whole bucket without a prefix condition:
S3 needs it to answer 404 rather than 403 for a missing key, and the bucket
holds only viz-site data. If you share the bucket, add a prefix condition
and check that missing keys still return 404.

## 4. The key policy

`key-policy.json` keeps the account's administrators able to manage the key
(the first statement: without it nobody can change the key policy again),
lets the `viz-site-server` role `kms:Decrypt`, and lets the
`viz-site-publisher` role `kms:Decrypt` and `kms:GenerateDataKey`. Apply it
with the key id from section 1:

```
aws kms put-key-policy --key-id <key id> --policy-name default --policy file://key-policy.json
```

## 5. What the site does with S3

The server only lists, heads and gets objects under the root prefix. The
`viz` CLI also puts, deletes and copies (`viz move`). Neither touches any
other prefix or bucket.
