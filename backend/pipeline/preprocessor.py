"""
Image Preprocessor for License Plate Enhancement.
Applies a series of filters to improve plate visibility for OCR.
"""
import cv2
import numpy as np


class Preprocessor:
    def __init__(
        self,
        bilateral_d=11,
        bilateral_sigma_color=17,
        bilateral_sigma_space=17,
        canny_threshold1=30,
        canny_threshold2=200,
        adaptive_block_size=11,
        adaptive_c=2,
        morph_kernel_size=(3, 3),
        superres_model_path=None,
    ):
        self.bilateral_d = bilateral_d
        self.bilateral_sigma_color = bilateral_sigma_color
        self.bilateral_sigma_space = bilateral_sigma_space
        self.canny_threshold1 = canny_threshold1
        self.canny_threshold2 = canny_threshold2
        self.adaptive_block_size = adaptive_block_size
        self.adaptive_c = adaptive_c
        self.morph_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, morph_kernel_size
        )
        self.superres_model_path = superres_model_path

    def to_grayscale(self, frame):
        """Convert BGR image to grayscale."""
        if len(frame.shape) == 3:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame

    def apply_bilateral_filter(self, gray):
        """Edge-preserving noise reduction."""
        # Gaussian blur is significantly cheaper than bilateral filtering and
        # is enough for the contour-based plate detector.
        return cv2.GaussianBlur(gray, (5, 5), 0)

    def apply_adaptive_threshold(self, gray):
        """Adaptive thresholding for varying lighting conditions."""
        return cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            self.adaptive_block_size,
            self.adaptive_c,
        )

    def apply_canny(self, gray):
        """Canny edge detection."""
        return cv2.Canny(gray, self.canny_threshold1, self.canny_threshold2)

    def apply_morphology(self, binary):
        """Morphological operations to clean edges."""
        # Close small gaps
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, self.morph_kernel, iterations=2)
        # Remove small noise
        opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, self.morph_kernel, iterations=1)
        return opened

    def apply_super_resolution(self, image, scale=2):
        """
        Upscale small plate crops before OCR.

        Tries OpenCV DNN super-resolution when a model is available; otherwise
        falls back to high-quality interpolation plus a mild sharpening pass.
        """
        if image is None or image.size == 0:
            return image

        scale = max(1, int(scale))

        # Prefer OpenCV DNN super-resolution when the contrib module and model
        # are available, but never fail the pipeline if they are missing.
        try:
            import os

            model_path = getattr(self, "superres_model_path", None)
            if model_path and os.path.exists(model_path):
                from cv2 import dnn_superres

                upsampler = dnn_superres.DnnSuperResImpl_create()
                # EDSR is a good default for text-like plate crops.
                upsampler.readModel(model_path)
                upsampler.setModel("edsr", scale)
                return upsampler.upsample(image)
        except Exception:
            # Fall back to interpolation below.
            pass

        interpolation = cv2.INTER_CUBIC if scale <= 2 else cv2.INTER_LANCZOS4
        enlarged = cv2.resize(image, None, fx=scale, fy=scale, interpolation=interpolation)

        # Mild sharpening helps keep character edges crisp after scaling.
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
        return cv2.filter2D(enlarged, -1, kernel)

    def preprocess_for_edges(self, frame):
        """
        Full preprocessing pipeline for edge-based plate detection.
        
        Returns:
            edges: Canny edge image
            gray: grayscale version
        """
        gray = self.to_grayscale(frame)
        blurred = self.apply_bilateral_filter(gray)
        edges = self.apply_canny(blurred)
        edges = self.apply_morphology(edges)
        return edges, gray

    def preprocess_for_ocr(self, plate_image):
        """
        Preprocess a cropped plate image for OCR.
        
        Returns:
            processed: enhanced plate image ready for OCR
        """
        gray = self.to_grayscale(plate_image)

        # Super-resolve crops to ensure sharp character edges for OCR.
        h, w = gray.shape[:2]
        if h < 150 or w < 300:
            gray = self.apply_super_resolution(gray, scale=2)

        # Resize to improve OCR (target height ~96px)
        h, w = gray.shape[:2]
        if h < 96:
            scale = 96.0 / max(h, 1)
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        # Keep OCR preprocessing lightweight for real-time throughput.
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        enhanced = cv2.equalizeHist(blurred)

        # Otsu threshold works well enough for most plate crops and is cheaper
        # than adaptive thresholding.
        _, thresh = cv2.threshold(
            enhanced,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU,
        )

        # Add morphological operations (erosion and dilation)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        thresh = cv2.erode(thresh, kernel, iterations=1)
        thresh = cv2.dilate(thresh, kernel, iterations=1)

        # Add a white border (padding) which significantly improves Tesseract accuracy
        thresh = cv2.copyMakeBorder(thresh, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=[255, 255, 255])

        return thresh

    @staticmethod
    def compute_sharpness(image):
        """
        Compute image sharpness using Laplacian variance.
        Higher value = sharper image.
        """
        gray = image if len(image.shape) == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return cv2.Laplacian(gray, cv2.CV_64F).var()
