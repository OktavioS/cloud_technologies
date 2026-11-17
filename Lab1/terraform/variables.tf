variable "region" {
  description = "AWS region"
  type        = string
  default     = "eu-north-1"
}

variable "project" {
  description = "Prefix for resource names"
  type        = string
  default     = "cloudlab1"
}

variable "image_tag" {
  description = "Image tag for the first deployment; afterwards CI sets the commit SHA"
  type        = string
  default     = "bootstrap"
}

variable "github_repo" {
  description = "GitHub repository owner/name allowed to assume the deploy role"
  type        = string
}

variable "budget_email" {
  description = "Email for budget and monitoring alerts"
  type        = string
}

variable "budget_limit_usd" {
  description = "Monthly budget limit, USD"
  type        = string
  default     = "10"
}

variable "app_min_tasks" {
  description = "Minimum number of app tasks"
  type        = number
  default     = 1
}

variable "app_max_tasks" {
  description = "Maximum number of app tasks"
  type        = number
  default     = 4

  validation {
    condition     = var.app_max_tasks >= 3 && var.app_max_tasks <= 4
    error_message = "Lab 2 requires a maximum of 3 or 4 instances."
  }
}

variable "cpu_target_percent" {
  description = "Target average CPU utilization for target tracking"
  type        = number
  default     = 60
}

variable "scale_out_cooldown" {
  description = "Seconds after a scale-out before the next scale-out may start"
  type        = number
  default     = 60
}

variable "scale_in_cooldown" {
  description = "Seconds after a scale-in before the next scale-in may start"
  type        = number
  default     = 120
}

variable "cpu_alarm_threshold" {
  description = "CPU percent that triggers the overload email"
  type        = number
  default     = 70
}

variable "cache_ttl_seconds" {
  description = "TTL of cached GET /notes pages"
  type        = number
  default     = 30

  validation {
    condition     = var.cache_ttl_seconds >= 30 && var.cache_ttl_seconds <= 60
    error_message = "Lab 2 requires a TTL of 30-60 seconds."
  }
}

variable "redis_image" {
  description = "Redis image for the cache service"
  type        = string
  default     = "public.ecr.aws/docker/library/redis:7.4.1-alpine"
}

variable "worker_min_tasks" {
  description = "Minimum number of queue workers"
  type        = number
  default     = 1
}

variable "worker_max_tasks" {
  description = "Maximum number of queue workers"
  type        = number
  default     = 4
}

variable "worker_backlog_per_task" {
  description = "Target number of visible messages per worker task"
  type        = number
  default     = 20
}

variable "worker_delay_ms" {
  description = "Simulated work per message, ms"
  type        = number
  default     = 200
}

variable "enable_schedule" {
  description = "Scheduled minimum capacity: day_min_tasks during the day, night_min_tasks at night"
  type        = bool
  default     = false
}

variable "schedule_timezone" {
  description = "IANA timezone for scheduled scaling"
  type        = string
  default     = "Europe/Kiev"
}

variable "day_start_cron" {
  description = "When the day schedule starts"
  type        = string
  default     = "cron(0 8 * * ? *)"
}

variable "night_start_cron" {
  description = "When the night schedule starts"
  type        = string
  default     = "cron(0 23 * * ? *)"
}

variable "day_min_tasks" {
  description = "Minimum app tasks during the day"
  type        = number
  default     = 2
}

variable "night_min_tasks" {
  description = "Minimum app tasks at night"
  type        = number
  default     = 1
}
