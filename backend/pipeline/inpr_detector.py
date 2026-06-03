"""
Optional Detectron2-based detector adapter for the INPR model.

This wraps the external INPR plate detector as a drop-in backend for the
existing pipeline. It detects plates only; OCR is still handled separately.
"""
import logging
import os
import urllib.request

import cv2

from .preprocessor import Preprocessor

logger = logging.getLogger(__name__)


class INPRPlateDetector:
    MODEL_URL = "https://github.com/patrickn699/INPR/releases/download/inpr_v1.0/model_final.pth"
    CONFIG_URL = "https://github.com/patrickn699/INPR/releases/download/inpr_v1.0/config.yaml"

    def __init__(self, model_dir, score_threshold=0.7):
        self.model_dir = model_dir
        self.score_threshold = score_threshold
        self.preprocessor = Preprocessor()
        self._ready = False
        self._predictor = None
        self._init_detector()

    @property
    def available(self):
        return self._ready

    def _ensure_model_files(self):
        os.makedirs(self.model_dir, exist_ok=True)
        weights_path = os.path.join(self.model_dir, "model_final.pth")
        config_path = os.path.join(self.model_dir, "config.yaml")

        if not os.path.isfile(weights_path):
            logger.info("Downloading INPR detector weights...")
            urllib.request.urlretrieve(self.MODEL_URL, weights_path)

        if not os.path.isfile(config_path):
            logger.info("Downloading INPR detector config...")
            urllib.request.urlretrieve(self.CONFIG_URL, config_path)

        return weights_path, config_path

    def _init_detector(self):
        try:
            from detectron2.config import get_cfg
            from detectron2.engine import DefaultPredictor
        except Exception as exc:
            logger.warning(f"INPR detector unavailable: detectron2 import failed ({exc})")
            return

        try:
            weights_path, config_path = self._ensure_model_files()

            cfg = get_cfg()
            cfg.merge_from_file(config_path)
            cfg.MODEL.WEIGHTS = weights_path
            cfg.MODEL.ROI_HEADS.SCORE_THRESH_TEST = self.score_threshold
            cfg.MODEL.DEVICE = "cpu"

            self._predictor = DefaultPredictor(cfg)
            self._ready = True
            logger.info("INPR detector initialized successfully")
        except Exception as exc:
            logger.warning(f"INPR detector init failed, falling back to contour detector: {exc}")
            self._predictor = None
            self._ready = False

    def detect(self, frame):
        if not self._ready or self._predictor is None:
            return []

        if frame is None or frame.size == 0:
            return []

        # Detectron2 expects RGB input.
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        outputs = self._predictor(rgb)
        instances = outputs.get("instances")
        if instances is None or len(instances) == 0:
            return []

        boxes = instances.pred_boxes.tensor.cpu().numpy()
        scores = instances.scores.cpu().numpy() if instances.has("scores") else [1.0] * len(boxes)

        candidates = []
        frame_area = frame.shape[0] * frame.shape[1]

        for box, score in zip(boxes, scores):
            x1, y1, x2, y2 = [int(v) for v in box]
            pad_x = max(6, int((x2 - x1) * 0.12))
            pad_y = max(4, int((y2 - y1) * 0.18))
            cx1 = max(0, x1 - pad_x)
            cy1 = max(0, y1 - pad_y)
            cx2 = min(frame.shape[1], x2 + pad_x)
            cy2 = min(frame.shape[0], y2 + pad_y)

            plate_img = frame[cy1:cy2, cx1:cx2]
            if plate_img.size == 0:
                continue

            sharpness = Preprocessor.compute_sharpness(plate_img)
            area = max(1, (x2 - x1) * (y2 - y1))
            plate_area = plate_img.shape[0] * plate_img.shape[1]
            aspect_ratio = (x2 - x1) / max((y2 - y1), 1)

            candidates.append({
                "plate_image": plate_img,
                "bbox": (x1, y1, x2 - x1, y2 - y1),
                "sharpness": sharpness,
                "contour": None,
                "aspect_ratio": aspect_ratio,
                "area": area,
                "rectangularity": 1.0,
                "aspect_score": min(1.0, max(0.0, score)),
                "size_score": min(1.0, plate_area / float(max(frame_area * 0.05, 1.0))),
                "contour_area_ratio": area / float(max(frame_area, 1)),
                "score": float(score) * 100.0 + sharpness * 0.25,
            })

        candidates.sort(key=lambda c: (c["score"], c["sharpness"]), reverse=True)
        return candidates

    def detect_in_vehicle_region(self, frame, vehicle_bbox):
        vx, vy, vw, vh = vehicle_bbox
        sx1 = vx + int(vw * 0.05)
        sx2 = vx + int(vw * 0.95)
        sy1 = vy + int(vh * 0.25)
        sy2 = vy + int(vh * 0.90)

        vehicle_roi = frame[sy1:sy2, sx1:sx2]
        if vehicle_roi.size == 0:
            return []

        candidates = self.detect(vehicle_roi)
        for c in candidates:
            bx, by, bw, bh = c["bbox"]
            c["bbox"] = (bx + sx1, by + sy1, bw, bh)
        return candidates