Sample PDFs for OCR Evaluator Testing
======================================

1. sample_question_paper.pdf - Upload in tab "1. Upload Question Paper"
2. sample_answer_booklet.pdf - Upload in tab "3. Submit Answer"

Quick test flow:
----------------
1. Start server: py -m uvicorn app.main:app --host 127.0.0.1 --port 8001
2. Open http://127.0.0.1:8001/

3. Tab 1: Upload sample_question_paper.pdf → Click Analyze
4. Tab 2: Fill answer keys:
   - Q1: "Process by which plants make food using sunlight"
   - Q2: "H2O"
   - Q3: "Object at rest stays at rest"
   → Click Save all

5. Tab 3: Select question set → Upload sample_answer_booklet.pdf → Submit
6. Tab 4: View results (submission ID auto-filled)
