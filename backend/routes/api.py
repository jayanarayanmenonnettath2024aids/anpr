"""
REST API Endpoints.
History, search, export, blacklist, stats, and config.
"""
import logging
from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from typing import Optional

from models.schemas import (
    PlateHistoryResponse,
    StatsResponse,
    BlacklistEntry,
    BlacklistRecord,
    ConfigResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["ANPR API"])


def get_db():
    from main import database
    return database


def get_plate_manager():
    from main import plate_manager
    return plate_manager


def get_stream_manager():
    from main import stream_manager
    return stream_manager


@router.get("/history", response_model=PlateHistoryResponse)
async def get_history(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Get paginated plate detection history."""
    db = get_db()
    result = await db.get_history(
        page=page, per_page=per_page, search=search,
        date_from=date_from, date_to=date_to
    )
    return result


@router.get("/history/export")
async def export_history():
    """Export all detections as CSV."""
    db = get_db()
    pm = get_plate_manager()
    detections = await db.get_all_detections()
    csv_content = pm.export_csv(detections)
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=anpr_export.csv"},
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get current detection statistics."""
    pm = get_plate_manager()
    sm = get_stream_manager()
    stats = pm.get_stats()
    db_stats = await get_db().get_today_stats()

    return StatsResponse(
        total_today=db_stats.get("total_today", stats["total_today"]),
        plates_per_minute=stats["plates_per_minute"],
        avg_confidence=db_stats.get("avg_confidence", stats["avg_confidence"]),
        active_blacklist=stats["active_blacklist"],
        pipeline_status="active",
        connected_clients=sm.detection_client_count + sm.feed_client_count,
    )


@router.get("/blacklist", response_model=list[BlacklistRecord])
async def get_blacklist():
    """Get all blacklisted plates."""
    db = get_db()
    return await db.get_blacklist()


@router.post("/blacklist")
async def add_blacklist(entry: BlacklistEntry):
    """Add a plate to the blacklist."""
    db = get_db()
    pm = get_plate_manager()
    success = await db.add_blacklist(entry.plate_text, entry.description)
    if success:
        pm.add_to_blacklist(entry.plate_text)
    return {"success": success, "plate_text": entry.plate_text.upper()}


@router.delete("/blacklist/{plate_text}")
async def remove_blacklist(plate_text: str):
    """Remove a plate from the blacklist."""
    db = get_db()
    pm = get_plate_manager()
    await db.remove_blacklist(plate_text)
    pm.remove_from_blacklist(plate_text)
    return {"success": True, "plate_text": plate_text.upper()}


@router.get("/config", response_model=ConfigResponse)
async def get_config():
    """Get current pipeline configuration."""
    from config import Config
    return ConfigResponse(
        video_source=Config.VIDEO_SOURCE,
        camera_id=Config.CAMERA_ID,
        roi_enabled=Config.ROI_ENABLED,
        roi_coords={
            "y1": Config.ROI_Y1, "y2": Config.ROI_Y2,
            "x1": Config.ROI_X1, "x2": Config.ROI_X2,
        },
        frame_skip=Config.FRAME_SKIP,
        trigger_zone_y=Config.TRIGGER_LINE_Y,
        ocr_engine=Config.OCR_ENGINE,
        dedup_window=Config.DEDUP_WINDOW_SECONDS,
    )
