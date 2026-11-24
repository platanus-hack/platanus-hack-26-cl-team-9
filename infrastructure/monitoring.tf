# Backstops for Bedrock spend. The exact limit lives in the backend (docs/assistant.md); neither of these
# stops a call. Both email var.alert_email.
resource "aws_sns_topic" "bedrock_alerts" {
  name = "cascadasen-bedrock-alerts"
}
# The recipient must click the confirmation link AWS emails once, or nothing is delivered.
resource "aws_sns_topic_subscription" "bedrock_email" {
  topic_arn = aws_sns_topic.bedrock_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}
# Converse reports into the same AWS/Bedrock metrics as InvokeModel, dimension ModelId only.
resource "aws_cloudwatch_metric_alarm" "bedrock_tokens" {
  alarm_name          = "cascadasen-bedrock-tokens"
  alarm_description   = "Input + output tokens of ${var.llm_model} above ${var.bedrock_alarm_tokens} in ${var.bedrock_alarm_period_s} s."
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.bedrock_alarm_tokens
  evaluation_periods  = var.bedrock_alarm_evaluation_periods
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.bedrock_alerts.arn]
  metric_query {
    id          = "tokens"
    expression  = "FILL(input, 0) + FILL(output, 0)"
    label       = "Input + output tokens"
    return_data = true
  }
  dynamic "metric_query" {
    for_each = toset(["InputTokenCount", "OutputTokenCount"])
    content {
      id = lower(trimsuffix(metric_query.value, "TokenCount"))
      metric {
        namespace   = "AWS/Bedrock"
        metric_name = metric_query.value
        dimensions  = { ModelId = var.llm_model }
        period      = var.bedrock_alarm_period_s
        stat        = "Sum"
      }
    }
  }
}
# Credits are left out (include_credit = false): the account runs on credits, which would hide the usage.
resource "aws_budgets_budget" "bedrock" {
  name         = "cascadasen-bedrock"
  budget_type  = "COST"
  limit_amount = tostring(var.bedrock_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  cost_filter {
    name   = "Service"
    values = ["Amazon Bedrock"]
  }
  cost_types {
    include_credit = false
    include_refund = false
  }
  dynamic "notification" {
    for_each = toset(var.bedrock_budget_alert_percentages)
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [var.alert_email]
    }
  }
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}
