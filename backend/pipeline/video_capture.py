"""
Threaded Video Capture
Runs cv2.VideoCapture in a dedicated daemon thread.
Pushes latest frames to a bounded queue for the processing pipeline.
"""
import cv2
import threading
import queue
import time
import logging

logger = logging.getLogger(__name__)


class VideoCapture:
    def __init__(self, source, max_queue_size=2):
        self.source = source
        self.queue = queue.Queue(maxsize=max_queue_size)
        self.cap = None
        self.running = False
        self.thread = None
        self.fps = 0
        self.frame_width = 0
        self.frame_height = 0
        self._lock = threading.Lock()
        self._reconnect_delay = 2.0

    def start(self):
        """Start the capture thread."""
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        logger.info(f"Video capture started: {self.source}")

    def stop(self):
        """Stop the capture thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5.0)
        if self.cap:
            self.cap.release()
        logger.info("Video capture stopped")

    def _open_source(self):
        """Open video source with retry logic."""
        if self.cap:
            self.cap.release()

        # Try as integer (webcam index) first
        try:
            source = int(self.source)
        except (ValueError, TypeError):
            source = self.source

        self.cap = cv2.VideoCapture(source)

        if self.cap.isOpened():
            self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
            self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            logger.info(
                f"Source opened: {self.frame_width}x{self.frame_height} @ {self.fps:.1f}fps"
            )
            return True
        else:
            logger.warning(f"Failed to open source: {self.source}")
            return False

    def _capture_loop(self):
        """Main capture loop running in background thread."""
        while self.running:
            if not self.cap or not self.cap.isOpened():
                if not self._open_source():
                    logger.info(f"Retrying in {self._reconnect_delay}s...")
                    time.sleep(self._reconnect_delay)
                    continue

            ret, frame = self.cap.read()

            if not ret:
                # End of video file — loop back to start
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                logger.info("Video ended, looping...")
                continue

            # Drop old frames to keep only the latest
            try:
                self.queue.put_nowait(frame)
            except queue.Full:
                try:
                    self.queue.get_nowait()
                except queue.Empty:
                    pass
                self.queue.put_nowait(frame)

            # Match source FPS roughly
            if self.fps > 0:
                time.sleep(1.0 / self.fps)

    def get_frame(self):
        """Get the latest frame (non-blocking). Returns None if no frame available."""
        try:
            return self.queue.get_nowait()
        except queue.Empty:
            return None

    def get_frame_blocking(self, timeout=1.0):
        """Get a frame with blocking wait."""
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None

    @property
    def is_opened(self):
        return self.cap is not None and self.cap.isOpened()

    @property
    def resolution(self):
        return (self.frame_width, self.frame_height)
