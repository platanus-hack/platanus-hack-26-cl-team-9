data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "task_execution" {
  name               = "cascadasen-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs.amazonaws.com"]
    }
  }
}

# Lets ECS shift traffic between the blue and green target groups during a deployment.
resource "aws_iam_role" "ecs_infrastructure" {
  name               = "cascadasen-ecs-infrastructure"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "ecs_infrastructure" {
  role       = aws_iam_role.ecs_infrastructure.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonECSInfrastructureRolePolicyForLoadBalancers"
}
# Role of the running containers. The backend reads and writes sessions and runs in the sessions bucket.
resource "aws_iam_role" "task" {
  name               = "cascadasen-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}
data "aws_iam_policy_document" "task_sessions" {
  statement {
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [
      "${aws_s3_bucket.sessions.arn}/sessions/*",
      "${aws_s3_bucket.sessions.arn}/runs/*",
      # Assistant conversations (application/assistant.py).
      "${aws_s3_bucket.sessions.arn}/assistant/*",
    ]
  }
  # No prefix condition: without ListBucket on the bucket, S3 answers 403 instead of 404 for a missing key.
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.sessions.arn]
  }
}
resource "aws_iam_role_policy" "task_sessions" {
  name   = "cascadasen-task-sessions"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task_sessions.json
}

# In-app assistant (docs/assistant.md): the backend calls Bedrock Converse. Any model is allowed except
# Anthropic; the web picks the model. The Deny wins over the Allow. A cross-region profile also needs
# the foundation-model ARN of every region it routes to, hence the wildcard region.
data "aws_iam_policy_document" "task_bedrock" {
  statement {
    actions = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = [
      "arn:aws:bedrock:*::foundation-model/*",
      "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/*",
    ]
  }
  statement {
    effect    = "Deny"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = [
      "arn:aws:bedrock:*::foundation-model/anthropic.*",
      "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/*anthropic*",
    ]
  }
}
resource "aws_iam_role_policy" "task_bedrock" {
  name   = "cascadasen-task-bedrock"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task_bedrock.json
}
