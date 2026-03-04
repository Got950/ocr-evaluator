# Contributing to OCR Evaluator

Thank you for your interest in contributing! This guide covers local setup, testing, and how to add new features.

## Local Development Setup (without Docker)

### 1. Clone and create virtualenv
```bash
git clone https://github.com/youruser/ocr_evaluator.git
cd ocr_evaluator
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
.venv\Scripts\activate      # Windows
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt   # linting + formatting tools
```

### 3. Set up PostgreSQL
You need a local PostgreSQL instance. Create a database:
```sql
CREATE DATABASE ocr_evaluator;
```

### 4. Configure environment
```bash
cp .env.example .env
# Edit .env: set DATABASE_URL to your local postgres connection string
# Set SECRET_KEY to any random 32+ character string for local dev
```

### 5. Run database migrations
```bash
alembic upgrade head
```

### 6. Start the server
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Open http://127.0.0.1:8001/docs for the interactive API docs.

---

## Running Tests

### Integration tests (requires running server)
```bash
pip install reportlab requests
python tests/test_all_features.py
```

### Standalone engine tests (no server needed)
```bash
python scripts/test_numerical_engine.py
python scripts/test_symbolic_engine.py
python scripts/test_hybrid_engine.py
```

### pytest
```bash
pytest tests/ -v --tb=short
```

---

## How to Add a New Grading Engine

OCR Evaluator uses a modular engine architecture. Each `subject_type` routes to a dedicated engine.

### 1. Create the engine service

Create `app/services/my_engine.py`:

```python
from typing import Any

def evaluate_my_type(question: Any, answer_text: str) -> dict:
    # Your grading logic here
    score = 0.0
    feedback = "..."
    return {
        "score": float(score),
        "feedback": feedback,
        "evaluation_details": {
            # engine-specific details
        },
    }
```

**Rules:**
- Accept `question` (SQLAlchemy model) and `answer_text` (str)
- Return a dict with `score`, `feedback`, and `evaluation_details`
- Wrap everything in try/except — never let the engine crash the worker
- Access `question.max_marks`, `question.answer_key`, etc. via `getattr()` for safety

### 2. Register in the engine router

Edit `app/services/engine_router.py`:

```python
from app.services.my_engine import evaluate_my_type

# Add to route_engine() before the descriptive fallback:
if subject_type == "my_type":
    return evaluate_my_type(question, answer_text)
```

### 3. Add the subject_type to the model

Edit `app/models/database.py` — add to `SubjectType` enum:
```python
class SubjectType(str, enum.Enum):
    ...
    my_type = "my_type"
```

Also add `"my_type"` to `_ALLOWED_SUBJECT_TYPES` in `engine_router.py`.

### 4. Update schemas if needed

If your engine needs new fields on `Question` (like `correct_numeric_answer` does for numerical), add them to:
- `app/models/database.py` (SQLAlchemy column)
- `app/models/schemas.py` (Pydantic fields on `CreateQuestionRequest` / `CreateQuestionResponse`)
- Generate an Alembic migration: `alembic revision --autogenerate -m "add_my_type_fields"`

### 5. Add a test script

Create `scripts/test_my_engine.py` following the pattern in `scripts/test_numerical_engine.py`.

---

## Pull Request Guidelines

- **One feature per PR** — keep changes focused and reviewable
- **Tests required** — add or update tests for any behavior change
- **Describe what changed** — include a clear summary in the PR description
- **Don't break existing engines** — grading engine logic is critical path; don't modify engines you're not specifically improving
- **Run the full test suite** before submitting: `python tests/test_all_features.py`

---

## Code Style

We use **black** for formatting and **isort** for import ordering:

```bash
pip install -r requirements-dev.txt
black app/ tests/ scripts/
isort app/ tests/ scripts/
```

Configuration is in `pyproject.toml` (if present) or uses defaults.

---

## Reporting Bugs

Open a GitHub Issue with:
1. **What you expected** to happen
2. **What actually happened** (include error messages, status codes)
3. **Steps to reproduce** (API calls, PDF samples if relevant)
4. **Environment** (OS, Python version, GPU/CPU, Docker or local)

For security vulnerabilities, please email [author] directly instead of opening a public issue.
