# Хмарні технології — лабораторні роботи (осінь 2026)

Один репозиторій для всіх трьох лабораторних. Кожна лаба — в окремій папці.

| Лаба | Тема | Папка | Статус |
|---|---|---|---|
| 1 | Розгортання застосунку в AWS: Docker, Terraform, ECS Fargate, RDS, ALB, CI/CD | [`Lab1/`](Lab1/) | у роботі |
| 2 | — | `Lab2/` | ще не почата |
| 3 | — | `Lab3/` | ще не почата |

## Лаба 1 — коротко

**Застосунок:** Notes API — REST API для нотаток (Python, FastAPI + PostgreSQL), з документацією Swagger на `/docs`.

**Публічна адреса:** `http://<ALB_DNS>` ← буде додано після `terraform apply`

**Хмара:** AWS (`eu-central-1`) — ECR, RDS PostgreSQL у приватній підмережі, ECS Fargate за Application Load Balancer; уся інфраструктура в Terraform; автоматичний деплой через GitHub Actions з OIDC (без збережених ключів).

Детальний опис, архітектура, ендпоінти й інструкції запуску — у [`Lab1/README.md`](Lab1/README.md).

## Структура репозиторію

```
.github/workflows/
  lab1-deploy.yml   — CI/CD для Лаби 1 (запускається лише при змінах у Lab1/)
Lab1/
  app/              — код застосунку
  Dockerfile, compose.yaml
  terraform/        — уся інфраструктура AWS
  README.md         — повний опис Лаби 1
Lab2/, Lab3/        — наступні лабораторні
```
