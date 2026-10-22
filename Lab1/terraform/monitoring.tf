# Бонус 7: моніторинг. Логи вже йдуть у CloudWatch (ecs.tf).
# Тут: дашборд з метриками + алерти на email через SNS.

locals {
  alb_dim = aws_lb.main.arn_suffix             # як CloudWatch називає наш балансувальник
  tg_dim  = aws_lb_target_group.app.arn_suffix # і target group
}

# ---------- Куди слати алерти ----------

resource "aws_sns_topic" "alerts" {
  name = "${var.project}-alerts"
}

# Після apply AWS надішле лист "AWS Notification - Subscription Confirmation" —
# треба натиснути Confirm subscription, інакше листи не приходитимуть.
resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.budget_email
}

# ---------- Алерти ----------

# Застосунок відповів помилкою 5xx хоча б раз за хвилину
resource "aws_cloudwatch_metric_alarm" "app_5xx" {
  alarm_name          = "${var.project}-app-5xx"
  alarm_description   = "Застосунок повертає помилки 5xx"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  dimensions          = { LoadBalancer = local.alb_dim }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching" # немає запитів = немає помилок
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

# Жоден контейнер не проходить health check 2 хвилини поспіль
resource "aws_cloudwatch_metric_alarm" "no_healthy_targets" {
  alarm_name          = "${var.project}-no-healthy-targets"
  alarm_description   = "Немає жодного здорового контейнера за балансувальником"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HealthyHostCount"
  dimensions          = { LoadBalancer = local.alb_dim, TargetGroup = local.tg_dim }
  statistic           = "Minimum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching" # немає даних = вважаємо, що все лежить
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

# ---------- Дашборд ----------

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project}-dashboard"

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric", x = 0, y = 0, width = 12, height = 6
        properties = {
          title   = "Кількість запитів (за хвилину)"
          region  = var.region
          view    = "timeSeries"
          stat    = "Sum"
          period  = 60
          metrics = [["AWS/ApplicationELB", "RequestCount", "LoadBalancer", local.alb_dim]]
        }
      },
      {
        type = "metric", x = 12, y = 0, width = 12, height = 6
        properties = {
          title  = "Помилки 5xx"
          region = var.region
          view   = "timeSeries"
          stat   = "Sum"
          period = 60
          metrics = [
            ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", local.alb_dim, { label = "від застосунку" }],
            ["AWS/ApplicationELB", "HTTPCode_ELB_5XX_Count", "LoadBalancer", local.alb_dim, { label = "від балансувальника" }],
          ]
        }
      },
      {
        type = "metric", x = 0, y = 6, width = 12, height = 6
        properties = {
          title  = "Латентність (секунди)"
          region = var.region
          view   = "timeSeries"
          period = 60
          metrics = [
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", local.alb_dim, { stat = "Average", label = "середня" }],
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", local.alb_dim, { stat = "p95", label = "p95" }],
          ]
        }
      },
      {
        type = "metric", x = 12, y = 6, width = 12, height = 6
        properties = {
          title  = "CPU і пам'ять контейнера (%)"
          region = var.region
          view   = "timeSeries"
          stat   = "Average"
          period = 60
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.app.name, { label = "CPU" }],
            ["AWS/ECS", "MemoryUtilization", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.app.name, { label = "Пам'ять" }],
          ]
        }
      },
      {
        type = "alarm", x = 0, y = 12, width = 12, height = 4
        properties = {
          title  = "Стан алертів"
          alarms = [aws_cloudwatch_metric_alarm.app_5xx.arn, aws_cloudwatch_metric_alarm.no_healthy_targets.arn]
        }
      },
      {
        type = "log", x = 12, y = 12, width = 12, height = 8
        properties = {
          title  = "Останні логи застосунку"
          region = var.region
          view   = "table"
          query  = "SOURCE '${aws_cloudwatch_log_group.app.name}' | fields @timestamp, @message | sort @timestamp desc | limit 20"
        }
      },
    ]
  })
}
