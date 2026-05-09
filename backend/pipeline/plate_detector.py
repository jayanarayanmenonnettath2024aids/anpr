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
            edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
        )

        # Sort by area (largest first) and take top candidates
        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        contours = contours[: self.max_candidates * 3]  # pre-filter

        candidates = []

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.min_area or area > self.max_area:
                continue

            # Approximate contour to polygon
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, self.approx_epsilon * peri, True)

            # License plates are rectangles (4 corners)
            if len(approx) == 4:
                x, y, w, h = cv2.boundingRect(approx)

                # Check aspect ratio
                if h == 0:
                    continue
                aspect_ratio = w / h

                if self.min_aspect_ratio <= aspect_ratio <= self.max_aspect_ratio:
                    # Crop the plate region from original frame
                    plate_img = frame[y: y + h, x: x + w]

                    if plate_img.size == 0:
                        continue

                    # Check sharpness
                    sharpness = Preprocessor.compute_sharpness(plate_img)

                    candidates.append({
                        "plate_image": plate_img,
                        "bbox": (x, y, w, h),
                        "sharpness": sharpness,
                        "contour": approx,
                        "aspect_ratio": aspect_ratio,
                        "area": area,
                    })

            # Also try rotated rectangle for angled plates
            elif len(approx) >= 4:
                rect = cv2.minAreaRect(contour)
                (cx, cy), (w_r, h_r), angle = rect

                if w_r == 0 or h_r == 0:
                    continue

                # Ensure width > height
                if w_r < h_r:
                    w_r, h_r = h_r, w_r
                    angle += 90

                aspect_ratio = w_r / h_r
                rect_area = w_r * h_r

                if (
                    self.min_area <= rect_area <= self.max_area
                    and self.min_aspect_ratio <= aspect_ratio <= self.max_aspect_ratio
                    and abs(angle) < 30  # Not too rotated
                ):
                    # Get bounding rect for crop
                    x, y, w, h = cv2.boundingRect(contour)
                    plate_img = frame[y: y + h, x: x + w]

                    if plate_img.size == 0:
                        continue

                    sharpness = Preprocessor.compute_sharpness(plate_img)

                    candidates.append({
                        "plate_image": plate_img,
                        "bbox": (x, y, w, h),
                        "sharpness": sharpness,
                        "contour": approx,
                        "aspect_ratio": aspect_ratio,
                        "area": rect_area,
                    })

        # Sort by sharpness (sharpest first) and limit
        candidates.sort(key=lambda c: c["sharpness"], reverse=True)
        candidates = candidates[: self.max_candidates]

        # Filter by sharpness threshold
        candidates = [
            c for c in candidates if c["sharpness"] >= self.sharpness_threshold
        ]

        if candidates:
            logger.debug(
                f"Found {len(candidates)} plate candidate(s), "
                f"best sharpness: {candidates[0]['sharpness']:.1f}"
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
        vehicle_roi = frame[vy: vy + vh, vx: vx + vw]

        if vehicle_roi.size == 0:
            return []

        candidates = self.detect(vehicle_roi)

        # Adjust coordinates to global frame
        for c in candidates:
            bx, by, bw, bh = c["bbox"]
            c["bbox"] = (bx + vx, by + vy, bw, bh)

        return candidates
