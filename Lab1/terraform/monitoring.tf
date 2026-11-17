locals {
  alb_dim           = aws_lb.main.arn_suffix
  tg_dim            = aws_lb_target_group.app.arn_suffix
  cluster_name      = aws_ecs_cluster.main.name
  app_service_name  = aws_ecs_service.app.name
  worker_name       = aws_ecs_service.worker.name
  metrics_namespace = "CloudLab1/App"
}

resource "aws_sns_topic" "alerts" {
  name = "${var.project}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.budget_email
}

resource "aws_cloudwatch_metric_alarm" "app_cpu_high" {
  alarm_name          = "${var.project}-app-cpu-high"
  alarm_description   = "Average CPU of the app service is above ${var.cpu_alarm_threshold}% for 2 minutes"
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  dimensions          = { ClusterName = local.cluster_name, ServiceName = local.app_service_name }
  statistic           = "Average"
  period              = 60
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  threshold           = var.cpu_alarm_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "app_at_max" {
  alarm_name          = "${var.project}-app-at-max-capacity"
  alarm_description   = "The app service runs the maximum number of tasks (${var.app_max_tasks})"
  namespace           = "ECS/ContainerInsights"
  metric_name         = "RunningTaskCount"
  dimensions          = { ClusterName = local.cluster_name, ServiceName = local.app_service_name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = var.app_max_tasks
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "app_5xx" {
  alarm_name          = "${var.project}-app-5xx"
  alarm_description   = "The app returns 5xx responses"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  dimensions          = { LoadBalancer = local.alb_dim }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "no_healthy_targets" {
  alarm_name          = "${var.project}-no-healthy-targets"
  alarm_description   = "No healthy app task behind the load balancer"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HealthyHostCount"
  dimensions          = { LoadBalancer = local.alb_dim, TargetGroup = local.tg_dim }
  statistic           = "Minimum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project}-dashboard"

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric", x = 0, y = 0, width = 12, height = 7
        properties = {
          title  = "1. Кількість екземплярів: бажана і фактична"
          region = var.region
          view   = "timeSeries"
          stat   = "Average"
          period = 60
          yAxis  = { left = { min = 0, max = var.app_max_tasks + 1, showUnits = false } }
          annotations = {
            horizontal = [{ label = "max ${var.app_max_tasks}", value = var.app_max_tasks }]
          }
          metrics = [
            ["ECS/ContainerInsights", "DesiredTaskCount", "ClusterName", local.cluster_name, "ServiceName", local.app_service_name, { label = "бажана" }],
            ["ECS/ContainerInsights", "RunningTaskCount", "ClusterName", local.cluster_name, "ServiceName", local.app_service_name, { label = "фактична" }],
          ]
        }
      },
      {
        type = "metric", x = 12, y = 0, width = 12, height = 7
        properties = {
          title  = "2. Завантаження процесора (%)"
          region = var.region
          view   = "timeSeries"
          stat   = "Average"
          period = 60
          yAxis  = { left = { min = 0, max = 100 } }
          annotations = {
            horizontal = [
              { label = "ціль масштабування ${var.cpu_target_percent}%", value = var.cpu_target_percent },
              { label = "алерт ${var.cpu_alarm_threshold}%", value = var.cpu_alarm_threshold, color = "#d62728" },
            ]
          }
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ClusterName", local.cluster_name, "ServiceName", local.app_service_name, { label = "середній CPU" }],
            ["AWS/ECS", "CPUUtilization", "ClusterName", local.cluster_name, "ServiceName", local.app_service_name, { stat = "Maximum", label = "максимальний CPU" }],
          ]
        }
      },
      {
        type = "metric", x = 0, y = 7, width = 8, height = 7
        properties = {
          title   = "3. Запити за хвилину"
          region  = var.region
          view    = "timeSeries"
          stat    = "Sum"
          period  = 60
          metrics = [["AWS/ApplicationELB", "RequestCount", "LoadBalancer", local.alb_dim, { label = "запитів/хв" }]]
        }
      },
      {
        type = "metric", x = 8, y = 7, width = 8, height = 7
        properties = {
          title  = "4. Латентність p95 (секунди)"
          region = var.region
          view   = "timeSeries"
          period = 60
          annotations = {
            horizontal = [{ label = "500 мс", value = 0.5, color = "#ff7f0e" }]
          }
          metrics = [
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", local.alb_dim, { stat = "p95", label = "p95" }],
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", local.alb_dim, { stat = "p50", label = "p50" }],
          ]
        }
      },
      {
        type = "metric", x = 16, y = 7, width = 8, height = 7
        properties = {
          title  = "5. Відповіді 5xx за хвилину"
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
        type = "metric", x = 0, y = 14, width = 8, height = 7
        properties = {
          title  = "Кеш: влучання, промахи, запити до БД за хвилину"
          region = var.region
          view   = "timeSeries"
          stat   = "Sum"
          period = 60
          yAxis  = { right = { min = 0, max = 100 } }
          metrics = [
            [local.metrics_namespace, "CacheHits", "Service", "app", { id = "hits", label = "влучання" }],
            [local.metrics_namespace, "CacheMisses", "Service", "app", { id = "misses", label = "промахи" }],
            [local.metrics_namespace, "CacheBypass", "Service", "app", { label = "кеш вимкнено" }],
            [local.metrics_namespace, "DbQueries", "Service", "app", { label = "запити до БД (GET /notes)" }],
            [{ expression = "100 * hits / (hits + misses)", label = "% влучань", yAxis = "right" }],
          ]
        }
      },
      {
        type = "metric", x = 8, y = 14, width = 8, height = 7
        properties = {
          title  = "Навантаження на базу даних"
          region = var.region
          view   = "timeSeries"
          period = 60
          metrics = [
            ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", aws_db_instance.main.identifier, { stat = "Average", label = "CPU бази %" }],
            ["AWS/RDS", "DatabaseConnections", "DBInstanceIdentifier", aws_db_instance.main.identifier, { stat = "Maximum", label = "з'єднання", yAxis = "right" }],
          ]
        }
      },
      {
        type = "alarm", x = 16, y = 14, width = 8, height = 7
        properties = {
          title = "Стан алертів"
          alarms = [
            aws_cloudwatch_metric_alarm.app_cpu_high.arn,
            aws_cloudwatch_metric_alarm.app_at_max.arn,
            aws_cloudwatch_metric_alarm.app_5xx.arn,
            aws_cloudwatch_metric_alarm.no_healthy_targets.arn,
          ]
        }
      },
      {
        type = "metric", x = 0, y = 21, width = 12, height = 7
        properties = {
          title  = "Черга: довжина і пропускна здатність"
          region = var.region
          view   = "timeSeries"
          period = 60
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.jobs.name, { stat = "Maximum", label = "повідомлень у черзі" }],
            ["AWS/SQS", "NumberOfMessagesSent", "QueueName", aws_sqs_queue.jobs.name, { stat = "Sum", label = "надіслано/хв" }],
            ["AWS/SQS", "NumberOfMessagesDeleted", "QueueName", aws_sqs_queue.jobs.name, { stat = "Sum", label = "оброблено/хв" }],
            ["AWS/SQS", "ApproximateAgeOfOldestMessage", "QueueName", aws_sqs_queue.jobs.name, { stat = "Maximum", label = "вік найстарішого, с", yAxis = "right" }],
          ]
        }
      },
      {
        type = "metric", x = 12, y = 21, width = 12, height = 7
        properties = {
          title  = "Обробники черги: бажана і фактична кількість"
          region = var.region
          view   = "timeSeries"
          stat   = "Average"
          period = 60
          yAxis  = { left = { min = 0, max = var.worker_max_tasks + 1, showUnits = false } }
          metrics = [
            ["ECS/ContainerInsights", "DesiredTaskCount", "ClusterName", local.cluster_name, "ServiceName", local.worker_name, { label = "бажана" }],
            ["ECS/ContainerInsights", "RunningTaskCount", "ClusterName", local.cluster_name, "ServiceName", local.worker_name, { label = "фактична" }],
          ]
        }
      },
      {
        type = "log", x = 0, y = 28, width = 24, height = 7
        properties = {
          title  = "Останні логи застосунку"
          region = var.region
          view   = "table"
          query  = "SOURCE '${aws_cloudwatch_log_group.app.name}' | fields @timestamp, @message | filter @message not like /_aws/ | sort @timestamp desc | limit 20"
        }
      },
    ]
  })
}
