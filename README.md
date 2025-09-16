📊 Analytics Portal — Excel → PostgreSQL → ECharts

Интерактивный дашборд: импорт Excel → нормализация данных в PostgreSQL (JSONB) → быстрые агрегаты через DRF → визуализации на Apache ECharts (в теме Sneat).

⚙️ Стек (кратко)

| Слой            | Технологии                                                                                                                                  |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **Backend**     | **Python 3.10**, **Django 5.2.5**, **Django REST Framework 3.16**, `django-allauth` (Session + JWT)                                         |
| **Frontend**    | **Apache ECharts (CDN)**, **Sneat** (Bootstrap-верстка + шаблоны), ванильный JS (fetch)                                                     |
| **Кэш**         | Встроенный кэш Django (готов к **Redis** через `django-redis`, опционально)                                                                 |
| **База данных** | **PostgreSQL** (`psycopg2-binary`), JSONB-хранилище для строк набора данных, индексы **GIN** + функциональные (по популярным ключам и дате) |

Как запустить локально
1) Зависимости
python -m venv venv
# Windows PowerShell:
.\venv\Scripts\Activate.ps1
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt

# 2) База данных (PostgreSQL)

Создайте БД и пользователя (пример):
CREATE DATABASE analytics;
CREATE USER postgres WITH ENCRYPTED PASSWORD 'postgres';
GRANT ALL PRIVILEGES ON DATABASE analytics TO postgres;

# 3) .env (в корне проекта)

DJANGO_ENVIRONMENT=local
DEBUG=True
SECRET_KEY=dev-secret

ALLOWED_HOSTS=127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000

DB_ENGINE=django.db.backends.postgresql
DB_NAME=analytics
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=127.0.0.1
DB_PORT=5432

BASE_URL=http://127.0.0.1:8000
PUBLIC_BASE_URL=http://127.0.0.1:8000

💡 Кэш через Redis — опционально. В settings.py уже есть пример конфигурации django-redis (раскомментируйте при необходимости и поднимите redis).

# 4) Миграции, суперпользователь, статика

python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput

# 5) Запуск

python manage.py runserver

Дашборд: http://127.0.0.1:8000/ (после логина)
Админка: http://127.0.0.1:8000/admin/

# 6) Импорт Excel (по листу)

Посмотреть названия листов:

python -c "from openpyxl import load_workbook; wb=load_workbook('14_list_report.xlsx',read_only=True,data_only=True); print('\n'.join(wb.sheetnames))"

Импорт конкретного листа:

python manage.py import_excel "14_list_report.xlsx" --sheet "33 37 ойлик кумак экс" --bulk-size 5000 --verbosity 2

# Как работает сайт

Импорт Excel: management-команда парсит лист, приводит значения к JSON-safe виду (числа → float, дата → YYYY-MM-DD), пишет:

«сырые» ячейки для аудита;

нормализованные строки (DatasetRow.data в JSONB).

БД (PostgreSQL): ускорение выборок за счёт GIN по JSONB и функциональных индексов (по ключам и датам).

API (DRF): универсальный /api/aggregate/ с group_by и metric (sum/avg/min/max/count:<field>), поддержка filters[...] и exclude[...].

Frontend (ECharts + Sneat):

6 графиков (bar/line/stack/pie/dataset-encode) с фильтрами и подсказками.

Порядок регионов берётся как в таблице (по колонке №), либо задаётся кастомным списком.

Для «pie» — дополнительная KPI-карточка (итог, TOP-1, TOP-3).

Аутентификация: вход через django-allauth (Google/Nextcloud), Session + JWT; доступ к дашборду и API — только для авторизованных пользователей.

Итог: грузите Excel → данные попадают в PostgreSQL (JSONB) → запрашиваете агрегаты через API → ECharts строит интерактивные графики прямо в браузере.
