resource "aws_ecr_repository" "app" {
  name                 = "${var.project}-app"
  image_tag_mutability = "IMMUTABLE" # тег = хеш коміту, перезаписувати не можна
  force_delete         = true        # щоб terraform destroy прибрав і образи

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Тримаємо лише 10 останніх образів
resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep last 10 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}
