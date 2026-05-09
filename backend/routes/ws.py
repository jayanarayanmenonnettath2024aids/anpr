"""
WebSocket Endpoints for real-time streaming.
- /ws/detections  → JSON plate detection events
- /ws/live-feed   → Binary JPEG video frames
"""
import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


def get_stream_manager():
    """Get the global stream manager (set in main.py)."""
    from main import stream_manager
    return stream_manager


@router.websocket("/ws/detections")
async def ws_detections(websocket: WebSocket):
    """
    WebSocket endpoint for plate detection events.
    Sends JSON messages when plates are detected:
    {
        "plate_text": "KA01AB1234",
        "confidence": 0.92,
        "timestamp": "2026-05-09T13:04:27",
        "camera_id": "CAM-01",
        "image_url": "/plates/plate_xxx.jpg",
        "is_blacklisted": false
    }
    """
    sm = get_stream_manager()
    await sm.connect_detection(websocket)

    try:
        while True:
            # Keep connection alive — listen for any client messages (ping/pong)
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send a ping to keep alive
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Detection WS error: {e}")
    finally:
        sm.disconnect_detection(websocket)


@router.websocket("/ws/live-feed")
async def ws_live_feed(websocket: WebSocket):
    """
    WebSocket endpoint for live video feed.
    Sends binary JPEG frames for real-time video display.
    """
    sm = get_stream_manager()
    await sm.connect_feed(websocket)

    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                try:
                    await websocket.send_bytes(b"ping")
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Feed WS error: {e}")
    finally:
        sm.disconnect_feed(websocket)
