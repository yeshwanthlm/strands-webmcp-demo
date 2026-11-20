# Palace Road Tiffin Room — static hosting on S3 + CloudFront.
#
# Private bucket, CloudFront-only access via Origin Access Control, HTTPS
# enforced, no public bucket ACLs. Nothing here costs money while idle beyond
# a few cents of storage.
#
#   cd infra
#   terraform init
#   terraform plan -out=tfplan
#   terraform apply tfplan          # ask before running this
#   terraform destroy               # after the talk

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 6.0" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

provider "aws" {
  region  = var.region
  profile = var.profile

  default_tags {
    tags = {
      Project = "scd-mysuru-2026"
      Purpose = "WebMCP talk demo"
    }
  }
}

variable "region" {
  description = "Region for the S3 bucket. CloudFront itself is global."
  type        = string
  default     = "ap-south-1"
}

variable "profile" {
  description = "AWS CLI profile to use. null means the default chain."
  type        = string
  default     = null
}

variable "bucket_prefix" {
  type    = string
  default = "palace-road-tiffin"
}

resource "random_id" "suffix" {
  byte_length = 3
}

locals {
  bucket_name = "${var.bucket_prefix}-${random_id.suffix.hex}"
  site_dir    = "${path.module}/../site"

  # Only the files the site actually needs. Keeps serve.sh out of the bucket.
  files = {
    "index.html" = "text/html; charset=utf-8"
    "styles.css" = "text/css; charset=utf-8"
    "app.js"     = "text/javascript; charset=utf-8"
    "webmcp.js"  = "text/javascript; charset=utf-8"
    "hud.js"     = "text/javascript; charset=utf-8"
  }
}

# ----------------------------------------------------------------- bucket

resource "aws_s3_bucket" "site" {
  bucket = local.bucket_name
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  bucket = aws_s3_bucket.site.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "site" {
  bucket = aws_s3_bucket.site.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_object" "file" {
  for_each = local.files

  bucket        = aws_s3_bucket.site.id
  key           = each.key
  source        = "${local.site_dir}/${each.key}"
  etag          = filemd5("${local.site_dir}/${each.key}")
  content_type  = each.value
  cache_control = "public, max-age=60"
}

# ------------------------------------------------------------- cloudfront

resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${local.bucket_name}-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# Managed policies, looked up rather than hardcoded by id.
data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_response_headers_policy" "security" {
  name = "Managed-SecurityHeadersPolicy"
}

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  default_root_object = "index.html"
  comment             = "Palace Road Tiffin Room — WebMCP talk demo"
  price_class         = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id                = "s3-site"
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  default_cache_behavior {
    target_origin_id       = "s3-site"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    cache_policy_id            = data.aws_cloudfront_cache_policy.optimized.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# Let only this distribution read the bucket.
data "aws_iam_policy_document" "bucket" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.site.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.site.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id
  policy = data.aws_iam_policy_document.bucket.json

  depends_on = [aws_s3_bucket_public_access_block.site]
}

# ---------------------------------------------------------------- outputs

output "plain_site" {
  description = "Arm A. The ordinary website."
  value       = "https://${aws_cloudfront_distribution.site.domain_name}/"
}

output "webmcp_site" {
  description = "Arm B. Same site, tools declared."
  value       = "https://${aws_cloudfront_distribution.site.domain_name}/?webmcp=1"
}

output "bucket" {
  value = aws_s3_bucket.site.id
}

output "distribution_id" {
  description = "Use with redeploy.sh to invalidate the cache."
  value       = aws_cloudfront_distribution.site.id
}
