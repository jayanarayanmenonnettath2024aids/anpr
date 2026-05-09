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

logger = logging.getLogger(__name__)


class PlateManager:
    def __init__(self, dedup_window=30, blacklist=None, plates_dir="plates"):
        self.dedup_window = dedup_window
        self.blacklist = set(blacklist or [])
        self.plates_dir = plates_dir
        self._recent_plates = OrderedDict()  # plate_text -> last_seen_time
        self._plate_counter = 0
        self._detections_today = 0
        self._detection_times = []  # timestamps for plates/min calc
        self._total_confidence = 0.0
        self._confidence_count = 0

        os.makedirs(plates_dir, exist_ok=True)

    def is_duplicate(self, plate_text):
        """
        Check if this plate was recently detected.
        Returns True if duplicate (should be suppressed).
        """
        if not plate_text:
            return True

        current_time = time.time()

        # Clean expired entries
        expired = [
            k for k, t in self._recent_plates.items()
            if current_time - t > self.dedup_window
        ]
        for k in expired:
            del self._recent_plates[k]

        # Check if already seen
        normalized = plate_text.replace(" ", "").upper()
        if normalized in self._recent_plates:
            return True

        # Mark as seen
        self._recent_plates[normalized] = current_time
        return False

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

    def save_plate_image(self, plate_image):
        """
        Save cropped plate image to disk.
        Returns the filename.
        """
        import cv2

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
