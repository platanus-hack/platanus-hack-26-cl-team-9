output "cloudfront_url" {
  description = "Public URL of the deployment."
  value       = "https://${aws_cloudfront_distribution.main.domain_name}"
}

output "alb_dns_name" {
  description = "ALB DNS name (an ALB has no Elastic IP). CloudFront points to it."
  value       = aws_lb.main.dns_name
}

output "ecr_backend_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "ecr_web_url" {
  value = aws_ecr_repository.web.repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  value = aws_ecs_service.app.name
}
output "route53_name_servers" {
  description = "Name servers of the sub50.cl zone. Set them as NS records at the .cl registrar."
  value       = aws_route53_zone.main.name_servers
}
output "acm_certificate_arn" {
  description = "ACM certificate (us-east-1) for sub50.cl and *.sub50.cl. Use it for cloudfront_certificate_arn and alb_certificate_arn."
  value       = aws_acm_certificate_validation.main.certificate_arn
}
