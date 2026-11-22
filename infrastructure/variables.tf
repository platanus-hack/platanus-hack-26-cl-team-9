variable "image_tag" {
  description = "Tag of the backend and web images in ECR. deploy.sh sets it from the git commit."
  type        = string
}

variable "domain_name" {
  description = "Public domain: the Route 53 zone, the ACM certificate and the CloudFront alias."
  type        = string
  default     = "sub50.cl"
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
variable "session_ttl_days" {
  description = "Days before S3 expires session and run objects (the app TTL is 24 h; S3 rounds to the next UTC midnight)."
  type        = number
  default     = 1
}
