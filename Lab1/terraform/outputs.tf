output "app_url" {
  description = "Public URL of the service"
  value       = "http://${aws_lb.main.dns_name}"
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "github_deploy_role_arn" {
  description = "GitHub -> Settings -> Secrets and variables -> Actions -> Variables -> AWS_ROLE_ARN"
  value       = aws_iam_role.github_deploy.arn
}

output "db_endpoint" {
  value = aws_db_instance.main.address
}

output "dashboard_url" {
  value = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards/dashboard/${aws_cloudwatch_dashboard.main.dashboard_name}"
}

output "sqs_queue_url" {
  value = aws_sqs_queue.jobs.url
}

output "admin_token_secret_name" {
  description = "Secret with the token for /admin endpoints (used by loadtest/admin.ps1)"
  value       = aws_secretsmanager_secret.admin.name
}

output "alerts_topic_arn" {
  value = aws_sns_topic.alerts.arn
}
