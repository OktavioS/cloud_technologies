output "app_url" {
  description = "Публічна адреса застосунку"
  value       = "http://${aws_lb.main.dns_name}"
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "github_deploy_role_arn" {
  description = "Вставити в GitHub → Settings → Secrets and variables → Actions → Variables як AWS_ROLE_ARN"
  value       = aws_iam_role.github_deploy.arn
}

output "db_endpoint" {
  value = aws_db_instance.main.address
}

output "dashboard_url" {
  description = "Дашборд моніторингу (бонус 7)"
  value       = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards/dashboard/${aws_cloudwatch_dashboard.main.dashboard_name}"
}
