"""
Motion Detection using MOG2 Background Subtraction.
Detects moving objects and returns their bounding boxes.
"""
import cv2
import logging

logger = logging.getLogger(__name__)


class MotionDetector:
    def __init__(self, history=500, var_threshold=50, detect_shadows=True, min_contour_area=5000):
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=history,
            varThreshold=var_threshold,
            detectShadows=detect_shadows,
        )
        self.min_contour_area = min_contour_area
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    def detect(self, frame):
        """
        Detect moving objects in the frame.
        
        Args:
            frame: BGR image (ROI-cropped preferred)
            
        Returns:
            list of (x, y, w, h) bounding boxes for moving objects,
            foreground mask for visualization
        """
        # Apply background subtraction
        fg_mask = self.bg_subtractor.apply(frame)

        # Remove shadows (shadows are marked as 127 in MOG2)
        _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)

        # Morphological operations to remove noise and fill gaps
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, self.kernel, iterations=1)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, self.kernel, iterations=1)
        fg_mask = cv2.dilate(fg_mask, self.kernel, iterations=1)

        # Find contours
        contours, _ = cv2.findContours(
            fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # Filter by area
        bounding_boxes = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= self.min_contour_area:
                x, y, w, h = cv2.boundingRect(contour)
                bounding_boxes.append((x, y, w, h))

        return bounding_boxes, fg_mask

    def reset(self):
        """Reset the background model."""
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=50, detectShadows=True
        )
