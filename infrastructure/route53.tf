# Hosted zone only. Records, ACM certificates and the CloudFront alias come later.
resource "aws_route53_zone" "main" {
  name    = "sub50.cl"
  comment = "CascadaSEN public zone"
}
