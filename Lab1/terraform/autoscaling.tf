resource "aws_appautoscaling_target" "app" {
  service_namespace  = "ecs"
  scalable_dimension = "ecs:service:DesiredCount"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.app.name}"
  min_capacity       = var.app_min_tasks
  max_capacity       = var.app_max_tasks
}

resource "aws_appautoscaling_policy" "app_cpu" {
  name               = "${var.project}-app-cpu-target"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.app.service_namespace
  scalable_dimension = aws_appautoscaling_target.app.scalable_dimension
  resource_id        = aws_appautoscaling_target.app.resource_id

  target_tracking_scaling_policy_configuration {
    target_value       = var.cpu_target_percent
    scale_out_cooldown = var.scale_out_cooldown
    scale_in_cooldown  = var.scale_in_cooldown

    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}

resource "aws_appautoscaling_scheduled_action" "day" {
  count              = var.enable_schedule ? 1 : 0
  name               = "${var.project}-app-day"
  service_namespace  = aws_appautoscaling_target.app.service_namespace
  scalable_dimension = aws_appautoscaling_target.app.scalable_dimension
  resource_id        = aws_appautoscaling_target.app.resource_id
  schedule           = var.day_start_cron
  timezone           = var.schedule_timezone

  scalable_target_action {
    min_capacity = var.day_min_tasks
    max_capacity = var.app_max_tasks
  }
}

resource "aws_appautoscaling_scheduled_action" "night" {
  count              = var.enable_schedule ? 1 : 0
  name               = "${var.project}-app-night"
  service_namespace  = aws_appautoscaling_target.app.service_namespace
  scalable_dimension = aws_appautoscaling_target.app.scalable_dimension
  resource_id        = aws_appautoscaling_target.app.resource_id
  schedule           = var.night_start_cron
  timezone           = var.schedule_timezone

  scalable_target_action {
    min_capacity = var.night_min_tasks
    max_capacity = var.app_max_tasks
  }

  depends_on = [aws_appautoscaling_scheduled_action.day]
}

resource "aws_appautoscaling_target" "worker" {
  service_namespace  = "ecs"
  scalable_dimension = "ecs:service:DesiredCount"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.worker.name}"
  min_capacity       = var.worker_min_tasks
  max_capacity       = var.worker_max_tasks
}

resource "aws_appautoscaling_policy" "worker_backlog" {
  name               = "${var.project}-worker-backlog-target"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.worker.service_namespace
  scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension
  resource_id        = aws_appautoscaling_target.worker.resource_id

  target_tracking_scaling_policy_configuration {
    target_value       = var.worker_backlog_per_task
    scale_out_cooldown = 30
    scale_in_cooldown  = 60

    customized_metric_specification {
      metrics {
        id          = "visible"
        label       = "Visible messages"
        return_data = false

        metric_stat {
          stat = "Sum"

          metric {
            namespace   = "AWS/SQS"
            metric_name = "ApproximateNumberOfMessagesVisible"

            dimensions {
              name  = "QueueName"
              value = aws_sqs_queue.jobs.name
            }
          }
        }
      }

      metrics {
        id          = "workers"
        label       = "Running workers"
        return_data = false

        metric_stat {
          stat = "Average"

          metric {
            namespace   = "ECS/ContainerInsights"
            metric_name = "RunningTaskCount"

            dimensions {
              name  = "ClusterName"
              value = aws_ecs_cluster.main.name
            }

            dimensions {
              name  = "ServiceName"
              value = aws_ecs_service.worker.name
            }
          }
        }
      }

      metrics {
        id          = "backlog"
        label       = "Backlog per worker"
        expression  = "visible / workers"
        return_data = true
      }
    }
  }
}
