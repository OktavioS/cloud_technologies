variable "region" {
  description = "AWS-регіон"
  type        = string
  default     = "eu-central-1"
}

variable "project" {
  description = "Префікс для імен ресурсів"
  type        = string
  default     = "cloudlab1"
}

variable "image_tag" {
  description = "Тег образу для першого деплою (далі тег = хеш коміту, його ставить CI)"
  type        = string
  default     = "bootstrap"
}

variable "github_repo" {
  description = "GitHub-репозиторій у форматі owner/name — лише йому дозволено брати роль через OIDC"
  type        = string
}

variable "budget_email" {
  description = "Email для сповіщень бюджету"
  type        = string
}

variable "budget_limit_usd" {
  description = "Місячний ліміт бюджету, USD"
  type        = string
  default     = "10"
}
