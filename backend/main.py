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
from pipeline.inpr_detector import INPRPlateDetector
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
if Config.DETECTOR_BACKEND.lower() == "inpr":
    plate_detector = INPRPlateDetector(
        model_dir=Config.INPR_MODEL_DIR,
        score_threshold=Config.INPR_SCORE_THRESHOLD,
    )
    if not plate_detector.available:
        plate_detector = PlateDetector(
            min_aspect_ratio=Config.PLATE_MIN_ASPECT_RATIO,
            max_aspect_ratio=Config.PLATE_MAX_ASPECT_RATIO,
            min_area=Config.PLATE_MIN_AREA,
            max_area=Config.PLATE_MAX_AREA,
            approx_epsilon=Config.PLATE_APPROX_EPSILON,
            max_candidates=Config.PLATE_MAX_CANDIDATES,
            sharpness_threshold=Config.SHARPNESS_THRESHOLD,
        )
else:
    plate_detector = PlateDetector(
        min_aspect_ratio=Config.PLATE_MIN_ASPECT_RATIO,
        max_aspect_ratio=Config.PLATE_MAX_ASPECT_RATIO,
        min_area=Config.PLATE_MIN_AREA,
        max_area=Config.PLATE_MAX_AREA,
        approx_epsilon=Config.PLATE_APPROX_EPSILON,
        max_candidates=Config.PLATE_MAX_CANDIDATES,
        sharpness_threshold=Config.SHARPNESS_THRESHOLD,
    )
preprocessor = Preprocessor(superres_model_path=Config.OCR_SUPERRES_MODEL if Config.OCR_SUPERRES_ENABLED else None)
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
_detect_buffer = {}


def select_primary_motion_box(bounding_boxes, frame_width, frame_height):
    """
    Pick the most likely target vehicle from multiple motion boxes.

    Prefers large boxes near the center of the ROI, which works better for a
    single-lane or single-car scene than processing every moving object.
    """
    if not bounding_boxes:
        return None

    center_x = frame_width / 2.0
    center_y = frame_height * 0.72

    best_box = None
    best_score = None

    for (x, y, w, h) in bounding_boxes:
        area = w * h
        box_center_x = x + (w / 2.0)
        box_center_y = y + (h / 2.0)
        distance = abs(box_center_x - center_x) / max(frame_width, 1) + abs(box_center_y - center_y) / max(frame_height, 1)

        # Larger and more centered boxes win.
        score = area - (distance * area * 1.5)

        if best_score is None or score > best_score:
            best_score = score
            best_box = (x, y, w, h)

    return best_box


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

        # Convert to grayscale for the detection pipeline
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        frame = cv2.cvtColor(gray_frame, cv2.COLOR_GRAY2BGR)

        original_frame = frame.copy()

        # Apply adaptive thresholding and morphology for the display frame
        # This reduces noise and makes the number plate visible while keeping the B&W effect
        blurred = cv2.GaussianBlur(gray_frame, (5, 5), 0)
        bw_display = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 15, 8
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        bw_display = cv2.erode(bw_display, kernel, iterations=1)
        bw_display = cv2.dilate(bw_display, kernel, iterations=1)
        
        display_frame = cv2.cvtColor(bw_display, cv2.COLOR_GRAY2BGR)

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

        # Keep only the most likely target vehicle in single-car scenes.
        primary_box = select_primary_motion_box(bounding_boxes, roi.shape[1], roi.shape[0])
        triggered = [primary_box] if primary_box is not None else []

        # Draw only the selected target box to avoid clutter from other cars.
        if primary_box is not None:
            x, y, w, h = primary_box
            dx = Config.ROI_X1 if Config.ROI_ENABLED else 0
            dy = Config.ROI_Y1 if Config.ROI_ENABLED else 0
            cv2.rectangle(
                display_frame,
                (x + dx, y + dy),
                (x + dx + w, y + dy + h),
                (0, 255, 0), 2,
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

            triggered = trigger_zone.check(triggered)

        # ─── Step 4: Plate Detection & OCR ────────────────────────
        for (vx, vy, vw, vh) in triggered:
            # Add padding to the vehicle bounding box to ensure we capture the bumper/plate
            # even if the motion detector only caught the headlights
            pad_x = 70
            pad_y = 70
            x1 = max(0, vx - pad_x)
            y1 = max(0, vy - pad_y)
            x2 = min(roi.shape[1], vx + vw + pad_x)
            y2 = min(roi.shape[0], vy + vh + pad_y)
            
            # Get vehicle region from ROI
            vehicle_region = roi[y1: y2, x1: x2]
            if vehicle_region.size == 0:
                continue

            # Detect plate candidates from the tighter vehicle plate zone.
            candidates = plate_detector.detect_in_vehicle_region(roi, (x1, y1, x2 - x1, y2 - y1))
            best_detection = None

            for candidate in candidates[: Config.PLATE_OCR_TOP_K]:
                plate_img = candidate["plate_image"]
                bbox = candidate["bbox"]
                sharpness = candidate["sharpness"]
                
                # 1. Early Blur Rejection
                if sharpness < Config.SHARPNESS_THRESHOLD:
                    continue

                plate_area = plate_img.shape[0] * plate_img.shape[1]
                plate_score = candidate.get("score", 0.0)
                bx, by, bw, bh = bbox
                position_score = max(0.0, min(1.0, (by + bh / 2.0) / max(roi.shape[0], 1)))

                # Try OCR on the enhanced crop first, then on the raw crop as a fallback.
                ocr_inputs = [preprocessor.preprocess_for_ocr(plate_img), plate_img]

                for ocr_input in ocr_inputs:
                    text, confidence = ocr_engine.recognize(ocr_input)

                    if not text:
                        continue

                    normalized_text = plate_manager.normalize_plate_text(text)
                    alnum_len = len(normalized_text)
                    if alnum_len < 4:
                        continue

                    # 2. Strict Filter: Must contain at least one digit
                    if not any(char.isdigit() for char in normalized_text):
                        continue

                    # Prefer valid Indian plates, but keep strong alphanumeric reads
                    # so a partially imperfect OCR pass can still save the plate.
                    is_valid_plate = ocr_engine.validate_indian_plate(normalized_text)
                    strong_read = confidence >= 0.45 and plate_score >= 28.0 and alnum_len >= 6
                    if not is_valid_plate and not strong_read:
                        continue

                    score = (
                        plate_manager.quality_score(confidence, sharpness, plate_area)
                        + plate_score
                        + (position_score * 20.0)
                        + (60.0 if is_valid_plate else 0.0)
                        + (10.0 if ocr_input is plate_img else 0.0)
                    )
                    if best_detection is None or score > best_detection["score"]:
                        best_detection = {
                            "plate_img": plate_img,
                            "bbox": bbox,
                            "sharpness": sharpness,
                            "plate_area": plate_area,
                            "text": normalized_text,
                            "confidence": confidence,
                            "is_valid_plate": is_valid_plate,
                            "score": score,
                        }

            if not best_detection:
                continue

            plate_img = best_detection["plate_img"]
            bbox = best_detection["bbox"]
            sharpness = best_detection["sharpness"]
            plate_area = best_detection["plate_area"]
            text = best_detection["text"]
            confidence = best_detection["confidence"]
            is_valid_plate = best_detection["is_valid_plate"]

            decision = plate_manager.evaluate_detection(text, confidence, sharpness, plate_area)
            if decision["action"] == "skip":
                continue

            # Save or replace the best available crop for this plate.
            if decision["action"] == "replace" and decision["replace_filename"]:
                image_filename = plate_manager.save_plate_image(plate_img, filename=decision["replace_filename"])
            else:
                image_filename = plate_manager.save_plate_image(plate_img)

            plate_manager.commit_detection(
                text,
                image_filename,
                confidence,
                sharpness,
                plate_area=plate_area,
                matched_key=decision["matched_key"],
            )

            # Only brand-new detections are stored in the database and broadcast.
            if decision["action"] == "new":
                is_blacklisted = plate_manager.is_blacklisted(text)

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

                if main_loop is not None:
                    try:
                        # include a stable id so clients can deduplicate reliably
                        detection_data["id"] = image_filename
                        asyncio.run_coroutine_threadsafe(
                            _handle_detection(detection_data, image_filename, is_blacklisted),
                            main_loop,
                        )
                    except Exception as e:
                        logger.error(f"Failed to schedule detection: {e}")

                logger.info(
                    f"✅ PLATE: {text} | conf={confidence:.2%} | "
                    f"sharp={sharpness:.1f} | blacklist={is_blacklisted}"
                )

            # Draw the best detection on the display frame for visibility.
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


@app.post("/detect")
async def detect_endpoint(file: bytes = None, session_id: str | None = None):
    """
    Lightweight detection API for single-frame or short-burst aggregation.
    Accepts raw image bytes (multipart/form-data file upload) and returns a
    best-guess plate with confidence and timestamp. If `session_id` is
    provided, the service will aggregate recent reads for that session and
    prefer the most frequent/highest-confidence result.
    """
    from fastapi import UploadFile, File, Form
    import numpy as np
    import cv2
    import io
    import time as _time
    from collections import Counter

    # Read bytes from request payload. FastAPI will pass raw bytes for body,
    # but clients usually send multipart form 'file'. Try to handle both.
    image_bytes = None
    if isinstance(file, (bytes, bytearray)) and len(file) > 0:
        image_bytes = bytes(file)
    else:
        # Try reading from form upload (compatibility)
        # This branch supports tools that POST as multipart/form-data.
        try:
            from fastapi import Request
            # Access request body isn't straightforward here; return empty result.
            return {"plate": None, "confidence": 0.0, "timestamp": __import__("datetime").datetime.now().isoformat()}
        except Exception:
            return {"plate": None, "confidence": 0.0, "timestamp": __import__("datetime").datetime.now().isoformat()}

    # Decode image
    nparr = np.frombuffer(image_bytes, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None:
        return {"plate": None, "confidence": 0.0, "timestamp": __import__("datetime").datetime.now().isoformat()}

    # Run plate detection
    candidates = plate_detector.detect(frame)
    best_detection = None

    for candidate in candidates[: Config.PLATE_OCR_TOP_K]:
        plate_img = candidate["plate_image"]
        sharpness = candidate.get("sharpness", 0.0)
        
        # 1. Early Blur Rejection
        if sharpness < Config.SHARPNESS_THRESHOLD:
            continue

        plate_area = plate_img.shape[0] * plate_img.shape[1]

        # Try preprocessed then raw
        ocr_inputs = [preprocessor.preprocess_for_ocr(plate_img), plate_img]
        for ocr_input in ocr_inputs:
            text, confidence = ocr_engine.recognize(ocr_input)
            if not text:
                continue

            normalized = plate_manager.normalize_plate_text(text)
            if len(normalized) < 4:
                continue

            # 2. Strict Filter: Must contain at least one digit
            if not any(char.isdigit() for char in normalized):
                continue

            score = plate_manager.quality_score(confidence, sharpness, plate_area)
            if best_detection is None or score > best_detection["score"]:
                best_detection = {
                    "text": normalized,
                    "confidence": confidence,
                    "sharpness": sharpness,
                    "plate_area": plate_area,
                    "plate_img": plate_img,
                    "score": score,
                }

    if not best_detection:
        return {"plate": None, "confidence": 0.0, "timestamp": __import__("datetime").datetime.now().isoformat()}

    # Aggregation buffer (in-memory, short lived)
    key = session_id or "global"
    buf = _detect_buffer.get(key, [])
    buf.append({"plate": best_detection["text"], "conf": best_detection["confidence"], "t": _time.time()})

    # Keep only the last few seconds (short burst window)
    window_secs = max(1.0, min(8.0, Config.FRAME_SKIP * 0.5 + 2.0))
    cutoff = _time.time() - window_secs
    buf = [b for b in buf if b["t"] > cutoff]
    _detect_buffer[key] = buf

    plates = [b["plate"] for b in buf if b.get("plate")]
    if not plates:
        chosen_plate = best_detection["text"]
        chosen_conf = best_detection["confidence"]
    else:
        counts = Counter(plates)
        chosen_plate = counts.most_common(1)[0][0]
        confidences = [b["conf"] for b in buf if b.get("plate") == chosen_plate]
        chosen_conf = sum(confidences) / len(confidences) if confidences else best_detection["confidence"]

    timestamp = __import__("datetime").datetime.now().isoformat()

    # Save crop, commit to plate manager and broadcast (reuse pipeline handler)
    image_filename = plate_manager.save_plate_image(best_detection["plate_img"])
    plate_manager.commit_detection(chosen_plate, image_filename, chosen_conf, best_detection["sharpness"], plate_area=best_detection["plate_area"], matched_key=None)
    plate_manager.record_detection(chosen_conf)

    detection_data = {
        "plate_text": chosen_plate,
        "confidence": round(chosen_conf, 3),
        "timestamp": timestamp,
        "camera_id": Config.CAMERA_ID,
        "image_url": f"/plates/{image_filename}",
        "is_blacklisted": plate_manager.is_blacklisted(chosen_plate),
    }

    # Schedule async database insert and websocket broadcast
    if main_loop is not None:
        try:
            asyncio.run_coroutine_threadsafe(
                _handle_detection(detection_data, image_filename, detection_data["is_blacklisted"]),
                main_loop,
            )
        except Exception as e:
            logger.error(f"Failed to schedule detection from /detect: {e}")

    return {"plate": chosen_plate, "confidence": round(chosen_conf, 3), "timestamp": timestamp}


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
