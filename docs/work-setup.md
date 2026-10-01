# Setting up viz-site on a work machine

This guide takes a fresh clone to a working site on your company's AWS
account, with charts published from Databricks. Steps 1 to 4 need only your
laptop; steps 5 to 7 need the company's AWS account and Databricks
workspace.

The command snippets below use bash; on Windows PowerShell, use
`$env:NAME = "value"` instead of `export NAME=value`.

## What you need

- Python 3.11 and Git.
- Node.js 24 (only to build the front end outside Docker).
- Docker, `kubectl` and Helm 3 for the deployment.
- AWS CLI v2, signed in to the company account with rights to create IAM
  roles, KMS keys, VPC endpoints and ECR repositories. `eksctl` is
  optional; step 5 uses it for one command and shows the AWS CLI
  alternative.
- An EKS cluster that already has:
  - an ingress controller: either ingress-nginx with its controller Service
    on an internal load balancer
    (`service.beta.kubernetes.io/aws-load-balancer-scheme: internal`), or
    the AWS Load Balancer Controller with the private subnets tagged
    `kubernetes.io/role/internal-elb=1`;
  - a NetworkPolicy engine: the Amazon VPC CNI with network policy turned
    on (`enableNetworkPolicy=true`), or Calico or Cilium. Without one the
    chart's NetworkPolicy is silently ignored;
  - an IAM OIDC provider for IRSA, or the rights to add one (step 5 checks
    and creates it).
- The bucket must be in the same region as the cluster: the S3 gateway
  endpoint in step 5 reaches only buckets in its own region.
- A Databricks personal access token and a SQL warehouse id, for `viz query`.
- AWS credentials that can assume the publisher role, for `viz publish`.
- An AWS region for the bucket, set with both `AWS_DEFAULT_REGION` (read by
  the `viz` CLI through boto3) and `AWS_REGION`, or with `aws configure`.

## 1. Clone and install the CLI

```
git clone https://github.com/Trippical/viz-studio.git viz-site
cd viz-site
python3.11 -m venv .venv
.venv/bin/python -m pip install -e ".[databricks,dev]"
.venv/bin/viz --version
```

On Windows use `py -3.11 -m venv .venv` and `.venv\Scripts\...`. `[dev]` is
included because step 6 runs `pytest` to prove the real integrations.

## 2. Settings

Everything is configured with environment variables. The server and the CLI
share the `VIZ_*` ones.

| Variable | Default | Used by | What it does |
|---|---|---|---|
| `VIZ_STORAGE` | `local` | both | `local` (a folder) or `s3`. `viz publish` and `viz move` refuse to run unless it is set explicitly |
| `VIZ_S3_BUCKET` | none | both | Bucket name when `VIZ_STORAGE=s3` |
| `VIZ_ROOT_PREFIX` | `viz/` | both | Key prefix everything lives under |
| `VIZ_LOCAL_DIR` | `./sample-bucket` for the server; none for publishing | both | Folder used when `VIZ_STORAGE=local`. With `VIZ_STORAGE=local`, `viz publish` and `viz move` refuse to run without it, so they never write into the default `./sample-bucket` |
| `VIZ_TREE_TTL_SECONDS` | `60` | server | How long the folder tree is cached |
| `VIZ_ALLOWED_HOSTS` | `localhost,127.0.0.1` | server | Host names the site answers to; anything else gets 400, except `GET` and `HEAD /api/health` (load balancer checks send the pod IP). Must be set in deployment |
| `VIZ_AUTH_HEADER` | `X-Forwarded-Email` | server | Identity header set by the SSO proxy. Logged with every request; required on every request when `VIZ_REQUIRE_IDENTITY` is true |
| `VIZ_REQUIRE_IDENTITY` | `false` | server | When true, every request except `GET` and `HEAD /api/health` without the `VIZ_AUTH_HEADER` header gets 401. The Helm chart sets it to true (value `requireIdentity`); local runs and `viz preview` leave it off |
| `VIZ_MAX_DOCUMENT_BYTES` | `1048576` | server | Largest chart.json or dashboard file served |
| `VIZ_WEB_DIST` | `./web/dist` | server | Built front end |
| `VIZ_HOST` | `127.0.0.1` | server | Bind address (`0.0.0.0` in the container) |
| `VIZ_PORT` | `8000` | server | Port |
| `VIZ_AUTHOR` | none | CLI | Author when there is no Databricks login (see below) |
| `VIZ_QUERY_DENY` | empty | CLI | Comma-separated catalogs or `catalog.schema` that `viz query` refuses. A guard against accidents, not a permission boundary |
| `VIZ_PII_PATTERN` | names like email, ssn, phone | CLI | Column names that trigger a personal-data warning |
| `VIZ_STAGING_DIR` | `./.viz-staging` | CLI | Where charts are staged before publishing |
| `DATABRICKS_HOST` | none | CLI only | Workspace URL, for `viz query` |
| `DATABRICKS_TOKEN` | none | CLI only | Personal access token. Keep it in your shell or a secret store, never in a file in the repo |
| `DATABRICKS_WAREHOUSE_ID` | none | CLI only | SQL warehouse id, or pass `--warehouse` |

Author (attribution, not a permission check): when `DATABRICKS_HOST`,
`DATABRICKS_TOKEN` and `DATABRICKS_WAREHOUSE_ID` are all set, every command
(`viz query`, `viz stage`, `viz new-dashboard`, `viz pull-dashboard`) stamps
your Databricks login and `viz validate` confirms it with Databricks. A chart
from `viz query --warehouse <id>` also counts: validation asks the warehouse
the query ran on. Otherwise the CLI uses `VIZ_AUTHOR`, then your AWS identity,
then `<user>@local`; no command requires `DATABRICKS_WAREHOUSE_ID`.

Without all three Databricks variables, set `VIZ_AUTHOR` to your email, or
keep a fixed `role_session_name` in your AWS profile; otherwise the AWS
identity changes between commands and validation reports an author mismatch.
`viz stage` without Databricks falls back to the AWS caller ARN, which
includes the role session name; without a fixed `role_session_name`, every
process gets a new one.

Service principal: if the principal has a personal access token, put it in
`DATABRICKS_TOKEN` and everything works; `viz query` and `viz validate` both
see the principal's id, so charts are authored by the principal rather than
a person. OAuth machine-to-machine credentials (a client id and secret) are
not supported yet.

Files dropped in S3: `viz stage --from` reads a local file, so copy the file
down first (`aws s3 cp s3://your-drop-bucket/path/rows.parquet .`) and stage
the copy. Staging straight from an `s3://` path is not supported yet.

## 3. Try it locally

With Docker:

```
docker compose up --build
```

Then open http://127.0.0.1:8000. It serves the synthetic `sample-bucket`,
including the chart gallery at `/d/examples/gallery`.

Running the image without compose, set the storage yourself: `VIZ_STORAGE`,
`VIZ_LOCAL_DIR` (or `VIZ_S3_BUCKET`) and `VIZ_ALLOWED_HOSTS`. With none set,
the site starts but shows an empty tree.

Without Docker, build the front end once and run the server:

```
cd web
npm ci
node node_modules/esbuild/install.js
npm run build
cd ..
VIZ_WEB_DIST=web/dist .venv/bin/viz-server
```

## 4. Install the skill

```
.venv/bin/viz install-skill
```

This copies the `publish-viz` skill to `~/.claude/skills/publish-viz/`, where
Claude Code finds it. For Databricks Genie Code, the skill folder location is
not confirmed yet: find where your workspace loads skills from and run
`viz install-skill --dest <that folder>`. The skill teaches the whole path
below; its source is `skills/publish-viz/SKILL.md`.

## 5. Create the AWS resources

Do these in order: later items need values from earlier ones.

1. **Choose the namespace and the Helm release name.** The IRSA trust policy
   names the pods' service account as
   `system:serviceaccount:<namespace>:<service account>`, so both must be
   fixed before you create the server role. This guide uses the namespace
   `viz` and the release `viz-site`, which gives the service account
   `viz-site` (another release name `x` gives `x-viz-site`; the Helm value
   `serviceAccount.name` overrides it). Create the namespace now:
   `kubectl create namespace viz`
2. **Find the cluster's OIDC issuer and register it with IAM.** IRSA needs
   an IAM OIDC provider for the cluster. Print the issuer (replace
   `<cluster>` with the EKS cluster name):

   ```
   aws eks describe-cluster --name <cluster> --query cluster.identity.oidc.issuer --output text
   ```

   It prints `https://oidc.eks.<region>.amazonaws.com/id/<ID>`. Write down
   the part after `https://`; the server role's trust policy in item 6 needs
   it. Then list the providers IAM already has:
   `aws iam list-open-id-connect-providers`. If one of the ARNs ends in the
   same `<ID>`, skip to item 3. Otherwise create the provider:

   ```
   eksctl utils associate-iam-oidc-provider --cluster <cluster> --region <region> --approve
   ```

   Without `eksctl`, the AWS CLI does the same (use the full `https://` URL
   printed above):
   `aws iam create-open-id-connect-provider --url <issuer URL> --client-id-list sts.amazonaws.com`
3. **Create the S3 gateway VPC endpoint** in the cluster's VPC, attached to
   the route tables of the subnets the nodes run in, and write down its id
   (`vpce-...`). The pods reach S3 through it, and the bucket policy in
   item 6 needs the id.

   ```
   aws ec2 create-vpc-endpoint --vpc-endpoint-type Gateway \
     --vpc-id <cluster vpc id> --service-name com.amazonaws.<region>.s3 \
     --route-table-ids <route table ids of the node subnets> \
     --query VpcEndpoint.VpcEndpointId --output text
   ```

   If the VPC already has an S3 gateway endpoint, use its id instead:
   `aws ec2 describe-vpc-endpoints --filters Name=service-name,Values=com.amazonaws.<region>.s3`

   A gateway endpoint has no IP address of its own: traffic to S3 goes to
   the addresses in the region's S3 prefix list. Turn that list into CIDRs.
   The first command prints the prefix list id (`pl-...`), the second its
   CIDRs:

   ```
   aws ec2 describe-managed-prefix-lists --filters Name=prefix-list-name,Values=com.amazonaws.<region>.s3 \
     --query "PrefixLists[0].PrefixListId" --output text
   aws ec2 get-managed-prefix-list-entries --prefix-list-id pl-<id from the line above> \
     --query "Entries[].Cidr" --output text
   ```

   Write the CIDRs down: they go in the Helm value
   `networkPolicy.egressCidrs` in step 7.
4. **Create the STS interface endpoint.** The pods get their IRSA
   credentials from STS, and the NetworkPolicy only lets them reach the
   addresses you list, so give STS a fixed place in the VPC. Private DNS
   needs the VPC settings "DNS hostnames" and "DNS resolution" on. First
   find the VPC's CIDR and create a security group that lets the VPC reach
   the endpoint on 443:

   ```
   aws ec2 describe-vpcs --vpc-ids <cluster vpc id> --query "Vpcs[0].CidrBlock" --output text
   aws ec2 create-security-group --group-name viz-site-sts-endpoint \
     --description "HTTPS from the VPC to the STS endpoint" \
     --vpc-id <cluster vpc id> --query GroupId --output text
   aws ec2 authorize-security-group-ingress --group-id <sg id from the line above> \
     --protocol tcp --port 443 --cidr <vpc cidr from the first line>
   ```

   Then create the endpoint in the node subnets, with private DNS on so
   `sts.<region>.amazonaws.com` resolves to it:

   ```
   aws ec2 create-vpc-endpoint --vpc-endpoint-type Interface \
     --vpc-id <cluster vpc id> --service-name com.amazonaws.<region>.sts \
     --subnet-ids <node subnet ids> --security-group-ids <sg id> \
     --private-dns-enabled --query VpcEndpoint.VpcEndpointId --output text
   ```

   If the VPC already has an STS interface endpoint, use it instead; this
   prints its subnet ids:
   `aws ec2 describe-vpc-endpoints --filters Name=vpc-id,Values=<cluster vpc id> Name=service-name,Values=com.amazonaws.<region>.sts --query "VpcEndpoints[0].SubnetIds" --output text`

   Record the CIDRs of the endpoint's subnets:

   ```
   aws ec2 describe-subnets --subnet-ids <the endpoint's subnet ids> --query "Subnets[].CidrBlock" --output text
   ```

   Write them down next to the S3 CIDRs from item 3: both go in
   `networkPolicy.egressCidrs` in step 7.
5. **Create the ECR repository** for the image:

   ```
   aws ecr create-repository --repository-name viz-site \
     --image-scanning-configuration scanOnPush=true \
     --query repository.repositoryUri --output text
   ```

   It prints `123456789012.dkr.ecr.<region>.amazonaws.com/viz-site` (with
   your account id and region). Write it down: it is the Helm value
   `image.repository` in step 7, and the part before `/viz-site` is the
   registry you log in to there.
6. **Create the KMS key, the bucket, the roles and the policies**:
   `deploy/aws/README.md`, in its order. That covers the KMS key, the bucket
   baseline, the bucket policy (put the id from item 3 in place of
   `vpce-REPLACE_ME`), the `viz-site-server` role with its IRSA trust policy
   (use the namespace and service account from item 1 and the issuer from
   item 2), the `viz-site-publisher` role with its trust policy, and the KMS
   key policy.
7. **Act as the publisher role on your laptop.** To run `viz publish` and
   `viz move`, add a profile that assumes `viz-site-publisher`, with a fixed
   `role_session_name`. A fixed session name keeps your AWS identity, and so
   the author stamped on charts you stage from files, the same from one
   command to the next.

   ```
   # ~/.aws/config
   [profile viz-publisher]
   role_arn = arn:aws:iam::123456789012:role/viz-site-publisher
   source_profile = default
   role_session_name = viz-publisher
   region = your-region
   ```

   Then `export AWS_PROFILE=viz-publisher` before running publisher commands.

   If your company signs in with AWS SSO, the SSO role is not
   `viz-site-publisher`; either assume the publisher role from it as above,
   or add your SSO role's ARN to both publisher exemptions in
   `deploy/aws/bucket-policy.json` (the read Deny and the write Deny). Only
   the publisher role can write to the bucket.

## 6. Prove the real integrations

Run these before anyone relies on the site. Each is skipped unless you opt
in, and neither ever runs in CI.

Databricks (runs `SELECT 1` on your warehouse):

```
export VIZ_INTEGRATION=1 DATABRICKS_HOST=... DATABRICKS_TOKEN=... DATABRICKS_WAREHOUSE_ID=...
.venv/bin/python -m pytest tests/publish/test_query_integration.py -v
```

S3 (writes, reads, copies and deletes two small objects under a throwaway
prefix; needs the publisher role's credentials). Point it at the scratch
prefix `viz/_scratch/`. The publisher policy covers it, and the site never
lists it: the site reads only `viz/charts/` and `viz/dashboards/`.

```
export VIZ_INTEGRATION=1 VIZ_IT_S3_BUCKET=your-viz-bucket VIZ_IT_S3_PREFIX=viz/_scratch/ AWS_REGION=your-region AWS_DEFAULT_REGION=your-region
.venv/bin/python -m pytest tests/storage/test_s3_integration.py -v
```

Then publish one real chart end to end, also under the scratch prefix, so
nothing appears on the real site:

```
export VIZ_STORAGE=s3 VIZ_S3_BUCKET=your-viz-bucket VIZ_ROOT_PREFIX=viz/_scratch/ AWS_REGION=your-region AWS_DEFAULT_REGION=your-region
echo "SELECT 'a' AS label, 1 AS value" > first.sql
.venv/bin/viz query --sql-file first.sql --id smoke/first-chart
.venv/bin/viz validate .viz-staging/charts/smoke/first-chart
.venv/bin/viz publish .viz-staging/charts/smoke/first-chart
aws s3 ls s3://your-viz-bucket/viz/_scratch/charts/smoke/first-chart/
```

The listing shows `chart.json` and one data file named
`data.<16 hex characters>.<format>`. Publishing the same id again is
refused with the current author and date; add `--force` to `viz publish`
only when you mean to replace it.

Clean up when you are done, and clear the scratch prefix before you publish
anything real:

```
aws s3 rm s3://your-viz-bucket/viz/_scratch/ --recursive
rm -rf .viz-staging/charts/smoke first.sql
unset VIZ_ROOT_PREFIX VIZ_IT_S3_PREFIX
```

Versioning keeps the deleted objects as noncurrent versions for 30 days (see
`deploy/aws/README.md`); that is expected. On PowerShell, clear a variable
with `Remove-Item Env:VIZ_ROOT_PREFIX`.

## 7. Deploy

1. **Build and push the image.** `<registry>` is the part of the repository
   URI from step 5, item 5, before `/viz-site`
   (`123456789012.dkr.ecr.<region>.amazonaws.com`). Log in, build and push:

   ```
   aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <registry>
   docker build --platform linux/amd64 -t <registry>/viz-site:0.1.0 .
   docker push <registry>/viz-site:0.1.0
   ```

   The chart has no `tls` block; TLS is terminated by the load balancer or
   the company SSO proxy in front of it.
2. **Fill in your values and install.** Copy
   `deploy/helm/viz-site/values.yaml` to `my-values.yaml` at the repo root
   (never commit the filled copy). Fill in every `REPLACE_ME`, `example.com`
   and `123456789012` value: `image.repository` is the repository URI from
   step 5, item 5; `networkPolicy.egressCidrs` lists the S3 and STS CIDRs
   from step 5, items 3 and 4; set `ingress.alb.certificateArn` if you set
   `ingress.className: alb`. Then
   make these four decisions in `my-values.yaml` before you install:

   a. **Who may reach the load balancer.** The identity gate trusts the
      `authHeader` header. Anyone who can reach the load balancer can send
      that header themselves and pass as any user. So both of these must
      hold:
      - Only the SSO proxy can reach the load balancer.
      - The proxy overwrites the header on every request (it sets it, it
        never appends to it or passes through a value the user sent).

      Layout 1, the default: the company SSO proxy in front of an internal
      load balancer. Users reach the proxy, and the proxy reaches the load
      balancer. Set `ingress.allowedSourceCidrs` to the proxy's CIDRs:

      ```
      ingress:
        allowedSourceCidrs: ["10.20.30.0/24"]
      ```

      The chart turns this into `alb.ingress.kubernetes.io/inbound-cidrs`
      (className alb), which the ALB enforces in its security group, or
      `nginx.ingress.kubernetes.io/whitelist-source-range` (className
      nginx), which nginx checks against the client IP it sees. On AWS,
      `externalTrafficPolicy: Local` alone does not make nginx see the
      proxy's IP: a Classic Load Balancer never keeps the client IP. The
      ingress-nginx controller must sit behind a Network Load Balancer that
      keeps it: instance targets with `externalTrafficPolicy: Local` on the
      controller's Service, IP targets with the target group attribute
      `preserve_client_ip.enabled=true`, or proxy protocol turned on in both
      the NLB and the controller. If you cannot set that up, leave
      `allowedSourceCidrs` empty and instead limit who reaches the
      controller's load balancer: set `controller.service.loadBalancerSourceRanges`
      in the ingress-nginx Helm values to the proxy's CIDRs, or limit its
      security group to inbound 443 from them. Never widen
      `ingress.allowedSourceCidrs` to the VPC to make it work: every pod and
      node in the VPC could then forge the identity header.

      Layout 2: ingress-nginx asks oauth2-proxy about every request
      (`nginx.ingress.kubernetes.io/auth-url` and
      `nginx.ingress.kubernetes.io/auth-signin`) and copies the signed-in
      user's header from its answer onto the request
      (`nginx.ingress.kubernetes.io/auth-response-headers`), replacing any
      value the user sent. Put the three annotations in
      `ingress.annotations`, run oauth2-proxy with `--set-xauthrequest`, and
      set `authHeader` to the header you pass through, for example
      `X-Auth-Request-Email`; any other header name could still be forged.
      Users reach the ingress directly here, so leave `allowedSourceCidrs`
      empty and the rate limit on.

   b. **Who may reach the pods.** The chart's NetworkPolicy lets only the
      ingress controller reach the pods; with the wrong setting it drops
      every request.
      - `ingress.className: nginx`: traffic comes from the ingress-nginx
        namespace. The default is `ingress-nginx`. If the controller runs in
        another namespace, set `networkPolicy.ingressControllerNamespace` to
        that namespace. This command shows it in the first column:
        `kubectl get pods -A -l app.kubernetes.io/name=ingress-nginx`
      - `ingress.className: alb`: the ALB sends traffic straight to the pod
        IPs from its own subnets, not from a namespace, so
        `networkPolicy.ingressCidrs` must list the ALB's subnet CIDRs. Every
        address in those subnets can then reach the pods on port 8000 and
        forge the identity header. With the VPC CNI, pods and nodes often
        share the subnets tagged `kubernetes.io/role/internal-elb`, so do not
        simply list those. Put the ALB in dedicated subnets that no node
        group uses and no ENIConfig (VPC CNI custom networking) gives to
        pods, and pin the ALB to them with an annotation:

        ```
        ingress:
          annotations:
            alb.ingress.kubernetes.io/subnets: subnet-REPLACE_ME-a,subnet-REPLACE_ME-b
        ```

        Check that no node runs in them; none of the ALB subnet ids may
        appear in the output of:

        ```
        aws ec2 describe-instances --filters Name=tag:eks:cluster-name,Values=<cluster> \
          --query "Reservations[].Instances[].SubnetId" --output text
        ```

        Then list the dedicated subnets' CIDRs:

        ```
        aws ec2 describe-subnets --subnet-ids subnet-REPLACE_ME-a subnet-REPLACE_ME-b \
          --query "Subnets[].CidrBlock" --output text
        ```

        ```
        networkPolicy:
          ingressCidrs: ["10.0.1.0/24", "10.0.2.0/24"]
        ```

        If dedicated subnets are not possible, use Security Groups for Pods
        instead: give the viz-site pods a security group that allows port
        8000 only from the ALB's security group, and still list the ALB's
        subnet CIDRs in `networkPolicy.ingressCidrs`.

   c. **Rate limit.** With ingress-nginx the chart limits each client IP to
      `ingress.rateLimit.perSecond` requests per second. Behind the company
      SSO proxy every request arrives from the proxy's IP, so all users share
      that one limit and the site starts refusing everyone under normal use.
      Set `ingress.rateLimit.enabled: false` when a proxy sits in front of
      the ingress. On ALB the value does nothing; use a WAF rate-based rule
      there.

   d. **The first smoke test.** The site has no login of its own. With
      `requireIdentity: true` (the default), every request except
      `/api/health` that lacks the `authHeader` header (`X-Forwarded-Email`
      by default) gets 401, so until the SSO proxy is in front of the site
      every page returns 401. Keep it on: step 3 sends the header yourself
      through a port forward. Only if you cannot do that, set
      `requireIdentity: false` for the first install; step 5 turns it back
      on. Never leave it off: without it anyone who can reach the load
      balancer sees every chart.

   Install into the namespace from step 5:

   ```
   helm install viz-site deploy/helm/viz-site -f my-values.yaml -n viz
   ```

   From here on, change `my-values.yaml` and run `helm upgrade` with the
   same `-f my-values.yaml`; never run the install command again.
3. **First smoke test.** Open a port forward in one terminal:

   ```
   kubectl port-forward svc/viz-site 8080:80 -n viz
   ```

   In a second terminal, send a request with a host from your
   `allowedHosts` and the identity header:

   ```
   curl -H "Host: viz.internal.example.com" -H "X-Forwarded-Email: you@example.com" http://127.0.0.1:8080/api/tree
   ```

   It returns the folder tree as JSON. Stop the port forward with Ctrl+C.
4. **Connect the SSO proxy.** Point the company SSO proxy at the load
   balancer (layout 1), or deploy oauth2-proxy (layout 2), as decided in
   step 2a. Confirm with the proxy's owners that it overwrites the identity
   header on every request. If you chose to limit the controller's
   `loadBalancerSourceRanges` or a security group instead of
   `allowedSourceCidrs`, apply that now.
5. **Apply changes, and turn the gate back on if you turned it off.**
   `requireIdentity` is already `true` unless you set `requireIdentity: false`
   in step 2d. If you did, set `requireIdentity: true` in `my-values.yaml`
   now. Apply that and any other change you made to `my-values.yaml`:

   ```
   helm upgrade viz-site deploy/helm/viz-site -f my-values.yaml -n viz
   ```

6. **Check through the SSO proxy, then try to get around it.**
   - Check `https://<your host>/api/health` through the proxy; it returns
     `{"status": "ok"}` but does not touch S3, so it only says the pods are
     running. Then open `https://<your host>/` and
     check that the folder tree loads.
   - From a machine that is not the proxy, send a request with a made-up
     `authHeader` header straight to the load balancer:
     `curl -H "X-Forwarded-Email: someone@example.com" https://<load balancer host>/api/tree`.
     It must fail (403, or no connection at all); if it returns the tree,
     go back to step 2a.
   - From another pod in the cluster, send the same request straight to a
     viz-site pod. Find a pod IP in the IP column of
     `kubectl get pods -n viz -o wide`, then run a throwaway curl pod in
     another namespace:

     ```
     kubectl run forge-test --rm -it --restart=Never -n default --image=curlimages/curl -- \
       curl -s -m 5 -H "Host: viz.internal.example.com" -H "X-Forwarded-Email: someone@example.com" http://<pod ip>:8000/api/tree
     ```

     It must time out. Any HTTP answer, even a 400 or 401, means other
     pods can reach viz-site directly: check the NetworkPolicy engine
     ("What you need") and step 2b.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Every request returns 400 | The host is not in `VIZ_ALLOWED_HOSTS` (Helm: `allowedHosts`) |
| Every page returns 401 | `requireIdentity` is on and the request did not come through the SSO proxy (no `X-Forwarded-Email` header). See step 7 |
| Pods never become ready | The container exits at start (`kubectl logs`), or the cluster's NetworkPolicy engine blocks the kubelet's probes. `/api/health` needs neither S3 nor an allowed Host header |
| Pods are Ready but every request through the load balancer times out or gets 502/504 | The NetworkPolicy does not let the ingress controller in. On ALB set `networkPolicy.ingressCidrs` to the ALB subnets' CIDRs; with ingress-nginx in another namespace set `networkPolicy.ingressControllerNamespace`. See step 7, item 2 |
| Pods are Ready but pages show errors or an empty tree | The pods cannot read the bucket: check `networkPolicy.egressCidrs` (S3 and STS), the IRSA role and its trust policy, and the KMS key policy. Pods never call KMS themselves; S3 calls KMS on their behalf, so no egress rule for KMS is needed, but the key policy must allow the `viz-site-server` role `kms:Decrypt` |
| Large-data charts fail to load | `web/dist/duckdb/` is missing from the build; the DuckDB parquet extension is self-hosted and pinned to DuckDB v1.4.3, so re-pin it when upgrading `@duckdb/duckdb-wasm` |
| `viz validate` says the author does not match (Databricks) | The CLI uses the Databricks login only when `DATABRICKS_HOST`, `DATABRICKS_TOKEN` and `DATABRICKS_WAREHOUSE_ID` are all set. Set all three, or set `VIZ_AUTHOR` to your Databricks login |
| `viz validate` says the author does not match (not all Databricks variables set) | The AWS identity changed between commands. Set `VIZ_AUTHOR` to your email, or use a fixed `role_session_name` in your AWS profile |
| `viz query` says the query is refused | `VIZ_QUERY_DENY` lists that catalog or schema |
