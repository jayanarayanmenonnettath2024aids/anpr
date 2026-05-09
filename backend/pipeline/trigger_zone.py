"""
Trigger Zone Logic.
Detects when a moving vehicle's centroid crosses a virtual checkpoint line.
Prevents duplicate triggering with cooldown tracking.
"""
import time
import logging

logger = logging.getLogger(__name__)


class TriggerZone:
    def __init__(self, line_y=400, tolerance=40, cooldown=2.0):
        """
        Args:
            line_y: Y position of the trigger line within the ROI
            tolerance: pixel tolerance around the line
            cooldown: seconds before the same region can trigger again
        """
        self.line_y = line_y
        self.tolerance = tolerance
        self.cooldown = cooldown
        # Tracks recently triggered regions: { region_key: last_trigger_time }
        self._triggered = {}

    def check(self, bounding_boxes):
        """
        Check which bounding boxes cross the trigger line.
        
        Args:
            bounding_boxes: list of (x, y, w, h)
            
        Returns:
            list of (x, y, w, h) boxes that triggered (new crossings only)
        """
        triggered = []
        current_time = time.time()

        # Clean up expired entries
        expired = [
            k for k, t in self._triggered.items()
            if current_time - t > self.cooldown
        ]
        for k in expired:
            del self._triggered[k]

        for (x, y, w, h) in bounding_boxes:
            # Centroid of the bounding box
            cx = x + w // 2
            cy = y + h // 2

            # Check if centroid is near the trigger line
            if abs(cy - self.line_y) <= self.tolerance:
                # Create a region key based on horizontal position (binned to 50px)
                region_key = cx // 50

                if region_key not in self._triggered:
                    self._triggered[region_key] = current_time
                    triggered.append((x, y, w, h))
                    logger.debug(
                        f"Trigger! Vehicle at ({cx}, {cy}), region={region_key}"
                    )

        return triggered

    def reset(self):
        """Clear all tracked triggers."""
        self._triggered.clear()

    @property
    def active_tracks(self):
        return len(self._triggered)
