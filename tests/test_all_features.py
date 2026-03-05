"""
Full integration test: exercises every API endpoint with real requests.
Uses sample PDFs and reports actual pass/fail. No simulation.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:8001"
API_BASE = f"{BASE_URL}/api/v1"
TIMEOUT = 120  # OCR can be slow
POLL_INTERVAL = 2
POLL_MAX = 90  # max 90 * 2 = 180s wait for evaluation

try:
    import pytest  # type: ignore
except Exception:  # pragma: no cover
    pytest = None


if pytest is not None:

    @pytest.fixture(scope="session")
    def question_id() -> str:
        test_server_reachable()
        return str(test_professor_create_three_questions_for_booklet())

    @pytest.fixture(scope="session")
    def submission_id(question_id: str) -> str:
        sid = str(test_student_submit_answer(question_id))
        wait_for_completed(sid)
        return sid


def create_sample_question_paper_pdf(path: Path) -> None:
    """Create a PDF that OCR can read (question paper) - large font for TrOCR."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError:
        raise RuntimeError("reportlab required for tests: pip install reportlab")

    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica", 28)  # larger for TrOCR
    y = 800
    c.drawString(72, y, "1. Define photosynthesis. (5 marks)")
    y -= 50
    c.drawString(72, y, "2. What is the chemical formula of water? (3 marks)")
    y -= 50
    c.drawString(72, y, "3. Explain Newton first law. (7 marks)")
    c.save()


def create_sample_answer_booklet_pdf(path: Path) -> None:
    """Create a PDF simulating student answers - large font for TrOCR."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError:
        raise RuntimeError("reportlab required for tests: pip install reportlab")

    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica", 24)  # larger for TrOCR
    y = 800
    c.drawString(72, y, "1. Photosynthesis is the process by which plants make")
    y -= 40
    c.drawString(72, y, "food using light.")
    y -= 50
    c.drawString(72, y, "2. The formula is H2O.")
    y -= 50
    c.drawString(72, y, "3. Newton first law says an object at rest stays at rest.")
    c.save()


def run(name: str, fn):
    try:
        fn()
        print(f"[PASS] {name}")
        return True
    except AssertionError as e:
        print(f"[FAIL] {name}: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] {name}: {e}")
        return False


_auth_headers_cache: dict | None = None


def _get_auth_headers() -> dict:
    """Register and login as admin, return headers with Bearer token."""
    global _auth_headers_cache
    if _auth_headers_cache is not None:
        return _auth_headers_cache
    try:
        requests.post(
            f"{API_BASE}/auth/register",
            json={
                "email": "ci_test_admin@test.com",
                "password": "testpass123",
                "role": "admin",
                "institution_name": "CI Test",
            },
            timeout=10,
        )
    except Exception:
        pass  # May already exist
    r = requests.post(
        f"{API_BASE}/auth/login",
        data={"username": "ci_test_admin@test.com", "password": "testpass123"},
        timeout=10,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    token = r.json()["access_token"]
    _auth_headers_cache = {"Authorization": f"Bearer {token}"}
    return _auth_headers_cache


def test_server_reachable():
    r = requests.get(f"{BASE_URL}/openapi.json", timeout=5)
    assert r.status_code == 200, f"Server not reachable: {r.status_code}"
    data = r.json()
    assert "paths" in data


def test_professor_create_question():
    """Create a single question; returns its ID for student submission."""
    payload = {
        "question_text": "What is 2+2?",
        "answer_key": "4",
        "max_marks": 5,
        "evaluation_level": "easy",
    }
    r = requests.post(f"{API_BASE}/professor/create-question", json=payload, headers=_get_auth_headers(), timeout=TIMEOUT)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("status") == "success"
    assert "question_id" in data
    uuid.UUID(str(data["question_id"]))
    return data["question_id"]


def test_professor_create_three_questions_for_booklet():
    """Create exactly 3 questions so booklet (Q1,Q2,Q3) maps correctly."""
    payload = {
        "items": [
            {"question_text": "Define photosynthesis.", "answer_key": "Process by which plants make food using light", "max_marks": 5, "evaluation_level": "easy"},
            {"question_text": "What is the chemical formula of water?", "answer_key": "H2O", "max_marks": 3, "evaluation_level": "easy"},
            {"question_text": "Explain Newton's first law.", "answer_key": "Object at rest stays at rest", "max_marks": 7, "evaluation_level": "easy"},
        ]
    }
    r = requests.post(f"{API_BASE}/professor/create-questions-batch", json=payload, headers=_get_auth_headers(), timeout=TIMEOUT)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("status") == "success"
    ids = data["question_ids"]
    assert len(ids) == 3
    return ids[0]  # return first for submit-answer


def test_professor_analyze_question_paper():
    script_dir = Path(__file__).resolve().parent
    pdf_path = script_dir / "sample_question_paper.pdf"
    create_sample_question_paper_pdf(pdf_path)
    assert pdf_path.exists()

    with open(pdf_path, "rb") as f:
        files = {"file": ("question_paper.pdf", f, "application/pdf")}
        r = requests.post(
            f"{API_BASE}/professor/analyze-question-paper",
            files=files,
            headers=_get_auth_headers(),
            timeout=TIMEOUT,
        )
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("status") == "success"
    assert "extracted_text" in data
    assert "questions" in data
    assert len(data["questions"]) >= 1, f"Expected at least 1 question, got {data['questions']}"
    return data


def test_professor_create_questions_batch():
    payload = {
        "items": [
            {
                "question_text": "Batch Q1: Capital of France?",
                "answer_key": "Paris",
                "max_marks": 2,
                "evaluation_level": "easy",
            },
            {
                "question_text": "Batch Q2: 3+3?",
                "answer_key": "6",
                "max_marks": 2,
                "evaluation_level": "easy",
            },
        ]
    }
    r = requests.post(f"{API_BASE}/professor/create-questions-batch", json=payload, headers=_get_auth_headers(), timeout=TIMEOUT)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("status") == "success"
    assert "question_ids" in data
    assert len(data["question_ids"]) == 2
    return data["question_ids"]


def test_student_submit_answer(question_id: str):
    script_dir = Path(__file__).resolve().parent
    pdf_path = script_dir / "sample_answer_booklet.pdf"
    create_sample_answer_booklet_pdf(pdf_path)
    assert pdf_path.exists()

    with open(pdf_path, "rb") as f:
        files = {"file": ("answer_booklet.pdf", f, "application/pdf")}
        data_form = {"question_id": question_id}
        r = requests.post(
            f"{API_BASE}/student/submit-answer",
            files=files,
            data=data_form,
            headers=_get_auth_headers(),
            timeout=TIMEOUT,
        )
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    resp = r.json()
    assert resp.get("status") == "success"
    assert "submission_id" in resp
    return resp["submission_id"]


def test_evaluate_submission(submission_id: str):
    r = requests.post(f"{API_BASE}/evaluate/{submission_id}", headers=_get_auth_headers(), timeout=TIMEOUT)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    return r.json()


def wait_for_completed(submission_id: str) -> dict:
    for _ in range(POLL_MAX):
        r = requests.get(f"{API_BASE}/submission/{submission_id}", headers=_get_auth_headers(), timeout=TIMEOUT)
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
        data = r.json()
        status = data.get("submission_status", "")
        if status == "completed":
            return data
        if status == "failed":
            raise AssertionError(f"Submission failed: {data.get('feedback', data)}")
        time.sleep(POLL_INTERVAL)
    raise AssertionError("Evaluation did not complete in time")


def test_get_submission(submission_id: str):
    r = requests.get(f"{API_BASE}/submission/{submission_id}", headers=_get_auth_headers(), timeout=TIMEOUT)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    data = r.json()
    assert "submission_id" in data
    assert "extracted_text" in data
    assert "per_question_scores" in data or "score" in data
    return data


def test_override_submission(submission_id: str):
    payload = {"1": 4.0, "2": 2.0}
    r = requests.post(
        f"{API_BASE}/submission/{submission_id}/override",
        json=payload,
        headers=_get_auth_headers(),
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("status") == "success"
    assert data.get("final_score") == 6.0
    return data


def test_override_persisted(submission_id: str):
    r = requests.get(f"{API_BASE}/submission/{submission_id}", headers=_get_auth_headers(), timeout=TIMEOUT)
    assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
    data = r.json()
    assert float(data.get("final_score", 0)) == 6.0


def main():
    print("=" * 60)
    print("OCR Evaluator - Full Feature Test (real execution)")
    print("=" * 60)

    passed = 0
    total = 0

    # 1. Server reachable
    total += 1
    if run("Server reachable", test_server_reachable):
        passed += 1
    else:
        print("Aborting: server must be running at", BASE_URL)
        return

    # 2. Professor: create 3 questions for booklet (must be first so eval maps Q1,Q2,Q3)
    total += 1
    question_id = None
    try:
        question_id = str(test_professor_create_three_questions_for_booklet())
        passed += 1
        print("[PASS] Professor create-questions-batch (3 for booklet)")
    except Exception as e:
        print(f"[FAIL] Professor create-questions-batch (booklet): {e}")

    # 3. Professor: create single question
    total += 1
    try:
        test_professor_create_question()
        passed += 1
        print("[PASS] Professor create-question")
    except Exception as e:
        print(f"[FAIL] Professor create-question: {e}")

    # 4. Professor: analyze question paper
    total += 1
    if run("Professor analyze-question-paper", test_professor_analyze_question_paper):
        passed += 1

    # 5. Professor: create questions batch (2 more)
    total += 1
    if run("Professor create-questions-batch", test_professor_create_questions_batch):
        passed += 1

    # 6. Student submit (question_id from step 2 - first of 3 booklet questions)
    total += 1
    submission_id = None
    try:
        submission_id = test_student_submit_answer(str(question_id))
        passed += 1
        print("[PASS] Student submit-answer")
    except Exception as e:
        print(f"[FAIL] Student submit-answer: {e}")

    # 7. Wait for evaluation to complete
    if submission_id:
        total += 1
        try:
            result = wait_for_completed(submission_id)
            passed += 1
            print(f"[PASS] Evaluation completed (score={result.get('final_score', result.get('score'))})")
        except Exception as e:
            print(f"[FAIL] Evaluation completion: {e}")

    # 8. GET submission
    if submission_id:
        total += 1
        if run("GET submission", lambda: test_get_submission(submission_id)):
            passed += 1

    # 9. Manual override
    if submission_id:
        total += 1
        if run("Manual override", lambda: test_override_submission(submission_id)):
            passed += 1

    # 10. Verify override persisted
    if submission_id:
        total += 1
        try:
            r = requests.get(f"{API_BASE}/submission/{submission_id}", headers=_get_auth_headers(), timeout=TIMEOUT)
            assert r.status_code == 200
            data = r.json()
            assert float(data.get("final_score", 0)) == 6.0
            passed += 1
            print("[PASS] Override persisted in GET submission")
        except Exception as e:
            print(f"[FAIL] Override persistence: {e}")

    print("=" * 60)
    print(f"Result: {passed}/{total} tests passed")
    print("=" * 60)
    exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
