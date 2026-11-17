data "aws_secretsmanager_random_password" "jwt" {
  password_length     = 48
  exclude_punctuation = true
}

data "aws_secretsmanager_random_password" "admin" {
  password_length     = 40
  exclude_punctuation = true
}

data "aws_secretsmanager_random_password" "redis" {
  password_length     = 40
  exclude_punctuation = true
}

resource "aws_secretsmanager_secret" "jwt" {
  name                    = "${var.project}-jwt-secret"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "jwt" {
  secret_id     = aws_secretsmanager_secret.jwt.id
  secret_string = data.aws_secretsmanager_random_password.jwt.random_password

  lifecycle {
    ignore_changes = [secret_string]
  }
}

resource "aws_secretsmanager_secret" "admin" {
  name                    = "${var.project}-admin-token"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "admin" {
  secret_id     = aws_secretsmanager_secret.admin.id
  secret_string = data.aws_secretsmanager_random_password.admin.random_password

  lifecycle {
    ignore_changes = [secret_string]
  }
}

resource "aws_secretsmanager_secret" "redis" {
  name                    = "${var.project}-redis-password"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "redis" {
  secret_id     = aws_secretsmanager_secret.redis.id
  secret_string = data.aws_secretsmanager_random_password.redis.random_password

  lifecycle {
    ignore_changes = [secret_string]
  }
}
