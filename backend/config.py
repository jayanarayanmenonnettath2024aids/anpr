"""
ANPR System Configuration
All tunable parameters in one place.
"""
import os


class Config:
    # ─── Video Source ──────────────────────────────────────────────
    VIDEO_SOURCE = os.getenv("VIDEO_SOURCE", "video/videoq.mp4")  # file path or rtsp:// URL
    CAMERA_ID = os.getenv("CAMERA_ID", "CAM-01")

    # ─── ROI Cropping (y1, y2, x1, x2) ────────────────────────────
    # Set to None to process full frame. Adjust for your camera.
    ROI_ENABLED = True
    ROI_Y1 = int(os.getenv("ROI_Y1", "220"))   # Lower-half crop tuned for the target lane
    ROI_Y2 = int(os.getenv("ROI_Y2", "720"))   # Stop at the bottom (video is 720p)
    ROI_X1 = int(os.getenv("ROI_X1", "260"))
    ROI_X2 = int(os.getenv("ROI_X2", "1120"))

    # ─── Motion Detection (MOG2) ──────────────────────────────────
    MOG2_HISTORY = 250
    MOG2_VAR_THRESHOLD = 50
    MOG2_DETECT_SHADOWS = True
    MIN_CONTOUR_AREA = 3500  # px² — ignore contours smaller than this

    # ─── Trigger Zone ─────────────────────────────────────────────
    TRIGGER_ZONE_ENABLED = False
    TRIGGER_LINE_Y = 500       # Y position of trigger line within ROI
    TRIGGER_TOLERANCE = 60     # px tolerance around the line
    TRIGGER_COOLDOWN = 2.0     # seconds cooldown per tracked object

    # ─── Plate Detection ──────────────────────────────────────────
    PLATE_MIN_ASPECT_RATIO = 2.0
    PLATE_MAX_ASPECT_RATIO = 5.5
    PLATE_MIN_AREA = 1000          # small plates
    PLATE_MAX_AREA = 9000          # Reject massive truck banners!
    PLATE_APPROX_EPSILON = 0.02    # fraction of perimeter for approxPolyDP
    PLATE_MAX_CANDIDATES = 5       # max contours to evaluate

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
    OCR_ENGINE = os.getenv("OCR_ENGINE", "tesseract")  # "paddleocr", "tesseract", or "easyocr"
    OCR_LANGUAGE = "en"
    OCR_CONFIDENCE_THRESHOLD = 0.25
    OCR_USE_ANGLE_CLS = False

    # ─── Sharpness Selection ─────────────────────────────────────
    SHARPNESS_THRESHOLD = 8.0  # Laplacian variance — reject below this

    # ─── Performance ──────────────────────────────────────────────
    FRAME_SKIP = 4          # process every Nth frame
    JPEG_QUALITY = 60       # for WebSocket video streaming
    MAX_QUEUE_SIZE = 1      # capture queue depth

    # ─── Deduplication ────────────────────────────────────────────
    DEDUP_WINDOW_SECONDS = 45  # suppress same/similar plate within this window
    DEDUP_SIMILARITY_THRESHOLD = 0.86
    PLATE_OCR_TOP_K = 2

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
