resource "aws_route53_zone" "main" {
  name    = var.domain_name
  comment = "CascadaSEN public zone"
}

# Apex alias to CloudFront (A and AAAA). Z2FDTNDATAQYW2 is the fixed hosted zone ID of every
# CloudFront distribution.
resource "aws_route53_record" "apex" {
  for_each = toset(["A", "AAAA"])
  zone_id  = aws_route53_zone.main.zone_id
  name     = var.domain_name
  type     = each.key
  alias {
    name                   = aws_cloudfront_distribution.main.domain_name
    zone_id                = aws_cloudfront_distribution.main.hosted_zone_id
    evaluate_target_health = false
  }
}
