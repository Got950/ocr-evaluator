"""Create sample PDFs for testing the OCR Evaluator."""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "test_samples"


def create_question_paper(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica", 22)
    y = 800
    c.drawString(72, y, "Sample Question Paper")
    y -= 60
    c.setFont("Helvetica", 16)
    c.drawString(72, y, "1. Define photosynthesis. (5 marks)")
    y -= 40
    c.drawString(72, y, "2. What is the chemical formula of water? (3 marks)")
    y -= 40
    c.drawString(72, y, "3. Explain Newton's first law. (7 marks)")
    c.save()


def create_answer_booklet(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica", 18)
    y = 800
    c.drawString(72, y, "1. Photosynthesis is the process by which plants make")
    y -= 35
    c.drawString(72, y, "food using sunlight.")
    y -= 50
    c.drawString(72, y, "2. The formula is H2O.")
    y -= 50
    c.drawString(72, y, "3. Newton's first law says an object at rest stays at rest.")
    c.save()


if __name__ == "__main__":
    SAMPLES_DIR.mkdir(exist_ok=True)
    qp = SAMPLES_DIR / "sample_question_paper.pdf"
    ab = SAMPLES_DIR / "sample_answer_booklet.pdf"
    create_question_paper(qp)
    create_answer_booklet(ab)
    print("Created:")
    print("  -", qp)
    print("  -", ab)
    print("\nUse these in the UI at http://127.0.0.1:8001/")
