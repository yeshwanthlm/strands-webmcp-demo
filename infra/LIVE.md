# Live deployment

Deployed 20 Nov 2026 with `terraform apply`, AWS CLI profile `personal`.

| | Value |
|---|---|
| Account | 696457893256 (`personal` profile) |
| Site | https://d2gk3ykaq9ah2.cloudfront.net/ |
| WebMCP | Switch in the header. Or open with `?webmcp=1` to start it on |
| Bucket | `palace-road-tiffin-2d2614` (ap-south-1, private) |
| CloudFront | `EHBLPE2UZGE7W` |

Every Terraform command here needs `-var profile=personal`. Without it,
Terraform uses the `default` profile, which is a different account.

```
cd infra
terraform plan -var profile=personal
./redeploy.sh personal        # terraform apply + clear cache
terraform destroy -var profile=personal
```

The state file `infra/terraform.tfstate` is local and git-ignored. Keep it.
Losing it means removing these resources by hand.
