"""
OCR Engine Wrapper.
Supports PaddleOCR (primary) and Tesseract (fallback).
Includes character normalization for license plate text.
"""
import re
import logging

logger = logging.getLogger(__name__)

# Character normalization map (common OCR confusions for plates)
CHAR_MAP = {
    "O": "0", "D": "0", "Q": "0",  # letters → digits (in digit positions)
    "I": "1", "L": "1",
    "Z": "2",
    "B": "8",
    "S": "5",
    "G": "6",
}


class OCREngine:
    def __init__(self, engine="paddleocr", lang="en", confidence_threshold=0.4, use_angle_cls=True):
        self.engine_name = engine
        self.lang = lang
        self.confidence_threshold = confidence_threshold
        self.ocr = None
        self._init_engine(engine, lang, use_angle_cls)

    def _init_engine(self, engine, lang, use_angle_cls):
        """Initialize the OCR engine."""
        if engine == "paddleocr":
            try:
                from paddleocr import PaddleOCR
                self.ocr = PaddleOCR(
                    use_angle_cls=use_angle_cls,
                    lang=lang,
                    show_log=False,
                    use_gpu=False,
                )
                logger.info("PaddleOCR initialized successfully")
            except ImportError:
                logger.warning("PaddleOCR not installed, falling back to Tesseract")
                self._init_engine("tesseract", lang, use_angle_cls)
                return
            except Exception as e:
                logger.warning(f"PaddleOCR init failed: {e}, falling back to Tesseract")
                self._init_engine("tesseract", lang, use_angle_cls)
                return

        elif engine == "tesseract":
            try:
                import pytesseract
                self.ocr = pytesseract
                self.engine_name = "tesseract"
                logger.info("Tesseract OCR initialized")
            except ImportError:
                logger.error(
                    "Neither PaddleOCR nor Tesseract available! "
                    "Install: pip install paddleocr paddlepaddle  OR  pip install pytesseract"
                )
                self.ocr = None

    def recognize(self, plate_image):
        """
        Run OCR on a cropped plate image.
        
        Args:
            plate_image: BGR or grayscale image of the plate
            
        Returns:
            (text, confidence) or (None, 0.0) if failed
        """
        if self.ocr is None:
            return None, 0.0

        try:
            if self.engine_name == "paddleocr":
                return self._paddle_ocr(plate_image)
            elif self.engine_name == "tesseract":
                return self._tesseract_ocr(plate_image)
        except Exception as e:
            logger.error(f"OCR error: {e}")
            return None, 0.0

    def _paddle_ocr(self, image):
        """Run PaddleOCR."""
        result = self.ocr.ocr(image, cls=True)

        if not result or not result[0]:
            return None, 0.0

        # Combine all text lines
        texts = []
        confidences = []

        for line in result[0]:
            if line and len(line) >= 2:
                text = line[1][0]
                conf = line[1][1]
                texts.append(text)
                confidences.append(conf)

        if not texts:
            return None, 0.0

        combined_text = " ".join(texts)
        avg_confidence = sum(confidences) / len(confidences)

        # Normalize
        cleaned = self._normalize_plate_text(combined_text)

        if avg_confidence < self.confidence_threshold:
            return None, avg_confidence

        return cleaned, avg_confidence

    def _tesseract_ocr(self, image):
        """Run Tesseract OCR."""
        import cv2

        # Ensure grayscale
        if len(image.shape) == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Tesseract config for license plates
        config = (
            "--oem 3 --psm 7 "
            "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        )

        text = self.ocr.image_to_string(image, config=config).strip()

        if not text:
            return None, 0.0

        # Get confidence
        try:
            data = self.ocr.image_to_data(image, config=config, output_type=self.ocr.Output.DICT)
            confs = [int(c) for c in data["conf"] if int(c) > 0]
            avg_confidence = (sum(confs) / len(confs) / 100.0) if confs else 0.5
        except Exception:
            avg_confidence = 0.5

        cleaned = self._normalize_plate_text(text)

        if avg_confidence < self.confidence_threshold:
            return None, avg_confidence

        return cleaned, avg_confidence

    @staticmethod
    def _normalize_plate_text(text):
        """
        Normalize OCR output for license plates.
        - Remove non-alphanumeric characters
        - Uppercase
        - Fix common confusions
        """
        # Remove everything except letters, digits, spaces
        text = re.sub(r"[^A-Za-z0-9\s]", "", text)
        text = text.upper().strip()

        # Remove excessive spaces
        text = re.sub(r"\s+", " ", text)

        return text

    @staticmethod
    def validate_indian_plate(text):
        """
        Validate against common Indian plate formats.
        Examples: KA01AB1234, MH02CD5678, DL3CAB1234
        
        Returns True if it loosely matches an Indian plate pattern.
        """
        # Remove spaces
        clean = text.replace(" ", "")

        # Indian plate pattern: 2 letters + 2 digits + 1-3 letters + 4 digits
        pattern = r"^[A-Z]{2}\d{1,2}[A-Z]{1,3}\d{4}$"
        return bool(re.match(pattern, clean))
