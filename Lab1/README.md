# Notes API — Лабораторні роботи 1 і 2 (Хмарні технології)

REST API для нотаток (FastAPI + PostgreSQL), розгорнутий в **AWS** через **Terraform**.

- **Лаба 1:** контейнер, ECS Fargate за Application Load Balancer, RDS PostgreSQL у приватній підмережі, ECR, CI/CD з GitHub Actions через OIDC; бонуси JWT, моніторинг, Swagger.
- **Лаба 2:** у **тому самому Terraform-проєкті й репозиторії** (так вимагає умова): автомасштабування, навантажувальний тест, панель моніторингу, сповіщення, кешування; бонуси черга, ідемпотентність, масштабування за розкладом.

**Публічна адреса:** http://cloudlab1-alb-1551329071.eu-north-1.elb.amazonaws.com
**Swagger UI:** http://cloudlab1-alb-1551329071.eu-north-1.elb.amazonaws.com/docs

> **Як усе підняти, запустити й перевірити кожну вимогу** — розділ «Інструкція» нижче.

## Вимоги і де вони виконані

### Лаба 1

| № | Вимога | Де |
|---|---|---|
| 1 | Docker + compose з volume, фіксована версія base image, залежності окремим шаром, non-root | `Dockerfile`, `compose.yaml` |
| 2 | Terraform: реєстр, керована БД, сервіс контейнера, публічна адреса; `apply` з нуля і `destroy` без залишку | `terraform/` |
| 3 | БД у приватній підмережі, SG БД лише від SG застосунку | `terraform/network.tf`, `database.tf` |
| 4 | Керований балансувальник з health check | `terraform/alb.tf` |
| 5 | GitHub Actions: push → build → ECR з тегом = SHA → оновлення сервісу, OIDC | `.github/workflows/lab1-deploy.yml`, `terraform/github_oidc.tf` |
| Б6 | JWT, 401 без токена | `app/auth.py`, `terraform/secrets.tf` |
| Б7 | Логи + дашборд + алерт на email у Terraform | `terraform/monitoring.tf` |
| Б8 | Swagger | `/docs` |

### Лаба 2

| № | Вимога | Де | Звіт |
|---|---|---|---|
| 1 | Автомасштабування 1–4 задачі, target tracking CPU 60 % | `terraform/autoscaling.tf` | [`docs/AUTOSCALING.md`](docs/AUTOSCALING.md) |
| 2 | Сценарій навантаження «мало записів, багато читань», 3 фази, одна команда | `loadtest/` | [`docs/LOADTEST.md`](docs/LOADTEST.md) |
| 3 | Панель: екземпляри, CPU, запити/хв, p95, 5xx | `terraform/monitoring.tf` | [`docs/AUTOSCALING.md`](docs/AUTOSCALING.md) |
| 4 | Лист при CPU > 70 % 2 хв і лист при поверненні до норми | `terraform/monitoring.tf` | [`docs/ALERTS.md`](docs/ALERTS.md) |
| 5 | Cache-aside для списку постів у Redis, TTL 30 с | `app/cache.py`, `terraform/redis.tf` | [`docs/CACHE.md`](docs/CACHE.md) |
| Б6 | Запис через чергу SQS → `202`, обробник масштабується від довжини черги | `app/worker.py`, `terraform/queue.tf` | [`docs/QUEUE.md`](docs/QUEUE.md) |
| Б7 | `Idempotency-Key` у Redis на 24 год + тест | `app/idempotency.py`, `tests/` | [`docs/IDEMPOTENCY.md`](docs/IDEMPOTENCY.md) |
| Б8 | Мінімум екземплярів удень 2, уночі 1 | `terraform/autoscaling.tf` | [`docs/SCHEDULE.md`](docs/SCHEDULE.md) |

## Ендпоінти

🔒 — потрібен заголовок `Authorization: Bearer <токен>`, без нього **401**. 🔑 — заголовок `X-Admin-Token` (токен у Secrets Manager).

| Метод | Шлях | Опис |
|---|---|---|
| GET | `/` | Сервіс і версія (хеш коміту) |
| GET | `/health` | Health check (процес + БД) |
| POST | `/auth/register` | Реєстрація `{"username": "...", "password": "..."}` |
| POST | `/auth/login` | Вхід → `access_token`, `user_id` |
| GET 🔒 | `/auth/me` | Хто я |
| GET | `/users/{id}` | Автор: ім'я, дата, кількість постів |
| GET | `/notes?limit=20&offset=0` | Список, новіші першими; **кешується**, заголовок `X-Cache: HIT/MISS/BYPASS` |
| GET | `/notes/{id}` | Один пост |
| POST 🔒 | `/notes` | Створити; необов'язковий заголовок `Idempotency-Key` |
| POST 🔒 | `/notes/async` | Створити через чергу → `202` + `job_id` |
| GET 🔒 | `/jobs/{job_id}` | Статус асинхронного створення |
| PUT / DELETE 🔒 | `/notes/{id}` | Змінити / видалити (лише автор) |
| GET / PUT 🔑 | `/admin/cache` | Стан кешу / увімкнути-вимкнути `{"enabled": false}` |
| GET / DELETE 🔑 | `/admin/stats` | Лічильники кешу й запитів до БД / обнулити |
| GET | `/debug/error` | Навмисна 500 для демо алерту |
| GET | `/docs` | Swagger UI |

## Архітектура

```
                          Інтернет
                             │ :80
                   ┌─────────▼──────────┐
                   │ ALB (health /health)│
                   └─────────┬──────────┘
                             │ :8000, лише від SG балансувальника
  ┌──────────────────────────▼───────────────────────────┐   Application Auto Scaling:
  │ ECS Fargate: cloudlab1-service (1…4 задачі)           │◄── CPU 60 %, розклад день/ніч
  │ app/main.py                                           │
  └────┬───────────────┬──────────────────────┬──────────┘
       │ SQL           │ кеш, ідемпотентність, │ SendMessage
       │               │ статуси задач         │
       │      ┌────────▼─────────┐      ┌──────▼───────┐
       │      │ Redis (ECS)       │      │ SQS jobs     │──► DLQ після 5 спроб
       │      │ redis.cloudlab1   │      └──────┬───────┘
       │      │ .local (Cloud Map)│             │ Receive / Delete
       │      └────────▲─────────┘      ┌──────▼──────────────────────┐
       │               └────────────────┤ ECS: cloudlab1-worker (1…4)  │◄── 20 повідомлень на обробник
       │                                └──────┬──────────────────────┘
  ┌────▼────────────────────────────────────────▼───┐
  │ RDS PostgreSQL 16, приватні підмережі            │
  └─────────────────────────────────────────────────┘

CloudWatch: метрики ECS / Container Insights / ALB / RDS / SQS + власні (EMF) → дашборд, алерти → SNS → email
GitHub push → Actions (OIDC) → ECR:<sha> → нові task definition для app і worker
```

## Структура проєкту

```
.github/workflows/lab1-deploy.yml   — CI/CD (у корені репозиторію)
Lab1/
  app/
    main.py          — API
    worker.py        — обробник черги (той самий образ, інша команда)
    cache.py         — cache-aside і перемикач кешу
    idempotency.py   — Idempotency-Key
    jobs.py          — SQS і статуси задач
    auth.py          — JWT і паролі
    db.py            — пул з'єднань і міграції
    metrics.py       — лічильники → CloudWatch (EMF) і Redis
    settings.py      — налаштування зі змінних середовища
  Dockerfile, compose.yaml, .env.example
  terraform/
    network.tf       — VPC, підмережі, SG (alb, app, worker, redis, db)
    database.tf      — RDS PostgreSQL
    ecr.tf, alb.tf
    ecs.tf           — кластер (Container Insights), app і worker
    redis.tf         — Redis як сервіс ECS + Cloud Map
    queue.tf         — SQS + dead-letter queue
    iam.tf           — ролі задач (least privilege)
    secrets.tf       — ключ JWT, адмін-токен, пароль Redis
    autoscaling.tf   — масштабування app (CPU, розклад) і worker (черга)
    monitoring.tf    — дашборд, алерти, SNS
    github_oidc.tf, budget.tf, variables.tf, outputs.tf, versions.tf
  loadtest/          — notes.js (k6), run.ps1, admin.ps1, results/
  tests/             — test_idempotency.py, run.ps1
  docs/              — звіти Лаби 2 і знімки в docs/img/
```

---

## Інструкція

Усі команди — **PowerShell**, Docker Desktop запущений (*Engine running*).

### 0. Передумови (один раз)

```powershell
git --version; docker --version; terraform --version; aws --version
aws sts get-caller-identity                      # в Arn має бути user/lab-admin, не root
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   # дозволити запуск .ps1-скриптів (питає Y)
```

### 1. Локальний запуск

```powershell
cd D:\univer\Cloud_Technologies\Lab1
copy .env.example .env               # лише якщо .env ще немає; потрібні DB_PASSWORD, REDIS_PASSWORD, JWT_SECRET, ADMIN_TOKEN
docker compose up --build -d         # db, redis, elasticmq (локальна SQS), app, worker
docker compose ps                    # усі 5 — running, db і redis — healthy
```

- http://localhost:8000/docs — Swagger
- `docker compose logs -f app` / `docker compose logs -f worker` — логи
- `docker compose down` — зупинити (дані лишаються); `docker compose down -v` — разом з даними

Локальні перевірки:

```powershell
curl.exe -s -D - -o NUL http://localhost:8000/notes            # X-Cache: MISS
curl.exe -s -D - -o NUL http://localhost:8000/notes            # X-Cache: HIT
.\tests\run.ps1 -Local                                         # 4 passed (ідемпотентність і черга)
.\loadtest\admin.ps1 cache-status -Local
.\loadtest\run.ps1 -Label local -Local -Vus 10 -RampUp 20s -Steady 40s -RampDown 20s
.\loadtest\run.ps1 -Label local-async -Local -Mode async -Vus 10 -RampUp 20s -Steady 40s -RampDown 20s
.\loadtest\admin.ps1 stats -Local                              # CacheHits, CacheMisses, JobsProcessed…
```

### 2. Розгортання в AWS

```powershell
cd D:\univer\Cloud_Technologies\Lab1\terraform
copy terraform.tfvars.example terraform.tfvars   # лише якщо ще немає: github_repo і budget_email
terraform init -upgrade

terraform apply -target="aws_ecr_repository.app"

$REPO = terraform output -raw ecr_repository_url
$REGISTRY = $REPO.Split('/')[0]
$PW = aws ecr get-login-password --region eu-north-1
docker login --username AWS --password $PW $REGISTRY
docker build -t "${REPO}:bootstrap" ..
docker push "${REPO}:bootstrap"

terraform apply                                  # ~10–15 хв, найдовше — RDS
terraform output
```

Після `apply`:
- на пошту прийде **AWS Notification — Subscription Confirmation** → **Confirm subscription** (інакше листи алертів не прийдуть);
- через 2–3 хв відповідає `terraform output -raw app_url`;
- `terraform output -raw dashboard_url` — панель.

Чому образ спершу з тегом `bootstrap`: ECS-сервісу потрібен образ у момент створення, а CI ще жодного разу не запускався. Далі всі образи кладе CI з тегом = SHA коміту.

> Після `terraform destroy` реєстр видаляється разом з образами, тож після нового `apply` сервіси не стартують (`CannotPullContainerError … not found`), доки в реєстрі немає образу. Замість ручного `bootstrap` можна одразу запустити CI: GitHub → **Actions → Lab 1-2 - Deploy to AWS ECS → Run workflow** — він збере образ з тегом SHA і задеплоїть обидва сервіси.

### 3. GitHub (CI/CD)

GitHub → **Settings → Secrets and variables → Actions → Variables**: `AWS_ROLE_ARN` = `terraform output -raw github_deploy_role_arn` (ім'я ролі не змінюється, тож після повторного `apply` значення те саме).

Push у `main` зі зміною коду в `Lab1/` → збірка → ECR з тегом SHA → нові ревізії task definition для `app` і `worker` → деплой. Зміни лише в `terraform/`, `docs/`, `loadtest/`, `tests/`, `README.md` деплой не запускають. Після зміни змінних середовища в Terraform запустити вручну: **Actions → Lab 1-2 - Deploy to AWS ECS → Run workflow**.

### 4. Перевірка Лаби 1

```powershell
cd D:\univer\Cloud_Technologies\Lab1\terraform
$URL = terraform output -raw app_url
```

**1 — контейнер:** `docker compose exec app whoami` → `appuser`; `Select-String -Path ..\Dockerfile -Pattern "FROM"` → фіксована версія; `docker compose down; docker compose up -d` → дані на місці (volume `lab1_pgdata`).

**2 — Terraform і БД:**
```powershell
terraform state list
Invoke-RestMethod "$URL/health"
Invoke-RestMethod "$URL/notes"
aws ecs describe-task-definition --task-definition cloudlab1-app --query "taskDefinition.containerDefinitions[0].secrets"
```

**3 — ізоляція БД:**
```powershell
aws rds describe-db-instances --db-instance-identifier cloudlab1-db --query "DBInstances[0].PubliclyAccessible"
aws ec2 describe-security-groups --filters Name=group-name,Values=cloudlab1-db-sg --query "SecurityGroups[0].IpPermissions"
```
`false`; порт 5432 лише від SG застосунку і обробника, `IpRanges` порожній.

**4 — балансувальник:**
```powershell
$TG = aws elbv2 describe-target-groups --names cloudlab1-tg --query "TargetGroups[0].TargetGroupArn" --output text
aws elbv2 describe-target-health --target-group-arn $TG --query "TargetHealthDescriptions[].TargetHealth.State"
```

**5 — CI/CD:** змінити текст у `root()` в `app\main.py` → `git add -A; git commit -m "demo"; git push` → Actions зелені → `Invoke-RestMethod "$URL/"` показує `version` = `git log -1 --format=%H`.

**Б6 — JWT:**
```powershell
try { Invoke-RestMethod -Method Post -Uri "$URL/notes" -ContentType "application/json" -Body '{"title":"x"}' } catch { $_.Exception.Response.StatusCode.value__ }
Invoke-RestMethod -Method Post -Uri "$URL/auth/register" -ContentType "application/json" -Body '{"username":"demo","password":"demopass123"}'
$TOKEN = (Invoke-RestMethod -Method Post -Uri "$URL/auth/login" -ContentType "application/json" -Body '{"username":"demo","password":"demopass123"}').access_token
Invoke-RestMethod -Method Post -Uri "$URL/notes" -ContentType "application/json" -Headers @{Authorization="Bearer $TOKEN"} -Body '{"title":"with token"}'
```

**Б7 — моніторинг:** `1..10 | ForEach-Object { try { Invoke-WebRequest "$URL/debug/error" -UseBasicParsing } catch {} }` → за 3–6 хв лист `ALARM: cloudlab1-app-5xx`.

### 5. Перевірка Лаби 2

Усе з папки `D:\univer\Cloud_Technologies\Lab1`. Перед кожним тестом відкрити панель (`terraform -chdir=terraform output -raw dashboard_url`), період **1 хв**, автооновлення **10 с**.

**1 — політика масштабування:**
```powershell
aws application-autoscaling describe-scalable-targets --service-namespace ecs --query "ScalableTargets[].[ResourceId,MinCapacity,MaxCapacity]" --output table
aws application-autoscaling describe-scaling-policies --service-namespace ecs --query "ScalingPolicies[].[PolicyName,PolicyType]" --output table
```

**2, 3, 4 — один прогін на 10 хвилин:**
```powershell
.\loadtest\run.ps1 -Label calibrate -RampUp 30s -Steady 1m -RampDown 30s   # пробний: чи CPU на сталій фазі > 70 %
.\loadtest\run.ps1 -Label baseline                                         # основний (за потреби -Vus 90)
```
На панелі: росте «Запити за хвилину» → CPU перетинає 60 % → спершу «бажана», потім «фактична» кількість екземплярів росте → CPU > 70 % 2 хв → лист **ALARM** → після спаду лист **OK** → через ~15–20 хв екземплярів знову 1:
```powershell
aws ecs describe-services --cluster cloudlab1-cluster --services cloudlab1-service --query "services[0].[desiredCount,runningCount]"
```

**5 — кеш з і без:**
```powershell
.\loadtest\admin.ps1 cache-off; .\loadtest\admin.ps1 reset-stats
.\loadtest\run.ps1 -Label no-cache; .\loadtest\admin.ps1 stats
.\loadtest\admin.ps1 cache-on;  .\loadtest\admin.ps1 reset-stats
.\loadtest\run.ps1 -Label with-cache; .\loadtest\admin.ps1 stats
```
Між прогонами дочекатися 1 екземпляра.

**Б6 — черга:** `.\loadtest\run.ps1 -Label async -Mode async` → на панелі росте «повідомлень у черзі», обробників 1 → 4, p95 не росте.

**Б7 — ідемпотентність:** `.\tests\run.ps1` → `4 passed`.

**Б8 — розклад:** [`docs/SCHEDULE.md`](docs/SCHEDULE.md), `terraform apply -var="enable_schedule=true"` (для демонстрації — з тестовим часом, команда в цьому файлі).

Звіти k6 зберігаються в `loadtest\results\<Label>.md`; числа з них переносяться в `docs/`.

### 6. Видалення (обов'язково після роботи)

```powershell
cd D:\univer\Cloud_Technologies\Lab1\terraform
terraform destroy
terraform state list                 # порожньо
cd ..; docker compose down
```

Вартість, поки стек піднятий: ~$2–3 на добу (3+ задачі Fargate: застосунок, обробник, Redis; ALB, RDS, Container Insights). Під час тестів до 4 + 4 задач. Бюджет `cloudlab1-monthly` надішле лист при 50 % від $10.

## Примітки щодо рішень

- **Секрети.** Пароль БД генерує RDS (Secrets Manager); ключ JWT, адмін-токен і пароль Redis генерує Terraform-джерело `aws_secretsmanager_random_password` прямо в Secrets Manager. У контейнери вони потрапляють через `secrets` у task definition. У репозиторії й образі секретів немає; state і `.env` — у `.gitignore`.
- **Мережа.** Задачі Fargate у публічних підмережах з публічною IP лише для вихідного трафіку (ECR, CloudWatch, SQS) без платного NAT Gateway. Вхід: застосунок — лише від балансувальника, Redis — лише від застосунку й обробника, БД — так само.
- **Redis як контейнер, а не ElastiCache:** ~$0.30/добу замість ~$12–16/міс., і видаляється разом зі стеком.
- **Масштабування і CI не конфліктують:** `ignore_changes = [task_definition, desired_count]` — версією керує CI, кількістю — Application Auto Scaling.
- **Коректне завершення:** deregistration delay 15 с → SIGTERM → uvicorn дообробляє запити до 20 с → `stopTimeout` 30 с. Обробник черги доробляє поточну пачку повідомлень.
- **Економія:** `db.t4g.micro`, Single-AZ, без бекапів; у продакшні — Multi-AZ і `backup_retention_period >= 7`.
