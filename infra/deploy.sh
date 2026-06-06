#!/usr/bin/env bash
# Build and push the backend + frontend images to Artifact Registry.
#
# Usage:
#   PROJECT_ID=my-proj REGION=us-central1 TAG=v1 \
#   BACKEND_URL=https://...run.app ./infra/deploy.sh
#
# BACKEND_URL is optional on the first run (frontend defaults to localhost); set
# it once the backend is deployed, then re-run to rebuild the frontend.
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
TAG="${TAG:-v1}"
REPO="${REGION}-docker.pkg.dev/${PROJECT_ID}/cloudops-images"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Configuring docker auth for ${REGION}-docker.pkg.dev"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

echo "==> Building + pushing backend: ${REPO}/backend:${TAG}"
docker build --platform linux/amd64 -t "${REPO}/backend:${TAG}" "${ROOT}/backend"
docker push "${REPO}/backend:${TAG}"

echo "==> Building + pushing frontend (VITE_API_URL=${BACKEND_URL}): ${REPO}/frontend:${TAG}"
docker build --platform linux/amd64 \
  --build-arg "VITE_API_URL=${BACKEND_URL}" \
  -t "${REPO}/frontend:${TAG}" "${ROOT}/frontend"
docker push "${REPO}/frontend:${TAG}"

echo "==> Done. Image refs:"
echo "    backend_image  = \"${REPO}/backend:${TAG}\""
echo "    frontend_image = \"${REPO}/frontend:${TAG}\""
