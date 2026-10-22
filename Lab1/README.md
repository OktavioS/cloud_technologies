# Notes API — Лабораторна робота 1 (Хмарні технології)

REST API для нотаток (FastAPI + PostgreSQL), розгорнутий в **AWS** через **Terraform**:
ECS Fargate за Application Load Balancer, керована база RDS PostgreSQL у приватній підмережі,
образи в приватному ECR, автоматичний деплой з GitHub Actions через OIDC.

**Публічна адреса:** `http://<ALB_DNS>` ← вставити вивід `terraform output app_url`
**Swagger UI:** `http://<ALB_DNS>/docs`

## Ендпоінти

| Метод | Шлях | Опис |
|---|---|---|
| GET | `/` | Інформація про сервіс і версію (хеш коміту) |
| GET | `/health` | Health check (процес + з'єднання з БД) |
| GET | `/notes` | Список нотаток |
| GET | `/notes/{id}` | Одна нотатка |
| POST | `/notes` | Створити `{"title": "...", "body": "..."}` |
| PUT | `/notes/{id}` | Оновити |
| DELETE | `/notes/{id}` | Видалити |
| GET | `/docs` | Swagger UI (OpenAPI) |

## Архітектура

```
Internet ──► ALB (public subnets, SG: 80 з інтернету)
                │  health check /health
                ▼
           ECS Fargate task (SG: 8000 лише від SG балансувальника)
                │  пароль з Secrets Manager → змінна середовища DB_PASSWORD
                ▼
           RDS PostgreSQL (private subnets, без публічної адреси, SG: 5432 лише від SG застосунку)

GitHub push → Actions (OIDC → IAM role) → docker build → ECR:<sha коміту> → нова task definition → ECS
```

## Структура проєкту

Лаба лежить у папці `Lab1/` спільного репозиторію з усіма лабами курсу.

```
.github/workflows/lab1-deploy.yml  — CI/CD (у корені репозиторію: GitHub бачить workflows лише там)
Lab1/
  app/main.py, requirements.txt    — код застосунку
  Dockerfile, .dockerignore        — образ (python:3.12.8-slim-bookworm, non-root)
  compose.yaml, .env.example       — локальний запуск із PostgreSQL
  terraform/
    versions.tf     — провайдер AWS
    variables.tf    — змінні; terraform.tfvars.example — приклад значень
    network.tf      — VPC, публічні/приватні підмережі, security groups
    database.tf     — RDS PostgreSQL (пароль керує AWS Secrets Manager)
    ecr.tf          — приватний реєстр образів
    alb.tf          — балансувальник, target group, health check
    ecs.tf          — кластер, IAM-ролі, task definition, сервіс, логи CloudWatch
    github_oidc.tf  — OIDC-провайдер GitHub і роль для CI/CD
    budget.tf       — бюджет зі сповіщеннями на email
    outputs.tf
```

## Локальний запуск

```bash
cp .env.example .env          # задати DB_PASSWORD
docker compose up --build     # http://localhost:8000/docs
docker compose down           # дані залишаються у volume pgdata
```

## Розгортання в AWS

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # заповнити github_repo і budget_email
terraform init

# 1. Спершу лише реєстр, щоб було куди покласти перший образ
terraform apply -target=aws_ecr_repository.app

# 2. Перший образ з тегом bootstrap
REPO=$(terraform output -raw ecr_repository_url)
aws ecr get-login-password --region eu-central-1 | docker login --username AWS --password-stdin ${REPO%%/*}
docker build -t $REPO:bootstrap .. && docker push $REPO:bootstrap

# 3. Уся інфраструктура (~10 хв, найдовше — RDS)
terraform apply
terraform output app_url
```

Далі — у GitHub: **Settings → Secrets and variables → Actions → Variables** додати
`AWS_ROLE_ARN` = `terraform output -raw github_deploy_role_arn`. Після цього кожен push у `main`
сам збирає образ з тегом = хеш коміту і оновлює сервіс.

**Відкат:** `Actions → Deploy → Re-run` на старому коміті, або ECS сам відкочує невдалий деплой (circuit breaker).

## Видалення

```bash
cd terraform && terraform destroy
```

## Примітки щодо рішень

- **Секрети.** Пароль БД генерує RDS і зберігає в Secrets Manager; ECS підставляє його в `DB_PASSWORD` при старті задачі. В репозиторії, образі і Terraform state пароля немає.
- **Мережа.** Задачі Fargate у публічних підмережах з публічною IP лише для вихідного трафіку (ECR, CloudWatch) без платного NAT Gateway; вхідний трафік на них заборонений — дозволено тільки від SG балансувальника.
- **Економія.** `db.t4g.micro`, Single-AZ, без бекапів/PITR — для навчального середовища; у продакшні — Multi-AZ і `backup_retention_period >= 7`.
