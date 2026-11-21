locals {
  backend_paths = ["/api/*", "/docs", "/redoc", "/openapi.json", "/map"]

  # One blue and one green target group per container. ECS swaps them on each deployment.
  target_groups = {
    backend-blue  = { port = 8000, health_path = "/api/v1/health" }
    backend-green = { port = 8000, health_path = "/api/v1/health" }
    web-blue      = { port = 80, health_path = "/healthz" }
    web-green     = { port = 80, health_path = "/healthz" }
  }
}

resource "aws_lb" "main" {
  name               = "cascadasen"
  load_balancer_type = "application"
  internal           = false
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
}

resource "aws_lb_target_group" "this" {
  for_each = local.target_groups

  name        = "cascadasen-${each.key}"
  port        = each.value.port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  deregistration_delay = 30

  health_check {
    path                = each.value.health_path
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

# Production listener: the one CloudFront talks to (HTTP :80, or HTTPS :443 when origin_https).
resource "aws_lb_listener" "production" {
  load_balancer_arn = aws_lb.main.arn
  port              = local.alb_port
  protocol          = var.origin_https ? "HTTPS" : "HTTP"
  ssl_policy        = var.origin_https ? "ELBSecurityPolicy-TLS13-1-2-2021-06" : null
  certificate_arn   = var.origin_https ? var.alb_certificate_arn : null

  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "not found"
      status_code  = "404"
    }
  }

  lifecycle {
    precondition {
      condition     = !var.origin_https || var.alb_certificate_arn != null
      error_message = "origin_https needs alb_certificate_arn."
    }
  }
}

# Test listener: ECS routes the green task here before the production swap. No ingress rule opens it.
resource "aws_lb_listener" "test" {
  load_balancer_arn = aws_lb.main.arn
  port              = 8080
  protocol          = "HTTP"

  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "not found"
      status_code  = "404"
    }
  }
}

# Rules per listener and container. ECS rewrites the forward action during a deployment,
# so Terraform must not revert it.
locals {
  listeners = {
    production = aws_lb_listener.production.arn
    test       = aws_lb_listener.test.arn
  }
  rules = {
    for pair in setproduct(keys(local.listeners), ["backend", "web"]) :
    "${pair[0]}-${pair[1]}" => {
      listener_arn = local.listeners[pair[0]]
      container    = pair[1]
      priority     = pair[1] == "backend" ? 10 : 100
      paths        = pair[1] == "backend" ? local.backend_paths : ["/*"]
    }
  }
}

resource "aws_lb_listener_rule" "this" {
  for_each = local.rules

  listener_arn = each.value.listener_arn
  priority     = each.value.priority

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this["${each.value.container}-blue"].arn
  }

  condition {
    path_pattern {
      values = each.value.paths
    }
  }

  lifecycle {
    ignore_changes = [action]
  }
}
