# OCR Evaluator

An AI-powered exam answer grading platform that uses OCR to read handwritten student answer booklets and automatically evaluates them using multiple grading engines. Professors upload question papers, students submit answer PDFs, and the system grades each answer using text similarity, numerical tolerance, symbolic algebra equivalence, or weighted hybrid scoring.

## Features

- **Handwriting OCR** — TrOCR (microsoft/trocr-base-handwritten) with Poppler fallback for typed PDFs
- **Multi-engine grading** — descriptive (easy/medium/hard), numerical, symbolic (SymPy), and hybrid weighted
- **Question paper analysis** — upload a PDF, auto-extract questions via OCR + regex parsing
- **Booklet segmentation** — splits multi-page answer booklets into per-question text
- **Manual override** — professors can override any per-question score after auto-grading
- **Safe mode** — disable AI grading (`AI_GRADING_ENABLED=false`) to queue submissions for manual review
- **JWT authentication** — role-based access (professor, student, admin) with institution scoping
- **S3/MinIO storage** — optional cloud file storage with local-disk fallback
- **Celery task queue** — async grading via Redis + Celery with automatic retry, or in-process fallback
- **Production middleware** — rate limiting, security headers, gzip, request IDs, structured JSON logging
- **Database migrations** — Alembic for schema management
- **Health monitoring** — `/health` endpoint reporting DB, GPU, model load, and grading status

## Architecture

```
                         ┌─────────────┐
                         │   Frontend   │
                         │  (static UI) │
                         └──────┬───────┘
                                │
                         ┌──────▼───────┐
                         │   FastAPI    │
                         │  (async)     │
                         └──┬───┬───┬───┘
                            │   │   │
               ┌────────────┘   │   └────────────┐
               │                │                │
        ┌──────▼──────┐ ┌──────▼──────┐  ┌──────▼──────┐
        │  PostgreSQL  │ │    Redis    │  │ MinIO / S3  │
        │  (data)      │ │  (broker)   │  │ (files)     │
        └──────────────┘ └──────┬──────┘  └─────────────┘
                                │
                         ┌──────▼──────┐
                         │   Celery    │
                         │  Worker(s)  │
                         │  OCR + AI   │
                         └─────────────┘
```

## Quick Start

```bash
git clone https://github.com/youruser/ocr_evaluator.git
cd ocr_evaluator
cp .env.example .env        # edit DATABASE_URL, SECRET_KEY at minimum
docker compose up --build    # starts postgres, redis, minio, app, celery, flower
docker compose exec app alembic upgrade head   # run migrations
```

Open http://localhost:8000/docs for the Swagger UI.

Create an admin user:
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"adminpass","role":"admin","institution_name":"My University"}'
```

## Prerequisites

- **Docker + Docker Compose** (recommended) — or Python 3.8+, PostgreSQL 15+, Redis 7+
- **8 GB RAM** minimum (TrOCR model is ~1.2 GB)
- **GPU** optional but recommended for faster OCR (CUDA-compatible NVIDIA GPU)
- **Poppler** — required for PDF-to-image conversion (`apt install poppler-utils` / `winget install poppler`)

## Configuration

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | *(required)* | PostgreSQL connection string |
| `SECRET_KEY` | `change-me...` | JWT signing key (min 32 chars) |
| `ENVIRONMENT` | `dev` | `dev` auto-runs migrations on startup |
| `LOG_LEVEL` | `INFO` | Structured log level |
| `AI_GRADING_ENABLED` | `true` | Set `false` for manual-review-only mode |
| `MAX_CONCURRENT_EVALUATIONS` | `4` | Parallel OCR/grading task limit |
| `ENABLE_RATE_LIMITING` | `true` | Per-IP submission rate limiting |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker (optional) |
| `S3_BUCKET` | *(empty)* | S3/MinIO bucket name (optional) |
| `S3_ENDPOINT_URL` | *(empty)* | MinIO endpoint (omit for AWS S3) |
| `AWS_ACCESS_KEY_ID` | *(empty)* | S3 credentials |
| `AWS_SECRET_ACCESS_KEY` | *(empty)* | S3 credentials |
| `S3_REGION` | `us-east-1` | S3 region |
| `UPLOAD_DIR` | `uploads` | Local file storage path |
| `MAX_UPLOAD_SIZE_BYTES` | `8388608` | Max upload size (8 MB) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT token lifetime |
| `TRUSTED_HOSTS` | `*` | Allowed hosts for TrustedHostMiddleware |
| `CORS_ORIGINS` | *(empty)* | Comma-separated CORS origins |
| `ENABLE_SECURITY_HEADERS` | `true` | Security response headers |
| `GZIP_MINIMUM_SIZE` | `1000` | Min bytes for gzip compression |

## Running Tests

```bash
# Install test dependencies
pip install reportlab requests pytest

# Run the integration test suite (requires running server on port 8001)
py -m uvicorn app.main:app --host 127.0.0.1 --port 8001 &
py tests/test_all_features.py

# Run with pytest
py -m pytest tests/ -v --tb=short

# Run individual engine tests (standalone, no server needed)
py scripts/test_numerical_engine.py
py scripts/test_symbolic_engine.py
py scripts/test_hybrid_engine.py
```

## Project Structure

```
ocr_evaluator/
├── app/
│   ├── main.py                      # FastAPI app, middleware, startup
│   ├── config.py                    # Pydantic settings from env
│   ├── worker.py                    # Celery app configuration
│   ├── dependencies.py              # Auth dependencies (JWT, role guards)
│   ├── api/
│   │   ├── routes_auth.py           # Register, login, me endpoints
│   │   ├── routes_professor.py      # Question paper upload, question CRUD
│   │   ├── routes_student.py        # Answer booklet submission
│   │   └── routes_evaluation.py     # Grading, submission retrieval, override
│   ├── models/
│   │   ├── database.py              # SQLAlchemy models + engine setup
│   │   └── schemas.py               # Pydantic request/response schemas
│   ├── services/
│   │   ├── ocr_service.py           # TrOCR + Poppler OCR
│   │   ├── embedding_service.py     # Sentence-transformer embeddings
│   │   ├── segmentation_service.py  # Answer booklet text segmentation
│   │   ├── question_paper_parser.py # Question extraction from OCR text
│   │   ├── engine_router.py         # Routes to correct grading engine
│   │   ├── evaluation_easy.py       # Cosine similarity grading
│   │   ├── evaluation_medium.py     # Concept matching grading
│   │   ├── evaluation_hard.py       # Rubric-based grading
│   │   ├── numerical_engine.py      # Tolerance-based numeric grading
│   │   ├── symbolic_engine.py       # SymPy algebraic equivalence
│   │   ├── hybrid_engine.py         # Weighted numerical + descriptive
│   │   ├── auth_service.py          # Password hashing + JWT
│   │   └── storage_service.py       # S3/MinIO file operations
│   ├── tasks/
│   │   └── grading_tasks.py         # Celery grading task with retry
│   └── utils/
│       └── text_cleaning.py         # Text normalization
├── alembic/                         # Database migrations
├── frontend/                        # Static web UI
├── tests/                           # Integration tests
├── scripts/                         # Dev/test helper scripts
├── docker-compose.yml               # Full stack (postgres, redis, minio, app, celery, flower)
├── Dockerfile
├── requirements.txt
├── .env.example
├── SETUP.md                         # Detailed setup instructions
├── CONTRIBUTING.md                  # Contribution guidelines
└── LICENSE                          # MIT
```

## Grading Engines

| Engine | `subject_type` | How it works |
|---|---|---|
| **Easy** | `descriptive` | Cosine similarity between student answer and answer key embeddings |
| **Medium** | `descriptive` | Concept matching — checks presence of key concepts using embeddings |
| **Hard** | `descriptive` | Rubric-based evaluation (accuracy, completeness, depth, clarity) |
| **Numerical** | `numerical` | Extracts numeric values, checks tolerance, optional unit matching with partial credit |
| **Symbolic** | `symbolic` | Parses mathematical expressions with SymPy, checks algebraic equivalence via `simplify(a - b) == 0` |
| **Hybrid** | `mixed` | Weighted combination of numerical + descriptive, configurable per-question weights |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and how to add new grading engines.

## License

[MIT](LICENSE)
