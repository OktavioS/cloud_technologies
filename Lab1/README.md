# Notes API — Лабораторна робота 1 (Хмарні технології)

REST API для нотаток (FastAPI + PostgreSQL), розгорнутий в **AWS** через **Terraform**:
ECS Fargate за Application Load Balancer, керована база RDS PostgreSQL у приватній підмережі,
образи в приватному ECR, автоматичний деплой з GitHub Actions через OIDC.

**Публічна адреса:** http://cloudlab1-alb-491227470.eu-north-1.elb.amazonaws.com
**Swagger UI:** http://cloudlab1-alb-491227470.eu-north-1.elb.amazonaws.com/docs

> **Як усе підняти, запустити й перевірити кожну вимогу лаби** — розділ «Інструкція: від нуля до перевірки всіх вимог» нижче.

## Ендпоінти

🔒 — потрібен заголовок `Authorization: Bearer <токен>`, без нього відповідь **401**.

| Метод | Шлях | Опис |
|---|---|---|
| GET | `/` | Інформація про сервіс і версію (хеш коміту) |
| GET | `/health` | Health check (процес + з'єднання з БД) |
| POST | `/auth/register` | Реєстрація `{"username": "...", "password": "..."}` (пароль ≥ 8 символів) |
| POST | `/auth/login` | Вхід → `{"access_token": "...", "token_type": "bearer"}` (токен діє 60 хв) |
| GET 🔒 | `/auth/me` | Хто я (ім'я з токена) |
| GET | `/notes` | Список нотаток |
| GET | `/notes/{id}` | Одна нотатка |
| POST 🔒 | `/notes` | Створити `{"title": "...", "body": "..."}` |
| PUT 🔒 | `/notes/{id}` | Оновити |
| DELETE 🔒 | `/notes/{id}` | Видалити |
| GET | `/debug/error` | Навмисна помилка 500 — для демонстрації алерту на 5xx |
| GET | `/docs` | Swagger UI (OpenAPI), кнопка **Authorize** для токена |

## Бонусні завдання

**6. Безпека доступу (JWT).** Сервіс сам видає і перевіряє JWT (HS256, PyJWT). Паролі в БД лише як сіль + хеш PBKDF2-SHA256. Ключ підпису `JWT_SECRET` генерує AWS і зберігає в Secrets Manager (`terraform/auth.tf`), у контейнер він потрапляє як змінна середовища через `secrets` у task definition.

**7. Моніторинг** (`terraform/monitoring.tf`). Логи застосунку — CloudWatch Logs `/ecs/cloudlab1-app`. Дашборд `cloudlab1-dashboard`: кількість запитів, помилки 5xx, латентність (середня і p95), CPU/пам'ять контейнера, стан алертів, останні логи. Алерти з доставкою на email через SNS: помилки 5xx і відсутність здорових контейнерів. Посилання на дашборд: `terraform output dashboard_url`.

**8. Документація API.** Swagger UI на `/docs`.

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

Логи й метрики → CloudWatch (дашборд, алерти) → SNS → email
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
    auth.tf         — секрет для підпису JWT (бонус 6)
    monitoring.tf   — дашборд CloudWatch, алерти, SNS (бонус 7)
    outputs.tf
```

## Інструкція: від нуля до перевірки всіх вимог

Усі команди — для **PowerShell** (Windows). Шляхи — від кореня репозиторію.

### 0. Передумови (один раз)

| Що | Перевірка |
|---|---|
| Git, Docker Desktop, Terraform ≥ 1.6, AWS CLI v2 | `git --version; docker --version; terraform --version; aws --version` |
| AWS-акаунт: MFA на root, окремий IAM-користувач (не root) | консоль AWS → Security credentials → MFA |
| Ключі IAM-користувача підключені | `aws configure` (регіон `eu-north-1`, формат `json`) |
| Працюємо НЕ від root | `aws sts get-caller-identity` → в `Arn` має бути `user/lab-admin` |

### 1. Локальний запуск (завдання 1)

Docker Desktop має бути запущений (*Engine running*).

```powershell
cd Lab1
copy .env.example .env        # один раз; у .env задати DB_PASSWORD і JWT_SECRET
docker compose up --build -d  # застосунок + PostgreSQL однією командою
docker compose ps             # app — running, db — running (healthy)
```

Відкрити http://localhost:8000/docs. Зупинка: `docker compose down` (дані лишаються), `docker compose down -v` (видалити й дані).

### 2. Розгортання в AWS (завдання 2–4, бонуси 6–7)

```powershell
cd Lab1\terraform
copy terraform.tfvars.example terraform.tfvars   # один раз: github_repo і budget_email
terraform init

# 2.1 Спершу лише реєстр образів — щоб було куди покласти перший образ
terraform apply -target="aws_ecr_repository.app"

# 2.2 Перший образ з тегом bootstrap
$REPO = aws ecr describe-repositories --repository-names cloudlab1-app --query "repositories[0].repositoryUri" --output text
$REGISTRY = $REPO.Split('/')[0]
$PW = aws ecr get-login-password --region eu-north-1   # через змінну: PowerShell 5.1 псує пароль у "|"
docker login --username AWS --password $PW $REGISTRY
docker build -t "${REPO}:bootstrap" ..
docker push "${REPO}:bootstrap"

# 2.3 Уся інфраструктура (~10–15 хв, найдовше — RDS)
terraform apply
terraform output
```

Після `apply`:

- на пошту прийде лист **AWS Notification - Subscription Confirmation** → натиснути **Confirm subscription** (інакше алерти не приходитимуть);
- через 1–3 хв застосунок відповість на `terraform output -raw app_url`.

### 3. Підключення GitHub (завдання 5, один раз)

GitHub → репозиторій → **Settings → Secrets and variables → Actions → Variables → New repository variable**:

- Name: `AWS_ROLE_ARN`
- Value: результат `terraform output -raw github_deploy_role_arn`

Це не секрет (лише адреса ролі). Ключів доступу в GitHub немає — вхід через OIDC.

### 4. Перевірка кожної вимоги

Спершу збережемо адресу застосунку (з папки `Lab1\terraform`):

```powershell
$URL = terraform output -raw app_url
```

**Завдання 1 — контейнер**

```powershell
cd ..                                            # у Lab1
docker compose exec app whoami                   # appuser — процес НЕ від root
Select-String -Path Dockerfile -Pattern "FROM"   # python:3.12.8-slim-bookworm — версія зафіксована, не latest
docker compose down; docker compose up -d        # перезапуск…
# …і GET /notes у http://localhost:8000/docs — дані на місці (volume pgdata)
docker volume ls                                 # є lab1_pgdata
```

Порядок шарів: у `Dockerfile` спершу `COPY requirements.txt` + `pip install`, потім `COPY app/` — при зміні коду `pip install` береться з кешу (видно `CACHED` у `docker compose build`).

**Завдання 2 — Terraform, керована БД, публічна адреса**

```powershell
cd terraform
terraform state list                             # усе, чим керує Terraform (~46 ресурсів)
Invoke-RestMethod "$URL/health"                  # {"status":"ok"} — застосунок живий і бачить БД
Invoke-RestMethod "$URL/notes"                   # дані з RDS
aws ecs describe-task-definition --task-definition cloudlab1-app --query "taskDefinition.containerDefinitions[0].[environment,secrets]"
# DB_HOST/DB_USER… — звичайні змінні; DB_PASSWORD і JWT_SECRET — з Secrets Manager (лише ARN, не значення)
```

**Завдання 3 — мережева ізоляція**

```powershell
aws rds describe-db-instances --db-instance-identifier cloudlab1-db --query "DBInstances[0].PubliclyAccessible"
# false — у бази немає публічної адреси
aws ec2 describe-security-groups --filters Name=group-name,Values=cloudlab1-db-sg --query "SecurityGroups[0].IpPermissions"
# порт 5432 відкритий лише для UserIdGroupPairs (SG застосунку), IpRanges порожній
aws ec2 describe-security-groups --filters Name=group-name,Values=cloudlab1-app-sg --query "SecurityGroups[0].IpPermissions"
# порт 8000 — лише від SG балансувальника
```

**Завдання 4 — балансувальник і health check**

```powershell
$TG = aws elbv2 describe-target-groups --names cloudlab1-tg --query "TargetGroups[0].TargetGroupArn" --output text
aws elbv2 describe-target-groups --names cloudlab1-tg --query "TargetGroups[0].[HealthCheckPath,HealthCheckIntervalSeconds]"
aws elbv2 describe-target-health --target-group-arn $TG --query "TargetHealthDescriptions[].TargetHealth.State"
# "/health", 15 і "healthy"
```

**Завдання 5 — автоматичний деплой**

```powershell
# 1. Змінити щось у Lab1\app\main.py (наприклад, текст у функції root)
git add -A; git commit -m "demo change"; git push
# 2. GitHub → Actions → дочекатися зеленої галочки (3–6 хв)
Invoke-RestMethod "$URL/"                        # version = хеш останнього коміту
git log -1 --format=%H                           # той самий хеш
aws ecr list-images --repository-name cloudlab1-app --query "imageIds[].imageTag"   # теги = хеші комітів
```

**Бонус 6 — JWT, 401 без токена**

```powershell
# без токена → 401
try { Invoke-RestMethod -Method Post -Uri "$URL/notes" -ContentType "application/json" -Body '{"title":"no token"}' } catch { $_.Exception.Response.StatusCode.value__ }

# реєстрація (один раз), вхід, запит з токеном → 201
Invoke-RestMethod -Method Post -Uri "$URL/auth/register" -ContentType "application/json" -Body '{"username":"demo","password":"demopass123"}'
$TOKEN = (Invoke-RestMethod -Method Post -Uri "$URL/auth/login" -ContentType "application/json" -Body '{"username":"demo","password":"demopass123"}').access_token
Invoke-RestMethod -Method Post -Uri "$URL/notes" -ContentType "application/json" -Headers @{Authorization="Bearer $TOKEN"} -Body '{"title":"with token"}'
```

Те саме мишкою: Swagger `/docs` → `/auth/login` → кнопка **Authorize**.

**Бонус 7 — моніторинг**

```powershell
terraform output -raw dashboard_url              # відкрити в браузері (акаунт Just Ship It, регіон Stockholm)
1..10 | ForEach-Object { try { Invoke-WebRequest "$URL/debug/error" -UseBasicParsing } catch {} }   # 10 помилок 500
# через 3–6 хв — лист "ALARM: cloudlab1-app-5xx" на пошту
aws cloudwatch describe-alarms --alarm-names cloudlab1-app-5xx --query "MetricAlarms[0].[StateValue,StateReason]"
aws logs tail /ecs/cloudlab1-app --since 10m     # логи застосунку з CloudWatch
```

**Бонус 8 — документація API:** `$URL/docs` у браузері.

**Бюджет:** `aws budgets describe-budgets --account-id (aws sts get-caller-identity --query Account --output text) --query "Budgets[].[BudgetName,BudgetLimit.Amount]"`

### 5. Видалення всього

```powershell
cd Lab1\terraform
terraform destroy          # yes; ~10 хв
terraform state list       # порожньо — у хмарі нічого не лишилось
```

Реєстр видаляється разом з образами (`force_delete`), секрети — одразу (`recovery_window_in_days = 0`), база — без фінального знімка.

Після повторного розгортання (`розділ 2`) адреса балансувальника буде **нова** — оновити її в README. Змінна `AWS_ROLE_ARN` у GitHub лишається тією ж.

**Відкат на попередню версію:** `git revert <хеш>` → `git push`, або GitHub → Actions → старий успішний запуск → *Re-run jobs*. Невдалий деплой ECS відкочує сам (circuit breaker).

## Примітки щодо рішень

- **Секрети.** Пароль БД генерує RDS і зберігає в Secrets Manager; ECS підставляє його в `DB_PASSWORD` при старті задачі. Ключ JWT — так само (`JWT_SECRET`). У репозиторії й образі секретів немає; Terraform state (може містити ключ JWT) — у `.gitignore`.
- **Мережа.** Задачі Fargate у публічних підмережах з публічною IP лише для вихідного трафіку (ECR, CloudWatch) без платного NAT Gateway; вхідний трафік на них заборонений — дозволено тільки від SG балансувальника.
- **OIDC.** GitHub тепер підписує `sub` з незмінними ID (`repo:owner@<id>/name@<id>:ref:…`), тому trust policy приймає обидва формати (`github_oidc.tf`).
- **Регіон.** `eu-north-1` (Стокгольм): AWS-проєкт створено в ньому.
- **Економія.** `db.t4g.micro`, Single-AZ, без бекапів/PITR — для навчального середовища; у продакшні — Multi-AZ і `backup_retention_period >= 7`.
