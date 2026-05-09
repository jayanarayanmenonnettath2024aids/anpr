"""
Pydantic Models / Schemas for the ANPR API.
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class PlateDetection(BaseModel):
    plate_text: str
    confidence: float
    timestamp: str
    camera_id: str
    image_url: str
    is_blacklisted: bool = False


class PlateRecord(BaseModel):
    id: int
    plate_text: str
    confidence: float
    timestamp: str
    camera_id: str
    image_path: Optional[str] = None
    is_blacklisted: bool = False


class PlateHistoryResponse(BaseModel):
    records: List[PlateRecord]
    total: int
    page: int
    per_page: int
    total_pages: int


class StatsResponse(BaseModel):
    total_today: int
    plates_per_minute: int
    avg_confidence: float
    active_blacklist: int
    pipeline_status: str = "active"
    connected_clients: int = 0


class BlacklistEntry(BaseModel):
    plate_text: str
    description: str = ""


class BlacklistRecord(BaseModel):
    id: int
    plate_text: str
    description: str
    added_at: str


class ConfigResponse(BaseModel):
    video_source: str
    camera_id: str
    roi_enabled: bool
    roi_coords: dict
    frame_skip: int
    trigger_zone_y: int
    ocr_engine: str
    dedup_window: int
