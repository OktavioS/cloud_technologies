# Бонус 6: ключ, яким сервіс підписує і перевіряє JWT-токени.
# Генерує AWS, зберігається в Secrets Manager; у код, образ і git не потрапляє.

data "aws_secretsmanager_random_password" "jwt" {
  password_length     = 48
  exclude_punctuation = true
}

resource "aws_secretsmanager_secret" "jwt" {
  name                    = "${var.project}-jwt-secret"
  recovery_window_in_days = 0 # щоб terraform destroy видаляв одразу, без 7-денного «кошика»
}

resource "aws_secretsmanager_secret_version" "jwt" {
  secret_id     = aws_secretsmanager_secret.jwt.id
  secret_string = data.aws_secretsmanager_random_password.jwt.random_password

  # data-джерело генерує новий пароль при кожному plan — ігноруємо, щоб ключ не мінявся
  lifecycle {
    ignore_changes = [secret_string]
  }
}
