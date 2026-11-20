#!/usr/bin/env bash
# Push site changes live, through Terraform, then clear the CloudFront cache.
#
#   ./redeploy.sh personal
#
# Terraform uploads any changed files in ../site and shows you the plan.
# Type "yes" to apply. Nothing changes outside Terraform, so its records
# always match what is live.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
PROFILE="${1:-personal}"

terraform apply -var "profile=${PROFILE}"

DIST="$(terraform output -raw distribution_id)"
ID="$(aws cloudfront create-invalidation \
  --distribution-id "$DIST" --paths "/*" \
  --profile "$PROFILE" --query 'Invalidation.Id' --output text)"
echo "clearing the CloudFront cache ($ID)..."
aws cloudfront wait invalidation-completed --distribution-id "$DIST" --id "$ID" --profile "$PROFILE"

echo
echo "live: $(terraform output -raw plain_site)"
