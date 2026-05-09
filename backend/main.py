"""
ANPR System — FastAPI Application Entry Point.
Orchestrates the full pipeline: capture → motion → trigger → detect → OCR → stream.
"""
import asyncio
import threading
import time
import os
import cv2
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import Config
from pipeline.video_capture import VideoCapture
from pipeline.motion_detector import MotionDetector
from pipeline.trigger_zone import TriggerZone
from pipeline.plate_detector import PlateDetector
from pipeline.preprocessor import Preprocessor
from pipeline.ocr_engine import OCREngine
from services.plate_manager import PlateManager
from services.stream_manager import StreamManager
from db.database import Database
from routes import ws, api

# ─── Logging Setup ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ANPR")

# ─── Global Instances ─────────────────────────────────────────────
database = Database(Config.DB_PATH)
stream_manager = StreamManager()
plate_manager = PlateManager(
    dedup_window=Config.DEDUP_WINDOW_SECONDS,
    blacklist=Config.BLACKLIST_PLATES,
    plates_dir=Config.PLATES_DIR,
)

# Pipeline components
video_capture = VideoCapture(Config.VIDEO_SOURCE, Config.MAX_QUEUE_SIZE)
motion_detector = MotionDetector(
    history=Config.MOG2_HISTORY,
    var_threshold=Config.MOG2_VAR_THRESHOLD,
    detect_shadows=Config.MOG2_DETECT_SHADOWS,
    min_contour_area=Config.MIN_CONTOUR_AREA,
)
trigger_zone = TriggerZone(
    line_y=Config.TRIGGER_LINE_Y,
    tolerance=Config.TRIGGER_TOLERANCE,
    cooldown=Config.TRIGGER_COOLDOWN,
)
plate_detector = PlateDetector(
    min_aspect_ratio=Config.PLATE_MIN_ASPECT_RATIO,
    max_aspect_ratio=Config.PLATE_MAX_ASPECT_RATIO,
    min_area=Config.PLATE_MIN_AREA,
    max_area=Config.PLATE_MAX_AREA,
    approx_epsilon=Config.PLATE_APPROX_EPSILON,
    max_candidates=Config.PLATE_MAX_CANDIDATES,
    sharpness_threshold=Config.SHARPNESS_THRESHOLD,
)
preprocessor = Preprocessor()
ocr_engine = OCREngine(
    engine=Config.OCR_ENGINE,
    lang=Config.OCR_LANGUAGE,
    confidence_threshold=Config.OCR_CONFIDENCE_THRESHOLD,
    use_angle_cls=Config.OCR_USE_ANGLE_CLS,
)

# ─── Pipeline State ──────────────────────────────────────────────
pipeline_running = False
pipeline_thread = None
latest_annotated_frame = None
frame_lock = threading.Lock()
main_loop = None


def run_pipeline():
    """
    Main processing pipeline — runs in a background thread.
    
    Pipeline steps:
    1. Get frame from capture queue
    2. Apply frame skipping
    3. Crop ROI
    4. Run motion detection
    5. Check trigger zone
    6. If triggered → detect plate → OCR
    7. Store annotated frame for WebSocket streaming
    """
    global pipeline_running, latest_annotated_frame

    logger.info("🚀 Pipeline started")
    frame_count = 0
    loop = None

    while pipeline_running:
        frame = video_capture.get_frame_blocking(timeout=1.0)
        if frame is None:
            continue

        frame_count += 1

        # Frame skipping
        if frame_count % Config.FRAME_SKIP != 0:
            continue

        original_frame = frame.copy()
        display_frame = frame.copy()

        # ─── Step 1: ROI Cropping ─────────────────────────────────
        if Config.ROI_ENABLED:
            roi = frame[
                Config.ROI_Y1: Config.ROI_Y2,
                Config.ROI_X1: Config.ROI_X2,
            ]
            # Draw ROI rectangle on display frame
            cv2.rectangle(
                display_frame,
                (Config.ROI_X1, Config.ROI_Y1),
                (Config.ROI_X2, Config.ROI_Y2),
                (0, 255, 255), 2,
            )
        else:
            roi = frame

        if roi.size == 0:
            continue

        # ─── Step 2: Motion Detection ─────────────────────────────
        bounding_boxes, fg_mask = motion_detector.detect(roi)

        # Draw motion contours on display frame
        for (x, y, w, h) in bounding_boxes:
            dx = Config.ROI_X1 if Config.ROI_ENABLED else 0
            dy = Config.ROI_Y1 if Config.ROI_ENABLED else 0
            cv2.rectangle(
                display_frame,
                (x + dx, y + dy),
                (x + dx + w, y + dy + h),
                (0, 255, 0), 1,
            )

        # ─── Step 3: Trigger Zone Check ───────────────────────────
        if Config.TRIGGER_ZONE_ENABLED:
            # Draw trigger line on display frame
            dx = Config.ROI_X1 if Config.ROI_ENABLED else 0
            dy = Config.ROI_Y1 if Config.ROI_ENABLED else 0
            line_y_global = Config.TRIGGER_LINE_Y + dy
            cv2.line(
                display_frame,
                (dx, line_y_global),
                (Config.ROI_X2 if Config.ROI_ENABLED else display_frame.shape[1], line_y_global),
                (0, 0, 255), 2,
            )
            cv2.putText(
                display_frame, "TRIGGER ZONE",
                (dx + 10, line_y_global - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1,
            )

            triggered = trigger_zone.check(bounding_boxes)
        else:
            triggered = bounding_boxes  # Process all if no trigger zone

        # ─── Step 4: Plate Detection & OCR ────────────────────────
        for (vx, vy, vw, vh) in triggered:
            # Add padding to the vehicle bounding box to ensure we capture the bumper/plate
            # even if the motion detector only caught the headlights
            pad_x = 100
            pad_y = 100
            x1 = max(0, vx - pad_x)
            y1 = max(0, vy - pad_y)
            x2 = min(roi.shape[1], vx + vw + pad_x)
            y2 = min(roi.shape[0], vy + vh + pad_y)
            
            # Get vehicle region from ROI
            vehicle_region = roi[y1: y2, x1: x2]
            if vehicle_region.size == 0:
                continue

            # Detect plate candidates
            candidates = plate_detector.detect(vehicle_region)

            for candidate in candidates:
                plate_img = candidate["plate_image"]
                bbox = candidate["bbox"]
                sharpness = candidate["sharpness"]

                # Preprocess for OCR
                processed = preprocessor.preprocess_for_ocr(plate_img)

                # Run OCR
                text, confidence = ocr_engine.recognize(plate_img)

                if text and len(text.replace(" ", "")) >= 4:
                    # Check deduplication
                    if plate_manager.is_duplicate(text):
                        continue

                    # Check blacklist
                    is_blacklisted = plate_manager.is_blacklisted(text)

                    # Save plate image
                    image_filename = plate_manager.save_plate_image(plate_img)

                    # Record stats
                    plate_manager.record_detection(confidence)

                    # Store in database (async from sync thread)
                    detection_data = {
                        "plate_text": text,
                        "confidence": round(confidence, 3),
                        "timestamp": datetime.now().isoformat(),
                        "camera_id": Config.CAMERA_ID,
                        "image_url": f"/plates/{image_filename}",
                        "is_blacklisted": is_blacklisted,
                    }

                    # Schedule async tasks
                    if main_loop is not None:
                        try:
                            asyncio.run_coroutine_threadsafe(
                                _handle_detection(detection_data, image_filename, is_blacklisted),
                                main_loop,
                            )
                        except Exception as e:
                            logger.error(f"Failed to schedule detection: {e}")

                    # Draw detection on display frame
                    dx = Config.ROI_X1 if Config.ROI_ENABLED else 0
                    dy = Config.ROI_Y1 if Config.ROI_ENABLED else 0
                    px, py, pw, ph = bbox
                    cv2.rectangle(
                        display_frame,
                        (px + x1 + dx, py + y1 + dy),
                        (px + x1 + dx + pw, py + y1 + dy + ph),
                        (255, 0, 255), 2,
                    )
                    cv2.putText(
                        display_frame,
                        f"{text} ({confidence:.0%})",
                        (px + x1 + dx, py + y1 + dy - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2,
                    )

                    logger.info(
                        f"✅ PLATE: {text} | conf={confidence:.2%} | "
                        f"sharp={sharpness:.1f} | blacklist={is_blacklisted}"
                    )

        # ─── Step 5: Add overlay info ─────────────────────────────
        cv2.putText(
            display_frame,
            f"ANPR | {Config.CAMERA_ID} | Frame #{frame_count}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2,
        )
        cv2.putText(
            display_frame,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1,
        )

        # Store annotated frame for WebSocket streaming
        _, jpeg = cv2.imencode(
            ".jpg", display_frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), Config.JPEG_QUALITY],
        )
        with frame_lock:
            latest_annotated_frame = jpeg.tobytes()

    logger.info("Pipeline stopped")


async def _handle_detection(detection_data, image_filename, is_blacklisted):
    """Handle a plate detection — store in DB and broadcast via WebSocket."""
    try:
        await database.add_plate(
            plate_text=detection_data["plate_text"],
            confidence=detection_data["confidence"],
            camera_id=detection_data["camera_id"],
            image_path=image_filename,
            is_blacklisted=is_blacklisted,
        )
        await stream_manager.broadcast_detection(detection_data)
    except Exception as e:
        logger.error(f"Detection handler error: {e}")


async def stream_frames():
    """Continuously stream annotated frames to WebSocket clients."""
    global latest_annotated_frame
    while pipeline_running:
        with frame_lock:
            frame_bytes = latest_annotated_frame

        if frame_bytes and stream_manager.feed_client_count > 0:
            await stream_manager.broadcast_frame(frame_bytes)

        await asyncio.sleep(1.0 / 30)  # ~30 FPS max


# ─── App Lifecycle ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    global pipeline_running, pipeline_thread, main_loop

    main_loop = asyncio.get_running_loop()

    logger.info("=" * 60)
    logger.info("  ANPR System Starting...")
    logger.info(f"  Video Source: {Config.VIDEO_SOURCE}")
    logger.info(f"  Camera ID: {Config.CAMERA_ID}")
    logger.info(f"  OCR Engine: {Config.OCR_ENGINE}")
    logger.info(f"  Frame Skip: every {Config.FRAME_SKIP}th frame")
    logger.info("=" * 60)

    # Initialize database
    await database.init()

    # Load blacklist from DB
    bl_records = await database.get_blacklist()
    for rec in bl_records:
        plate_manager.add_to_blacklist(rec["plate_text"])
    logger.info(f"Loaded {len(bl_records)} blacklisted plates from DB")

    # Create plates directory
    os.makedirs(Config.PLATES_DIR, exist_ok=True)
    os.makedirs("data", exist_ok=True)

    # Start video capture
    video_capture.start()

    # Start pipeline thread
    pipeline_running = True
    pipeline_thread = threading.Thread(target=run_pipeline, daemon=True)
    pipeline_thread.start()

    # Start frame streaming task
    stream_task = asyncio.create_task(stream_frames())

    yield

    # Shutdown
    logger.info("Shutting down ANPR system...")
    pipeline_running = False
    video_capture.stop()
    if pipeline_thread:
        pipeline_thread.join(timeout=5)
    stream_task.cancel()
    await database.close()
    logger.info("ANPR system stopped.")


# ─── FastAPI App ──────────────────────────────────────────────────
app = FastAPI(
    title="ANPR Command Center",
    description="Lightweight Real-Time Automatic Number Plate Recognition System",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files — serve plate images
os.makedirs(Config.PLATES_DIR, exist_ok=True)
app.mount("/plates", StaticFiles(directory=Config.PLATES_DIR), name="plates")

# Include routers
app.include_router(ws.router)
app.include_router(api.router)


@app.get("/")
async def root():
    return {
        "service": "ANPR Command Center",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=Config.HOST, port=Config.PORT, reload=False)
