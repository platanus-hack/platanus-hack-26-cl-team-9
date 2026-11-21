variable "image_tag" {
  description = "Tag of the backend and web images in ECR. deploy.sh sets it from the git commit."
  type        = string
}

variable "domain_name" {
  description = "Public domain served by CloudFront. null keeps the default *.cloudfront.net name."
  type        = string
  default     = null
}

variable "cloudfront_certificate_arn" {
  description = "ACM certificate in us-east-1 for domain_name. Required when domain_name is set."
  type        = string
  default     = null
}

variable "origin_https" {
  description = "Use HTTPS between CloudFront and the ALB. Needs alb_certificate_arn."
  type        = bool
  default     = false
}

variable "alb_certificate_arn" {
  description = "ACM certificate for the ALB HTTPS listener. Required when origin_https is true."
  type        = string
  default     = null
}
