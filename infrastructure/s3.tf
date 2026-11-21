# Shared sessions and persisted strategic runs (docs/stack.md 7.1). Private, encrypted, expired after the session TTL.
resource "aws_s3_bucket" "sessions" {
  bucket = "cascadasen-sessions-402909940511"
}
resource "aws_s3_bucket_public_access_block" "sessions" {
  bucket                  = aws_s3_bucket.sessions.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "sessions" {
  bucket = aws_s3_bucket.sessions.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
resource "aws_s3_bucket_ownership_controls" "sessions" {
  bucket = aws_s3_bucket.sessions.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}
# S3 rounds each expiry up to the next UTC midnight, so objects live between 1 and 2 days.
resource "aws_s3_bucket_lifecycle_configuration" "sessions" {
  bucket = aws_s3_bucket.sessions.id
  dynamic "rule" {
    for_each = toset(["sessions", "runs"])
    content {
      id     = "expire-${rule.value}"
      status = "Enabled"
      filter {
        prefix = "${rule.value}/"
      }
      expiration {
        days = var.session_ttl_days
      }
      abort_incomplete_multipart_upload {
        days_after_initiation = 1
      }
    }
  }
}
