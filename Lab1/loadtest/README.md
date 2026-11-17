# Навантажувальний тест (k6)

Сценарій `notes.js`: «мало записів, багато читань» (1 `POST /notes` + 9 читань у циклі), фази 3 хв наростання → 5 хв стало → 2 хв спад. k6 працює в Docker (`grafana/k6:1.6.1`), встановлювати не треба, достатньо запущеного Docker Desktop.

Усі команди — з папки `D:\univer\Cloud_Technologies\Lab1`.

| Що | Команда |
|---|---|
| Основний прогін проти хмари | `.\loadtest\run.ps1 -Label baseline` |
| Інша кількість користувачів | `.\loadtest\run.ps1 -Label baseline -Vus 90` |
| Пробний 2-хвилинний прогін | `.\loadtest\run.ps1 -Label calibrate -RampUp 30s -Steady 1m -RampDown 30s` |
| Запис через чергу (бонус 6) | `.\loadtest\run.ps1 -Label async -Mode async` |
| Проти локального `docker compose` | `.\loadtest\run.ps1 -Label local -Local -Vus 10 -RampUp 20s -Steady 40s -RampDown 20s` |

Звіт (запити, помилки, p50/p95/p99, частка влучань у кеш) друкується в кінці і зберігається в `results/<Label>.md`.

Адмін-команди для порівняння з кешем і без (`admin.ps1`, токен береться з Secrets Manager):

| Команда | Що робить |
|---|---|
| `.\loadtest\admin.ps1 cache-off` / `cache-on` | вимкнути / ввімкнути кеш на всіх екземплярах (≤5 с) |
| `.\loadtest\admin.ps1 cache-status` | поточний стан |
| `.\loadtest\admin.ps1 stats` | лічильники: влучання, промахи, запити до БД, % влучань |
| `.\loadtest\admin.ps1 reset-stats` | обнулити лічильники перед прогоном |

Для локального compose додати `-Local`.
