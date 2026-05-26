"""
License Plate Detector using Contour Analysis.
Finds rectangular regions likely to be license plates based on
shape, aspect ratio, and area — no deep learning required.
"""
import cv2
import numpy as np
import logging

from .preprocessor import Preprocessor

logger = logging.getLogger(__name__)


class PlateDetector:
    def __init__(
        self,
        min_aspect_ratio=1.5,
        max_aspect_ratio=6.0,
        min_area=800,
        max_area=50000,
        approx_epsilon=0.02,
        max_candidates=10,
        sharpness_threshold=50.0,
    ):
        self.min_aspect_ratio = min_aspect_ratio
        self.max_aspect_ratio = max_aspect_ratio
        self.min_area = min_area
        self.max_area = max_area
        self.approx_epsilon = approx_epsilon
        self.max_candidates = max_candidates
        self.sharpness_threshold = sharpness_threshold
        self.preprocessor = Preprocessor()

    def detect(self, frame):
        """
        Detect license plate regions in the given frame.
        
        Args:
            frame: BGR image (vehicle region preferred)
            
        Returns:
            list of dict: [{
                'plate_image': cropped plate BGR image,
                'bbox': (x, y, w, h),
                'sharpness': float,
                'contour': np.array
            }]
        """
        edges, gray = self.preprocessor.preprocess_for_edges(frame)

        # Find contours on edge image
        contours, _ = cv2.findContours(
            edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # Sort by area (largest first) and take top candidates
        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        contours = contours[: self.max_candidates * 3]  # pre-filter

        candidates = []

        frame_area = frame.shape[0] * frame.shape[1]
        ideal_aspect_ratio = 4.0

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.min_area or area > self.max_area:
                continue

            # Get bounding box
            x, y, w, h = cv2.boundingRect(contour)

            # Check aspect ratio
            if h == 0:
                continue
            aspect_ratio = w / h

            if self.min_aspect_ratio <= aspect_ratio <= self.max_aspect_ratio:
                rectangularity = area / float(max(w * h, 1))
                aspect_score = max(0.0, 1.0 - (abs(aspect_ratio - ideal_aspect_ratio) / ideal_aspect_ratio))
                size_score = min((w * h) / float(max(frame_area * 0.08, 1.0)), 1.0)
                contour_area_ratio = area / float(max(frame_area, 1))

                # Reject obvious non-plate textures such as road surface or large
                # body panels by requiring a compact contour with meaningful fill.
                if rectangularity < 0.38 or contour_area_ratio < 0.0008:
                    continue

                # Add a light padding so the crop keeps the full plate while
                # avoiding too much of the car body or surrounding scene.
                p_x = max(8, int(w * 0.18))
                p_y = max(6, int(h * 0.22))
                cx1 = max(0, x - p_x)
                cy1 = max(0, y - p_y)
                cx2 = min(frame.shape[1], x + w + p_x)
                cy2 = min(frame.shape[0], y + h + p_y)
                
                # Crop the plate region from original frame
                plate_img = frame[cy1:cy2, cx1:cx2]

                if plate_img.size == 0:
                    continue

                # Check sharpness
                sharpness = Preprocessor.compute_sharpness(plate_img)

                candidates.append({
                    "plate_image": plate_img,
                    "bbox": (x, y, w, h),
                    "sharpness": sharpness,
                    "contour": contour,
                    "aspect_ratio": aspect_ratio,
                    "area": area,
                    "rectangularity": rectangularity,
                    "aspect_score": aspect_score,
                    "size_score": size_score,
                    "contour_area_ratio": contour_area_ratio,
                })

        # Sort by plate-likeness first, then sharpness.
        for candidate in candidates:
            candidate["score"] = (
                candidate["sharpness"] * 0.45
                + candidate["rectangularity"] * 60.0
                + candidate["aspect_score"] * 35.0
                + candidate["size_score"] * 10.0
                + candidate["contour_area_ratio"] * 4000.0
            )

        candidates.sort(key=lambda c: (c["score"], c["sharpness"]), reverse=True)

        # Suppress highly overlapping fragments so the same plate is not
        # emitted multiple times from partial contours.
        selected = []
        for candidate in candidates:
            cx, cy, cw, ch = candidate["bbox"]
            candidate_area = cw * ch
            overlapped = False

            for picked in selected:
                px, py, pw, ph = picked["bbox"]
                inter_x1 = max(cx, px)
                inter_y1 = max(cy, py)
                inter_x2 = min(cx + cw, px + pw)
                inter_y2 = min(cy + ch, py + ph)

                if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
                    continue

                intersection = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
                union = candidate_area + (pw * ph) - intersection
                iou = intersection / float(max(union, 1))

                if iou >= 0.45:
                    overlapped = True
                    break

            if not overlapped:
                selected.append(candidate)

            if len(selected) >= self.max_candidates:
                break

        candidates = selected

        # Filter by sharpness threshold
        candidates = [
            c for c in candidates if c["sharpness"] >= self.sharpness_threshold
        ]

        if candidates:
            logger.debug(
                f"Found {len(candidates)} plate candidate(s), "
                f"best score: {candidates[0]['score']:.1f}"
            )

        return candidates

    def detect_in_vehicle_region(self, frame, vehicle_bbox):
        """
        Detect plates within a specific vehicle bounding box.
        
        Args:
            frame: full frame
            vehicle_bbox: (x, y, w, h) of the vehicle
            
        Returns:
            list of plate candidates with global coordinates
        """
        vx, vy, vw, vh = vehicle_bbox
        # Use only the lower-middle of the vehicle body. This avoids ground,
        # roofline, and neighboring car fragments that often get picked up by
        # the motion box but are not part of the license plate area.
        sx1 = vx + int(vw * 0.08)
        sx2 = vx + int(vw * 0.92)
        sy1 = vy + int(vh * 0.28)
        sy2 = vy + int(vh * 0.88)

        vehicle_roi = frame[sy1:sy2, sx1:sx2]

        if vehicle_roi.size == 0:
            return []

        candidates = self.detect(vehicle_roi)

        # Adjust coordinates to global frame
        for c in candidates:
            bx, by, bw, bh = c["bbox"]
            c["bbox"] = (bx + sx1, by + sy1, bw, bh)

        return candidates
