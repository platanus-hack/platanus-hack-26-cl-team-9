#!/usr/bin/env bash
# Deploy CascadaSEN to AWS (account 402909940511, us-east-1).
#   ./deploy.sh plan    check the account, create the state bucket if missing, init, validate, plan
#   ./deploy.sh apply   create ECR, build and push both images, apply the full plan
# Credentials come from AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY. If unset, they are
# sourced from KEYS_FILE (default: the team keys file). Nothing prints them.
set -euo pipefail

ACCOUNT_ID="402909940511"
REGION="us-east-1"
BUCKET="cascadasen-tfstate-${ACCOUNT_ID}"
KEYS_FILE="${KEYS_FILE:-/Users/alonsoutreras/Desktop/Hackathon/keys.txt}"

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$INFRA_DIR/.." && pwd)"
TAG_FILE="$INFRA_DIR/.deploy-tag"
export AWS_DEFAULT_REGION="$REGION"

usage() {
  echo "usage: $0 plan|apply" >&2
  exit 2
}

load_credentials() {
  if [[ -z "${AWS_ACCESS_KEY_ID:-}" || -z "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
    [[ -f "$KEYS_FILE" ]] || { echo "No AWS credentials in the environment and $KEYS_FILE not found" >&2; exit 1; }
    # shellcheck disable=SC1090
    source "$KEYS_FILE" >/dev/null 2>&1
  fi
}

check_account() {
  local actual
  actual="$(aws sts get-caller-identity --query Account --output text)"
  if [[ "$actual" != "$ACCOUNT_ID" ]]; then
    echo "Wrong AWS account: got $actual, expected $ACCOUNT_ID. Aborting." >&2
    exit 1
  fi
  echo "AWS account check OK: $ACCOUNT_ID"
}

# Image tag: short commit, plus -dirty-<UTC time> when the build inputs have uncommitted changes.
compute_tag() {
  local tag
  tag="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
  if [[ -n "$(git -C "$REPO_ROOT" status --porcelain -- backend web data infrastructure/docker)" ]]; then
    tag="${tag}-dirty-$(date -u +%Y%m%d%H%M%S)"
  fi
  echo "$tag"
}

# The part of the tag that identifies the commit and the dirty flag (without the timestamp).
tag_base() {
  echo "$1" | sed -E 's/-dirty-[0-9]+$/-dirty/'
}

ensure_state_bucket() {
  if aws s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1; then
    echo "State bucket exists: $BUCKET"
    return
  fi
  echo "Creating state bucket: $BUCKET"
  aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" >/dev/null
  aws s3api put-bucket-versioning --bucket "$BUCKET" --versioning-configuration Status=Enabled
  aws s3api put-bucket-encryption --bucket "$BUCKET" \
    --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
  aws s3api put-public-access-block --bucket "$BUCKET" \
    --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
}

tf_init() {
  terraform -chdir="$INFRA_DIR" init -input=false -backend-config="bucket=$BUCKET" >/dev/null
  terraform -chdir="$INFRA_DIR" fmt -check -recursive
  terraform -chdir="$INFRA_DIR" validate
}

cmd_plan() {
  local tag
  tag="$(compute_tag)"
  ensure_state_bucket
  tf_init
  terraform -chdir="$INFRA_DIR" plan -input=false -out=tfplan -var "image_tag=$tag"
  echo "$tag" >"$TAG_FILE"
  echo "Planned image tag: $tag"
}

push_image() {
  local name="$1" repo_url="$2" tag="$3"
  if aws ecr describe-images --repository-name "cascadasen/$name" --image-ids "imageTag=$tag" >/dev/null 2>&1; then
    echo "Image cascadasen/$name:$tag already in ECR, skipping build"
    return
  fi
  docker build --platform linux/amd64 -f "$INFRA_DIR/docker/$name.Dockerfile" -t "$repo_url:$tag" "$REPO_ROOT"
  docker push "$repo_url:$tag"
}

cmd_apply() {
  [[ -f "$TAG_FILE" ]] || { echo "No $TAG_FILE. Run '$0 plan' first." >&2; exit 1; }
  local planned current tag
  planned="$(cat "$TAG_FILE")"
  current="$(compute_tag)"
  if [[ "$(tag_base "$planned")" != "$(tag_base "$current")" ]]; then
    echo "The tree changed since the plan ($planned -> $current). Run '$0 plan' again." >&2
    exit 1
  fi
  tag="$planned"

  ensure_state_bucket
  tf_init

  # 1. ECR first, so the images exist before the ECS service starts.
  terraform -chdir="$INFRA_DIR" apply -input=false \
    -target=aws_ecr_repository.backend -target=aws_ecr_repository.web -var "image_tag=$tag"

  # 2. Build and push both images.
  local registry backend_url web_url
  backend_url="$(terraform -chdir="$INFRA_DIR" output -raw ecr_backend_url)"
  web_url="$(terraform -chdir="$INFRA_DIR" output -raw ecr_web_url)"
  registry="${backend_url%%/*}"
  aws ecr get-login-password | docker login --username AWS --password-stdin "$registry" >/dev/null
  push_image backend "$backend_url" "$tag"
  push_image web "$web_url" "$tag"

  # 3. Full apply from a fresh plan, shown before it runs.
  terraform -chdir="$INFRA_DIR" plan -input=false -out=tfplan -var "image_tag=$tag"
  terraform -chdir="$INFRA_DIR" apply -input=false tfplan

  echo "Deployed image tag: $tag"
  echo "URL: $(terraform -chdir="$INFRA_DIR" output -raw cloudfront_url)"
}

[[ $# -eq 1 ]] || usage
load_credentials
check_account
case "$1" in
  plan) cmd_plan ;;
  apply) cmd_apply ;;
  *) usage ;;
esac
