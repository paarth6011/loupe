# Deployment — Phase 3a (Cloud Run on GCP)

This deploys the stack to Google Cloud Run with Cloud SQL (Postgres), Memorystore
(Redis), and Secret Manager, provisioned by Terraform in `infra/terraform`.

> ⚠️ **This costs money.** Cloud SQL and Memorystore are not free-tier. Run
> `terraform destroy` when you're done experimenting. The local Docker Compose
> stack remains the zero-cost dev environment.

## Prerequisites (one-time)

```bash
# Install tooling
brew install --cask google-cloud-sdk
brew install hashicorp/tap/terraform

# Authenticate (interactive — run this yourself)
gcloud auth login
gcloud auth application-default login          # so Terraform can use your creds

# Create / select a project with billing enabled
gcloud projects create YOUR_PROJECT_ID         # or use an existing one
gcloud config set project YOUR_PROJECT_ID
# Link a billing account in the console: https://console.cloud.google.com/billing
```

## The circular dependency (read this first)

The frontend bakes in the backend URL at build time, and the backend's CORS
allows the frontend URL — but neither URL exists until deployed. So the order is:

1. Provision the registry → 2. push images (frontend points at localhost for
now) → 3. provision everything → 4. run migrations → 5. rebuild the frontend
with the real backend URL and set CORS → 6. re-apply.

## Steps

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars: project_id, admin_password, (optional) anthropic_api_key
terraform init
```

**1 — Create the Artifact Registry repo (and enable APIs):**

```bash
terraform apply \
  -target=google_project_service.apis \
  -target=google_artifact_registry_repository.images
```

**2 — Build and push images:**

```bash
cd ../..
PROJECT_ID=YOUR_PROJECT_ID REGION=us-central1 TAG=v1 ./infra/deploy.sh
# copy the printed backend_image / frontend_image into terraform.tfvars
```

**3 — Provision the rest (Cloud SQL, Redis, secrets, Cloud Run):**

```bash
cd infra/terraform
terraform apply
terraform output            # note backend_url, frontend_url, sql_connection_name
```

**4 — Run database migrations** (one-off, via the Cloud SQL Auth Proxy):

```bash
# In one terminal:
cloud-sql-proxy "$(terraform output -raw sql_connection_name)"
# In another (uses the random DB password from Secret Manager):
DATABASE_URL="$(gcloud secrets versions access latest --secret=cloudops-database-url \
  | sed 's#@/#@127.0.0.1:5432/#; s#?host=.*##')" \
  RUN_MIGRATIONS=1 \
  bash -c 'cd backend && alembic upgrade head'
```

**5 — Rebuild the frontend against the real backend URL, and set CORS:**

```bash
cd ../..
BACKEND_URL="$(cd infra/terraform && terraform output -raw backend_url)"
PROJECT_ID=YOUR_PROJECT_ID REGION=us-central1 TAG=v2 BACKEND_URL="$BACKEND_URL" ./infra/deploy.sh
# in terraform.tfvars: bump frontend_image to :v2, set cors_origins = frontend_url
```

**6 — Re-apply:**

```bash
cd infra/terraform
terraform apply
```

Open the `frontend_url`, log in with `admin` / your `admin_password`.

## Tear down

```bash
cd infra/terraform
terraform destroy
```

## What's codified

`infra/terraform/` provisions: required APIs, a VPC + Serverless VPC Access
connector (so Cloud Run reaches Redis), Artifact Registry, Cloud SQL (Postgres
16), Memorystore (Redis 7), Secret Manager secrets (DB URL, JWT secret, admin
password, Anthropic key), a least-privilege runtime service account, and the two
Cloud Run services with `/health` startup+liveness probes. Secrets are injected
from Secret Manager — never baked into images or committed.
