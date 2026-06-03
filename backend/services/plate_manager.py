"""
Plate Manager Service.
Handles deduplication, blacklist checking, history storage, and search.
"""
import time
import os
import csv
import io
import logging
from datetime import datetime
from collections import OrderedDict
import threading
import re

logger = logging.getLogger(__name__)
from difflib import SequenceMatcher


class PlateManager:
    def __init__(self, dedup_window=30, blacklist=None, plates_dir="plates"):
        self.dedup_window = dedup_window
        self.similarity_threshold = 0.86
        self.blacklist = set(blacklist or [])
        self.plates_dir = plates_dir
        self._recent_plates = OrderedDict()  # normalized_plate -> record
        self._lock = threading.Lock()
        self._plate_counter = 0
        self._detections_today = 0
        self._detection_times = []  # timestamps for plates/min calc
        self._total_confidence = 0.0
        self._confidence_count = 0

        os.makedirs(plates_dir, exist_ok=True)

    @staticmethod
    def normalize_plate_text(plate_text):
        if not plate_text:
            return ""
        return re.sub(r"[^A-Z0-9]", "", plate_text.upper().replace(" ", ""))

    @staticmethod
    def is_valid_indian_plate(text):
        clean = PlateManager.normalize_plate_text(text)
        pattern = r"^[A-Z]{2}\d{1,2}[A-Z]{1,3}\d{4}$"
        return bool(re.match(pattern, clean))

    @staticmethod
    def fuzzy_normalize(text):
        if not text: return ""
        text = PlateManager.normalize_plate_text(text)
        # Map visually similar characters to a single representation for deduplication
        cmap = {
            'O': '0', 'Q': '0', 'D': '0',
            'I': '1', 'L': '1',
            'Z': '2', 'S': '5', 'B': '8', 'G': '6', 'A': '4'
        }
        return "".join(cmap.get(c, c) for c in text)

    @staticmethod
    def same_plate(a, b):
        a_norm = PlateManager.normalize_plate_text(a)
        b_norm = PlateManager.normalize_plate_text(b)

        if not a_norm or not b_norm:
            return False

        if a_norm == b_norm:
            return True

        # Use fuzzy normalized strings to catch heavy OCR mangling (O vs 0, Z vs 2)
        a_fuzz = PlateManager.fuzzy_normalize(a_norm)
        b_fuzz = PlateManager.fuzzy_normalize(b_norm)

        # Treat partial OCR fragments as the same detection when one string is
        # clearly contained inside the other.
        short, long = sorted((a_fuzz, b_fuzz), key=len)
        if len(short) >= 5 and short in long:
            return True

        # Check if they share a significant common substring (at least 5 chars)
        matcher = SequenceMatcher(None, a_fuzz, b_fuzz)
        match = matcher.find_longest_match(0, len(a_fuzz), 0, len(b_fuzz))
        if match.size >= 5:
            return True

        # Many Indian plate OCR errors drop the state code but preserve the rest.
        if len(a_fuzz) >= 4 and len(b_fuzz) >= 4 and a_fuzz[-4:] == b_fuzz[-4:]:
            return True

        return matcher.ratio() >= 0.65

    @staticmethod
    def similarity(a, b):
        return SequenceMatcher(None, a, b).ratio()

    @staticmethod
    def quality_score(confidence, sharpness, plate_area=0):
        # Confidence carries the most weight, but a sharper/larger crop can
        # replace an earlier fuzzy one for the same plate.
        return (
            confidence * 100.0
            + min(sharpness, 250.0) * 0.25
            + min(plate_area / 1000.0, 10.0)
        )

    def _purge_expired_locked(self, current_time):
        expired = [
            k for k, record in self._recent_plates.items()
            if current_time - record["last_seen"] > self.dedup_window
        ]
        for key in expired:
            del self._recent_plates[key]

    def evaluate_detection(self, plate_text, confidence, sharpness, plate_area=0):
        """
        Decide whether a detection is new, a duplicate, or a better version of
        a similar recent plate.

        Returns a dict with:
        - action: "new", "replace", or "skip"
        - matched_key: matched recent plate key if any
        - replace_filename: filename to overwrite for better duplicates
        - score: current quality score
        """
        normalized = self.normalize_plate_text(plate_text)
        if not normalized:
            return {"action": "skip", "matched_key": None, "replace_filename": None, "score": 0.0}

        current_time = time.time()
        score = self.quality_score(confidence, sharpness, plate_area)

        with self._lock:
            self._purge_expired_locked(current_time)

            matched_key = None
            matched_ratio = 0.0
            for key in self._recent_plates.keys():
                ratio = 1.0 if key == normalized else self.similarity(normalized, key)
                if self.same_plate(normalized, key) and ratio > matched_ratio:
                    matched_key = key
                    matched_ratio = ratio

            if matched_key is None:
                return {"action": "new", "matched_key": normalized, "replace_filename": None, "score": score}

            record = self._recent_plates[matched_key]
            record["last_seen"] = current_time
            self._recent_plates.move_to_end(matched_key)

            if score > record["score"]:
                return {
                    "action": "replace",
                    "matched_key": matched_key,
                    "replace_filename": record["image_filename"],
                    "score": score,
                }

            return {
                "action": "skip",
                "matched_key": matched_key,
                "replace_filename": record["image_filename"],
                "score": record["score"],
            }

    def commit_detection(self, plate_text, image_filename, confidence, sharpness, plate_area=0, matched_key=None):
        """Persist/update the in-memory recent detection cache."""
        normalized = matched_key or self.normalize_plate_text(plate_text)
        if not normalized:
            return

        current_time = time.time()
        score = self.quality_score(confidence, sharpness, plate_area)

        with self._lock:
            self._purge_expired_locked(current_time)
            self._recent_plates[normalized] = {
                "plate_text": plate_text,
                "image_filename": image_filename,
                "confidence": confidence,
                "sharpness": sharpness,
                "score": score,
                "last_seen": current_time,
            }
            self._recent_plates.move_to_end(normalized)

    def is_blacklisted(self, plate_text):
        """Check if plate is in the blacklist."""
        if not plate_text:
            return False
        normalized = plate_text.replace(" ", "").upper()
        return normalized in self.blacklist

    def add_to_blacklist(self, plate_text):
        """Add a plate to the blacklist."""
        normalized = plate_text.replace(" ", "").upper()
        self.blacklist.add(normalized)

    def remove_from_blacklist(self, plate_text):
        """Remove a plate from the blacklist."""
        normalized = plate_text.replace(" ", "").upper()
        self.blacklist.discard(normalized)

    def save_plate_image(self, plate_image, filename=None):
        """
        Save cropped plate image to disk.
        Returns the filename.
        """
        import cv2

        if filename is None:
            self._plate_counter += 1
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"plate_{timestamp}_{self._plate_counter:04d}.jpg"
        filepath = os.path.join(self.plates_dir, filename)

        cv2.imwrite(filepath, plate_image)
        logger.info(f"Saved plate image: {filename}")

        return filename

    def record_detection(self, confidence):
        """Record stats for a detection."""
        self._detections_today += 1
        self._total_confidence += confidence
        self._confidence_count += 1
        self._detection_times.append(time.time())

        # Keep only last 5 minutes of timestamps
        cutoff = time.time() - 300
        self._detection_times = [t for t in self._detection_times if t > cutoff]

    def get_stats(self):
        """Get current detection statistics."""
        current_time = time.time()

        # Plates per minute (last 60 seconds)
        one_min_ago = current_time - 60
        recent = [t for t in self._detection_times if t > one_min_ago]
        plates_per_min = len(recent)

        avg_confidence = (
            self._total_confidence / self._confidence_count
            if self._confidence_count > 0
            else 0.0
        )

        return {
            "total_today": self._detections_today,
            "plates_per_minute": plates_per_min,
            "avg_confidence": round(avg_confidence, 3),
            "active_blacklist": len(self.blacklist),
        }

    @staticmethod
    def export_csv(detections):
        """Export detections list to CSV string."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Plate Number", "Confidence", "Camera", "Timestamp", "Image"])

        for d in detections:
            writer.writerow([
                d.get("id", ""),
                d.get("plate_text", ""),
                d.get("confidence", ""),
                d.get("camera_id", ""),
                d.get("timestamp", ""),
                d.get("image_path", ""),
            ])

        return output.getvalue()
