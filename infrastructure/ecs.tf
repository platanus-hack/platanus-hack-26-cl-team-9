data "aws_region" "current" {}

locals {
  containers = {
    backend = { port = 8000, repository_url = aws_ecr_repository.backend.repository_url }
    web     = { port = 80, repository_url = aws_ecr_repository.web.repository_url }
  }
}

resource "aws_ecs_cluster" "main" {
  name = "cascadasen"
}

# One task, 2 vCPU / 4 GB shared by both containers (no per-container limits).
resource "aws_ecs_task_definition" "app" {
  family                   = "cascadasen"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 2048
  memory                   = 4096
  execution_role_arn       = aws_iam_role.task_execution.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    for name, c in local.containers : {
      name         = name
      image        = "${c.repository_url}:${var.image_tag}"
      essential    = true
      portMappings = [{ containerPort = c.port, protocol = "tcp" }]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = data.aws_region.current.region
          "awslogs-stream-prefix" = name
        }
      }
    }
  ])
}

resource "aws_ecs_service" "app" {
  name                              = "cascadasen"
  cluster                           = aws_ecs_cluster.main.id
  task_definition                   = aws_ecs_task_definition.app.arn
  desired_count                     = 1
  launch_type                       = "FARGATE"
  health_check_grace_period_seconds = 60
  wait_for_steady_state             = true

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.task.id]
    assign_public_ip = true
  }

  deployment_configuration {
    strategy             = "BLUE_GREEN"
    bake_time_in_minutes = 2
  }

  # Two load balancer entries, one per container. Each has its own blue/green target group pair.
  load_balancer {
    target_group_arn = aws_lb_target_group.this["backend-blue"].arn
    container_name   = "backend"
    container_port   = 8000

    advanced_configuration {
      alternate_target_group_arn = aws_lb_target_group.this["backend-green"].arn
      production_listener_rule   = aws_lb_listener_rule.this["production-backend"].arn
      test_listener_rule         = aws_lb_listener_rule.this["test-backend"].arn
      role_arn                   = aws_iam_role.ecs_infrastructure.arn
    }
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.this["web-blue"].arn
    container_name   = "web"
    container_port   = 80

    advanced_configuration {
      alternate_target_group_arn = aws_lb_target_group.this["web-green"].arn
      production_listener_rule   = aws_lb_listener_rule.this["production-web"].arn
      test_listener_rule         = aws_lb_listener_rule.this["test-web"].arn
      role_arn                   = aws_iam_role.ecs_infrastructure.arn
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.ecs_infrastructure,
    aws_iam_role_policy_attachment.task_execution,
  ]
}
