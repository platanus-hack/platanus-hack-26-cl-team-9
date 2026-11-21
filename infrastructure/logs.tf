resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/cascadasen"
  retention_in_days = 7
}
