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
# Role of the running containers. The backend reads and writes sessions, runs and assistant conversations
# in the sessions bucket, reads grids from it and calls Bedrock.
resource "aws_iam_role" "task" {
  name               = "cascadasen-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}
data "aws_iam_policy_document" "task_sessions" {
  statement {
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [
      "${aws_s3_bucket.sessions.arn}/assistant/*",
      "${aws_s3_bucket.sessions.arn}/runs/*",
      "${aws_s3_bucket.sessions.arn}/sessions/*",
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

# Grids (docs/regional.md) are uploaded by hand under grids/; the app only reads them.
data "aws_iam_policy_document" "task_grids" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.sessions.arn}/grids/*"]
  }
}
resource "aws_iam_role_policy" "task_grids" {
  name   = "cascadasen-task-grids"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task_grids.json
}
# Bedrock Converse for the assistant, the C2 commander and the after-action narrative. Only the model in
# use (var.llm_model, in this region); the live policy allowed every foundation model and denied Anthropic.
data "aws_iam_policy_document" "task_bedrock" {
  statement {
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = ["arn:aws:bedrock:${data.aws_region.current.region}::foundation-model/${var.llm_model}"]
  }
}
resource "aws_iam_role_policy" "task_bedrock" {
  name   = "cascadasen-task-bedrock"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task_bedrock.json
}
