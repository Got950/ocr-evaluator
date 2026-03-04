# OCR Evaluator - Setup

## Prerequisites
- Python 3.8+
- PostgreSQL (local or cloud)
- Redis (optional — enables Celery task queue; without it, grading runs in-process)
- Poppler (for PDF support)

## 1. Install dependencies
```bash
py -m pip install -r requirements.txt
```

## 2. Database

### Option A: Neon (no install)
1. Sign up at https://neon.tech (free)
2. Create project → Connect → copy connection string
3. In `.env` set:
```
DATABASE_URL=postgresql+asyncpg://user:pass@ep-xxx.neon.tech/dbname?sslmode=require
```

### Option B: Local PostgreSQL
1. `winget install PostgreSQL.PostgreSQL.16`
2. Complete installer (set postgres password)
3. Start service: Services → postgresql-x64-16 → Start
4. In `.env` set:
```
DATABASE_URL=postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/ocr_evaluator
```

## 3. Database migrations (Alembic)
```bash
py -m alembic upgrade head
```
In dev mode (`ENVIRONMENT=dev`), the server auto-runs migrations on startup.
For production, always run migrations as a separate step before deploying.

## 4. Poppler (for PDF support)
Required for PDF uploads (question papers and answer booklets):
```bash
winget install poppler
```
Restart your terminal after install.

## 5. Redis (optional, for Celery)
```bash
# Docker
docker run -d --name redis -p 6379:6379 redis:7-alpine
```
Set in `.env`:
```
REDIS_URL=redis://localhost:6379/0
```

## 6. S3/MinIO (optional, for cloud file storage)
Without S3, uploads go to local `uploads/` directory.
```bash
docker run -d --name minio -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \
  minio/minio server /data --console-address ":9001"
```
Set in `.env`:
```
S3_BUCKET=ocr-evaluator-uploads
S3_ENDPOINT_URL=http://localhost:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
```

## 7. Environment variables
Copy `.env.example` to `.env` and fill in your values:
```bash
cp .env.example .env
```
Key variables:
- `DATABASE_URL` — PostgreSQL connection string
- `SECRET_KEY` — JWT signing key (min 32 chars)
- `REDIS_URL` — Redis for Celery (optional)
- `S3_BUCKET` — S3/MinIO bucket (optional)
- `AI_GRADING_ENABLED` — set to `false` for safe/manual-review mode

## 8. Run the server
```bash
py -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```
Or use Docker Compose:
```bash
docker compose up --build
```

## 9. Create first admin user
```bash
py -c "
import requests
r = requests.post('http://127.0.0.1:8001/api/v1/auth/register', json={
    'email': 'admin@example.com',
    'password': 'adminpassword',
    'role': 'admin',
    'institution_name': 'My University'
})
print(r.json())
"
```

## 10. API docs
- Swagger UI: http://127.0.0.1:8001/docs
- ReDoc: http://127.0.0.1:8001/redoc

## 11. Monitoring
- Health: `GET /health`
- Flower (Celery monitoring): http://localhost:5555 (when using Docker Compose)
- MinIO console: http://localhost:9001

## 12. Run tests
```bash
py -m pip install reportlab requests pytest -q
py tests/test_all_features.py
```

## Services in docker-compose
| Service | Port | Purpose |
|---------|------|---------|
| app | 8000 | FastAPI server |
| db | 5432 | PostgreSQL |
| redis | 6379 | Celery broker/backend |
| minio | 9000/9001 | S3-compatible object storage |
| celery_worker | — | Background grading tasks |
| flower | 5555 | Celery monitoring UI |
