# Certificate for sub50.cl and *.sub50.cl, validated by DNS in the zone from route53.tf.
# Not attached to CloudFront or the ALB yet.
resource "aws_acm_certificate" "main" {
  domain_name               = aws_route53_zone.main.name
  subject_alternative_names = ["*.${aws_route53_zone.main.name}"]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# The apex and the wildcard produce the same validation record. Keys are the domain names
# (known at plan time) and allow_overwrite lets both entries write the same record.
resource "aws_route53_record" "acm_validation" {
  for_each = {
    for o in aws_acm_certificate.main.domain_validation_options : o.domain_name => o
  }

  zone_id         = aws_route53_zone.main.zone_id
  name            = each.value.resource_record_name
  type            = each.value.resource_record_type
  records         = [each.value.resource_record_value]
  ttl             = 60
  allow_overwrite = true
}

# Waits until the certificate is ISSUED. This only succeeds after the .cl registrar delegates
# sub50.cl to the Route 53 name servers.
resource "aws_acm_certificate_validation" "main" {
  certificate_arn         = aws_acm_certificate.main.arn
  validation_record_fqdns = [for r in aws_route53_record.acm_validation : r.fqdn]
}
