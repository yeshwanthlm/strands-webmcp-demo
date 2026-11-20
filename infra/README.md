# Hosting the site on AWS

S3 holds the four files. CloudFront serves them over HTTPS. The bucket stays
private: only the distribution can read it, through Origin Access Control.

```
         browser  ──HTTPS──▶  CloudFront  ──OAC──▶  S3 (private)
```

## Deploy

```
cd infra
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

The last command creates real resources. Read the plan first.

Terraform prints both URLs:

```
plain_site  = "https://d111111abcdef8.cloudfront.net/"
webmcp_site = "https://d111111abcdef8.cloudfront.net/?webmcp=1"
```

The first distribution takes about 5 minutes to go live.

## Point the agent at it

The two agents always use the live site. It is set on the `SITE =` line near
the top of each agent file.

## After changing the site

```
./redeploy.sh personal
```

Runs `terraform apply` (you approve the plan), then clears the CloudFront cache.

## Cost

Four small files and a `PriceClass_100` distribution. Storage and requests for
a demo audience land in cents, and CloudFront's free tier likely covers it.
The first 1,000 invalidation paths each month are free.

Tear it down when the talk is over:

```
terraform destroy
```

## Should you present from the cloud or from localhost?

**Present from localhost.** `./site/serve.sh` has no dependency on venue Wi-Fi,
no DNS, no cache to invalidate, and no CloudFront propagation wait. The flag
works fine on `127.0.0.1`.

Use the CloudFront URL for the thing localhost cannot do: putting a real link
and a QR code on the last slide so the room can open the site on their own
phones and laptops while you talk.
