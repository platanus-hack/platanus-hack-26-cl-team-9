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
variable "llm_model" {
  description = "Bedrock model id used by the backend (CASCADASEN_LLM_MODEL). The task role may invoke only this model, and the token alarm watches it."
  type        = string
  default     = "deepseek.v3.2"
}
variable "alert_email" {
  description = "Email that receives the Bedrock token alarm and the Bedrock budget alerts. No default: personal data stays out of the repo. Pass it with TF_VAR_alert_email or a git-ignored terraform.tfvars."
  type        = string
  sensitive   = true
  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "alert_email must be an email address."
  }
}
variable "bedrock_alarm_tokens" {
  description = "Alarm when input + output tokens of llm_model, summed over one period, exceed this. Default is about twice the busiest hour seen (2.1M input tokens during testing); about $3 an hour at an assumed DeepSeek V3.2 price near $0.7 per million tokens. To confirm."
  type        = number
  default     = 4000000
}
variable "bedrock_alarm_period_s" {
  description = "Length in seconds of the window the token alarm sums over."
  type        = number
  default     = 3600
}
variable "bedrock_alarm_evaluation_periods" {
  description = "Consecutive windows above the threshold before the alarm fires."
  type        = number
  default     = 1
}
variable "bedrock_budget_usd" {
  description = "Monthly budget for Amazon Bedrock usage, credits excluded. Observed 21 to 23 Nov 2026 testing: USD 4.95 in 3 days. To confirm."
  type        = number
  default     = 30
}
variable "bedrock_budget_alert_percentages" {
  description = "Percentages of the budget that send an email when the actual spend passes them. A forecast alert at 100% is always added."
  type        = list(number)
  default     = [50, 80, 100]
}
