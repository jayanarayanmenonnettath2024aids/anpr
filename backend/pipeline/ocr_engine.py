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

        elif engine == "easyocr":
            try:
                import easyocr
                # Disable GPU if no CUDA is available, usually CPU is fine for small plates
                self.ocr = easyocr.Reader(['en'], gpu=False, verbose=False)
                self.engine_name = "easyocr"
                logger.info("EasyOCR initialized successfully")
            except ImportError:
                logger.error("EasyOCR not installed! Run: pip install easyocr")
                self.ocr = None
        elif engine == "tesseract":
            try:
                import pytesseract
                import os
                # Set tesseract path for Windows if installed via winget
                if os.name == 'nt' and os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
                    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
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
            elif self.engine_name == "easyocr":
                return self._easyocr_ocr(plate_image)
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

    def _easyocr_ocr(self, image):
        """Run EasyOCR."""
        result = self.ocr.readtext(image)
        if not result:
            return None, 0.0

        texts = []
        confidences = []

        for bbox, text, conf in result:
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
        # Remove everything except letters, digits (like INPR removal of punctuation)
        text = re.sub(r"[^A-Za-z0-9]", "", text)
        text = text.upper().strip()
        return text

    @staticmethod
    def validate_indian_plate(text):
        """
        Validate against common Indian plate formats based on INPR logic.
        Validates state code and applies strict regex pattern match.
        """
        clean = text.upper()
        
        # INPR defined state codes
        valid_states = [
            'AP', 'AR', 'AS', 'BR', 'CG', 'GA', 'GJ', 'HR', 'HP', 'JK', 'JH', 
            'KA', 'KL', 'MP', 'MH', 'MN', 'ML', 'MZ', 'NL', 'OD', 'PB', 'RJ', 
            'SK', 'TN', 'TS', 'TR', 'UA', 'UK', 'UP', 'WB', 'AN', 'CH', 'DN', 
            'DD', 'DL', 'LD', 'PY'
        ]
        
        # Check if the plate starts with a valid state code
        if clean[:2] not in valid_states:
            return False
            
        # INPR specific patterns
        # pattern_1: 2 chars + 2 digits + 2 chars + 4 digits
        # pattern_2: 2 chars + 2 digits + 1 char + 4 digits
        pattern_1 = r"^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$"
        pattern_2 = r"^[A-Z]{2}\d{2}[A-Z]{1}\d{4}$"
        
        if re.match(pattern_1, clean) or re.match(pattern_2, clean):
            return True
            
        return False
