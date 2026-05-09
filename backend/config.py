"""
ANPR System Configuration
All tunable parameters in one place.
"""
import os


class Config:
    # ─── Video Source ──────────────────────────────────────────────
    VIDEO_SOURCE = os.getenv("VIDEO_SOURCE", "video.mp4")  # file path or rtsp:// URL
    CAMERA_ID = os.getenv("CAMERA_ID", "CAM-01")

    # ─── ROI Cropping (y1, y2, x1, x2) ────────────────────────────
    # Set to None to process full frame. Adjust for your camera.
    ROI_ENABLED = True
    ROI_Y1 = int(os.getenv("ROI_Y1", "250"))
    ROI_Y2 = int(os.getenv("ROI_Y2", "800"))
    ROI_X1 = int(os.getenv("ROI_X1", "200"))
    ROI_X2 = int(os.getenv("ROI_X2", "1400"))

    # ─── Motion Detection (MOG2) ──────────────────────────────────
    MOG2_HISTORY = 500
    MOG2_VAR_THRESHOLD = 50
    MOG2_DETECT_SHADOWS = True
    MIN_CONTOUR_AREA = 5000  # px² — ignore contours smaller than this

    # ─── Trigger Zone ─────────────────────────────────────────────
    TRIGGER_ZONE_ENABLED = True
    TRIGGER_LINE_Y = 400       # Y position of trigger line within ROI
    TRIGGER_TOLERANCE = 40     # px tolerance around the line
    TRIGGER_COOLDOWN = 2.0     # seconds cooldown per tracked object

    # ─── Plate Detection ──────────────────────────────────────────
    PLATE_MIN_ASPECT_RATIO = 1.5   # width / height
    PLATE_MAX_ASPECT_RATIO = 6.0
    PLATE_MIN_AREA = 800
    PLATE_MAX_AREA = 50000
    PLATE_APPROX_EPSILON = 0.02    # fraction of perimeter for approxPolyDP
    PLATE_MAX_CANDIDATES = 10      # max contours to evaluate

    # ─── Image Preprocessing ──────────────────────────────────────
    BILATERAL_D = 11
    BILATERAL_SIGMA_COLOR = 17
    BILATERAL_SIGMA_SPACE = 17
    CANNY_THRESHOLD1 = 30
    CANNY_THRESHOLD2 = 200
    ADAPTIVE_BLOCK_SIZE = 11
    ADAPTIVE_C = 2
    MORPH_KERNEL_SIZE = (3, 3)

    # ─── OCR ──────────────────────────────────────────────────────
    OCR_ENGINE = os.getenv("OCR_ENGINE", "paddleocr")  # "paddleocr" or "tesseract"
    OCR_LANGUAGE = "en"
    OCR_CONFIDENCE_THRESHOLD = 0.4
    OCR_USE_ANGLE_CLS = True

    # ─── Sharpness Selection ─────────────────────────────────────
    SHARPNESS_THRESHOLD = 50.0  # Laplacian variance — reject below this

    # ─── Performance ──────────────────────────────────────────────
    FRAME_SKIP = 3          # process every Nth frame
    JPEG_QUALITY = 70       # for WebSocket video streaming
    MAX_QUEUE_SIZE = 2      # capture queue depth

    # ─── Deduplication ────────────────────────────────────────────
    DEDUP_WINDOW_SECONDS = 30  # suppress same plate within this window

    # ─── Blacklist ────────────────────────────────────────────────
    BLACKLIST_PLATES = [
        # Add plates to watch for, e.g.:
        # "KA01AB1234",
    ]

    # ─── Database ─────────────────────────────────────────────────
    DB_PATH = os.getenv("DB_PATH", "data/anpr.db")

    # ─── Server ───────────────────────────────────────────────────
    HOST = "0.0.0.0"
    PORT = 8000
    CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000", "*"]

    # ─── Plate Storage ────────────────────────────────────────────
    PLATES_DIR = "plates"
