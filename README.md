# ANPR Command Center

Lightweight Real-Time Automatic Number Plate Recognition System — **No YOLO / No Deep Learning Object Detection**.

## Architecture

```
Camera/Video → ROI Crop → Motion Detection (MOG2) → Contour Detection
    → Trigger Zone → Edge Detection → Plate Rectangle Detection
    → PaddleOCR → WebSocket → React Dashboard
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Video Processing | OpenCV (contour-based) |
| Motion Detection | MOG2 Background Subtraction |
| OCR | PaddleOCR (primary) / Tesseract (fallback) |
| Backend | FastAPI + WebSocket |
| Frontend | React + Vite |
| Database | SQLite (async) |
| Deployment | Docker Compose |

## Quick Start

### 1. Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
# Place your video file as video.mp4 in the backend directory
python main.py
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

### 3. Docker (Production)

```bash
docker-compose up --build
```

## Configuration

All parameters are in `backend/config.py`:

- **Video source**: file path or RTSP URL
- **ROI coordinates**: crop to road area only
- **Motion thresholds**: sensitivity tuning
- **Trigger zone**: virtual checkpoint line position
- **Plate detection**: aspect ratio, area bounds
- **OCR engine**: paddleocr or tesseract
- **Frame skip**: process every Nth frame
- **Blacklist**: plates to alert on

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| WS | `/ws/detections` | Real-time plate detection events (JSON) |
| WS | `/ws/live-feed` | Live annotated video stream (binary JPEG) |
| GET | `/api/history` | Paginated plate history |
| GET | `/api/history/export` | CSV export |
| GET | `/api/stats` | Pipeline statistics |
| GET/POST/DELETE | `/api/blacklist` | Blacklist management |
| GET | `/api/config` | Current configuration |

## Performance

- **Latency**: 10-40ms per frame (no neural network inference)
- **Frame processing**: configurable skip rate
- **ROI cropping**: reduces processed pixels by 60-80%
- **Trigger zone**: avoids continuous OCR processing
