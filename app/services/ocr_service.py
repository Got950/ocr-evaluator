from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import torch
from PIL import Image, ImageEnhance, ImageOps
from transformers import TrOCRProcessor, VisionEncoderDecoderModel


logger = logging.getLogger("ocr_evaluator.ocr")


@dataclass(frozen=True)
class OCRService:
    processor: TrOCRProcessor
    model: VisionEncoderDecoderModel
    device: torch.device

    @classmethod
    def load(cls) -> "OCRService":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info("OCR running on device: %s", device)
        processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
        model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten")
        model.to(device)
        model.eval()
        return cls(processor=processor, model=model, device=device)

    def _preprocess(self, img: Image.Image) -> Image.Image:
        img = img.convert("RGB")
        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
        img = ImageOps.pad(img, (1024, 1024), method=resampling, color=(255, 255, 255))
        img = ImageEnhance.Contrast(img).enhance(1.1)
        return img

    def _ocr_image(self, img: Image.Image) -> str:
        img = self._preprocess(img)
        pixel_values = self.processor(images=img, return_tensors="pt").pixel_values.to(self.device)
        with torch.inference_mode():
            generated_ids = self.model.generate(pixel_values, max_length=512, num_beams=2)
        return self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()

    def _pdftotext_fallback(self, pdf_path: str) -> str:
        """Extract text from typed PDFs using poppler's pdftotext."""
        import subprocess

        try:
            result = subprocess.run(
                ["pdftotext", "-layout", pdf_path, "-"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass
        return ""

    def _ocr_pdf(self, pdf_path: str) -> str:
        # Try pdftotext first for typed PDFs
        typed_text = self._pdftotext_fallback(pdf_path)
        if typed_text and len(typed_text) >= 20:
            return typed_text

        try:
            from pdf2image import convert_from_path
        except Exception as e:
            raise ValueError("pdf2image is required for PDF OCR") from e

        try:
            pages = convert_from_path(pdf_path)
        except Exception as e:
            raise ValueError("Failed to convert PDF to images (poppler required)") from e

        if not pages:
            raise ValueError("PDF is empty")

        t0 = time.time()
        parts: list[str] = []
        for page in pages:
            text = self._ocr_image(page)
            parts.append(text)
        logger.info("OCR took %.2f seconds", float(time.time() - t0))

        full_text = "\n\n".join([p for p in parts if p]).strip()
        if (not full_text) or (len(full_text) < 20):
            raise ValueError("OCR extraction too short")
        return full_text

    def _resolve_path(self, image_path: str) -> str:
        """If the path starts with s3://, download to a temp file first."""
        if image_path.startswith("s3://"):
            s3_key = image_path[5:]
            import tempfile
            from app.services.storage_service import StorageService
            storage = StorageService.from_settings()
            data = storage.download_file_sync(s3_key)
            suffix = ".pdf" if s3_key.lower().endswith(".pdf") else ".png"
            tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            tmp.write(data)
            tmp.close()
            return tmp.name
        return image_path

    def extract_text(self, image_path: str) -> str:
        resolved = self._resolve_path(image_path)
        try:
            if resolved.lower().endswith(".pdf"):
                return self._ocr_pdf(resolved)

            t0 = time.time()
            with Image.open(resolved) as img:
                text = self._ocr_image(img)
            logger.info("OCR took %.2f seconds", float(time.time() - t0))
            if (not text) or (len(text) < 20):
                raise ValueError("OCR extraction too short")
            return text
        finally:
            if resolved != image_path:
                import os
                try:
                    os.unlink(resolved)
                except Exception:
                    pass

