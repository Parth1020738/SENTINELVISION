"""
SentinelVision - Plate OCR

Abstract interface for license plate OCR plus text normalization
and basic Indian plate format validation.

Phase 5: ANPR / License Plate Recognition

Design notes
------------
- The OCR backend returns structured PlateOCRResult objects.
- Text normalization is pure logic — fully testable without any
  OCR engine.
- is_valid_plate_format is a tolerant sanity check, NOT a legal
  validity check.
- For testing, inject a mock that implements PlateOCR.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Structured OCR result
# ---------------------------------------------------------------------------
@dataclass
class PlateOCRResult:
    """Result of OCR on a license plate crop.

    Attributes
    ----------
    text : str
        Raw recognized text (before normalization).
    confidence : float
        OCR confidence in [0, 1].
    """

    text: str
    confidence: float


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------
class PlateOCR(ABC):
    """Abstract interface for license plate OCR.

    Any object that implements ``recognize(crop) -> PlateOCRResult``
    satisfies this interface.  Real implementations may use PaddleOCR,
    EasyOCR, Tesseract, or any other backend.
    """

    @abstractmethod
    def recognize(self, crop: np.ndarray) -> PlateOCRResult:
        """Run OCR on a license plate crop.

        Parameters
        ----------
        crop : np.ndarray
            Cropped image of a license plate (BGR).

        Returns
        -------
        PlateOCRResult
            Recognized text and confidence.
        """
        ...


# ---------------------------------------------------------------------------
# Text normalization — pure logic, no model required
# ---------------------------------------------------------------------------
def normalize_plate_text(text: Optional[str]) -> str:
    """Normalize OCR text for license plates.

    Steps
    -----
    - Convert to uppercase.
    - Remove spaces, hyphens, dots, and all non-alphanumeric characters.
    - Keep only [A-Z0-9].

    Returns an empty string when input is ``None`` or becomes empty
    after stripping.
    """
    if text is None:
        return ""

    # Uppercase first
    text = text.upper()

    # Keep only alphanumeric characters
    cleaned = "".join(ch for ch in text if ch.isalnum())

    return cleaned


# ---------------------------------------------------------------------------
# Basic Indian plate format validation — tolerant sanity check only
# ---------------------------------------------------------------------------
def is_valid_plate_format(text: str) -> bool:
    """Check whether *text* looks like a common Indian registration plate.

    This is a **tolerant sanity check** — it does NOT prove a plate is
    legally valid.  It simply rejects obvious garbage.

    Accepted loose format::

        XX##XX####   (state, district, series, number)
        e.g. GJ01AB1234, MH12CD3456, DL01AB1234

    Rules
    -----
    - Length must be between 7 and 11 characters.
    - Must start with at least 2 letters (state code).
    - Must contain at least 2 digits (district code).
    - Must be entirely alphanumeric.
    """
    if not text:
        return False

    n = len(text)
    if n < 7 or n > 11:
        return False

    # Must be entirely alphanumeric
    if not text.isalnum():
        return False

    # Must start with at least 2 letters
    letter_prefix = 0
    for ch in text:
        if ch.isalpha():
            letter_prefix += 1
        else:
            break
    if letter_prefix < 2:
        return False

    # Must contain at least 2 digits
    digit_count = sum(1 for ch in text if ch.isdigit())
    if digit_count < 2:
        return False

    return True


# ---------------------------------------------------------------------------
# Real OCR backend — EasyOCR
# ---------------------------------------------------------------------------
class EasyOCROCR(PlateOCR):
    """Real OCR backend backed by EasyOCR.

    EasyOCR recognises alphanumeric scene text and is a good fit for
    license-plate crops.  It ships its own deep-learning models and, when a
    CUDA-capable torch is present, runs on the GPU.

    ``easyocr`` is imported lazily inside ``__init__`` so that the module
    (and the Phase 5 unit tests) can be imported and byte-compiled even when
    EasyOCR is not installed.
    """

    def __init__(self, langs=("en",), gpu: Optional[bool] = None) -> None:
        # Auto-detect GPU via torch if not specified explicitly.
        if gpu is None:
            try:
                import torch

                gpu = bool(torch.cuda.is_available())
            except Exception:
                gpu = False
        self._gpu = gpu

        import easyocr

        self._reader = easyocr.Reader(list(langs), gpu=gpu, verbose=False)
        print(f"[EasyOCROCR] EasyOCR reader ready (langs={list(langs)}, gpu={gpu})")

    # ------------------------------------------------------------------
    def recognize(self, crop: np.ndarray) -> PlateOCRResult:
        """Run EasyOCR on a BGR plate crop and return raw text + confidence.

        EasyOCR expects RGB input.  Very small crops are upscaled (preserving
        aspect ratio) to avoid the recogniser choking on sub-100px plates.
        """
        if crop is None or crop.size == 0:
            return PlateOCRResult(text="", confidence=0.0)

        # BGR (OpenCV) -> RGB
        rgb = np.ascontiguousarray(crop[:, :, ::-1])

        # Upscale tiny crops so characters are legible.
        h, w = rgb.shape[:2]
        if w < 256 and w > 0:
            import cv2

            scale = 256.0 / w
            rgb = cv2.resize(
                rgb, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
            )

        try:
            read_fn = getattr(self._reader, "readtext", None)
            if read_fn is None:
                read_fn = self._reader.read_text
            results = read_fn(rgb, detail=1, paragraph=False)
        except Exception as exc:  # defensive: never let OCR crash the pipeline
            print(f"[EasyOCROCR] read_text error: {exc}")
            return PlateOCRResult(text="", confidence=0.0)

        if not results:
            return PlateOCRResult(text="", confidence=0.0)

        texts = []
        confs = []
        for line in results:  # each: [bbox, text, confidence]
            text = line[1]
            conf = float(line[2])
            if text:
                texts.append(text)
                confs.append(conf)

        if not texts:
            return PlateOCRResult(text="", confidence=0.0)

        combined = " ".join(texts)
        confidence = sum(confs) / len(confs)
        return PlateOCRResult(text=combined, confidence=confidence)


# ---------------------------------------------------------------------------
# Real OCR backend — Tesseract (lightweight subprocess fallback)
# ---------------------------------------------------------------------------
class TesseractOCR(PlateOCR):
    """Real OCR backend backed by Tesseract (via pytesseract).

    Lightweight, fast-per-call alternative to EasyOCR.  Requires the
    Tesseract binary on the system (e.g. installed via winget).
    """

    def __init__(self, tesseract_cmd: Optional[str] = None) -> None:
        import pytesseract

        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        self._pytesseract = pytesseract

    # ------------------------------------------------------------------
    def recognize(self, crop: np.ndarray) -> PlateOCRResult:
        if crop is None or crop.size == 0:
            return PlateOCRResult(text="", confidence=0.0)

        import cv2

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        if w < 256 and w > 0:
            scale = 256.0 / w
            gray = cv2.resize(
                gray, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
            )

        try:
            data = self._pytesseract.image_to_data(
                gray, config="--psm 7", output_type=self._pytesseract.Output.DICT
            )
        except Exception as exc:
            print(f"[TesseractOCR] error: {exc}")
            return PlateOCRResult(text="", confidence=0.0)

        words, confs = [], []
        for text, conf in zip(data.get("text", []), data.get("conf", [])):
            text = str(text).strip()
            try:
                conf = float(conf)
            except (TypeError, ValueError):
                continue
            if text and conf >= 0:
                words.append(text)
                confs.append(conf / 100.0)

        if not words:
            return PlateOCRResult(text="", confidence=0.0)
        return PlateOCRResult(
            text=" ".join(words),
            confidence=sum(confs) / len(confs),
        )
