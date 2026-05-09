"""
SQLite Database for ANPR plate history and blacklist.
Uses aiosqlite for async operations.
"""
import aiosqlite
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path="data/anpr.db"):
        self.db_path = db_path
        self.db = None

    async def init(self):
        """Initialize database and create tables."""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self.db = await aiosqlite.connect(self.db_path)
        self.db.row_factory = aiosqlite.Row

        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS plates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_text TEXT NOT NULL,
                confidence REAL NOT NULL,
                timestamp TEXT NOT NULL,
                camera_id TEXT DEFAULT 'CAM-01',
                image_path TEXT,
                is_blacklisted INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS blacklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_text TEXT UNIQUE NOT NULL,
                description TEXT DEFAULT '',
                added_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_plates_text ON plates(plate_text)
        """)
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_plates_timestamp ON plates(timestamp)
        """)

        await self.db.commit()
        logger.info(f"Database initialized: {self.db_path}")

    async def close(self):
        """Close the database connection."""
        if self.db:
            await self.db.close()

    async def add_plate(self, plate_text, confidence, camera_id, image_path, is_blacklisted=False):
        """Insert a new plate detection record."""
        timestamp = datetime.now().isoformat()
        await self.db.execute(
            """INSERT INTO plates (plate_text, confidence, timestamp, camera_id, image_path, is_blacklisted)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (plate_text, confidence, timestamp, camera_id, image_path, int(is_blacklisted)),
        )
        await self.db.commit()
        return timestamp

    async def get_history(self, page=1, per_page=20, search=None, date_from=None, date_to=None):
        """Get paginated plate history with optional filtering."""
        conditions = []
        params = []

        if search:
            conditions.append("plate_text LIKE ?")
            params.append(f"%{search}%")
        if date_from:
            conditions.append("timestamp >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("timestamp <= ?")
            params.append(date_to)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        offset = (page - 1) * per_page

        # Get total count
        cursor = await self.db.execute(
            f"SELECT COUNT(*) as count FROM plates {where}", params
        )
        row = await cursor.fetchone()
        total = row[0]

        # Get records
        cursor = await self.db.execute(
            f"""SELECT id, plate_text, confidence, timestamp, camera_id, image_path, is_blacklisted
                FROM plates {where}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?""",
            params + [per_page, offset],
        )
        rows = await cursor.fetchall()

        records = [
            {
                "id": r[0],
                "plate_text": r[1],
                "confidence": r[2],
                "timestamp": r[3],
                "camera_id": r[4],
                "image_path": r[5],
                "is_blacklisted": bool(r[6]),
            }
            for r in rows
        ]

        return {
            "records": records,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
        }

    async def get_all_detections(self):
        """Get all detections for CSV export."""
        cursor = await self.db.execute(
            """SELECT id, plate_text, confidence, timestamp, camera_id, image_path
               FROM plates ORDER BY timestamp DESC"""
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "plate_text": r[1],
                "confidence": r[2],
                "timestamp": r[3],
                "camera_id": r[4],
                "image_path": r[5],
            }
            for r in rows
        ]

    async def add_blacklist(self, plate_text, description=""):
        """Add a plate to the blacklist."""
        try:
            await self.db.execute(
                "INSERT OR IGNORE INTO blacklist (plate_text, description) VALUES (?, ?)",
                (plate_text.upper().replace(" ", ""), description),
            )
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Blacklist add error: {e}")
            return False

    async def remove_blacklist(self, plate_text):
        """Remove a plate from the blacklist."""
        await self.db.execute(
            "DELETE FROM blacklist WHERE plate_text = ?",
            (plate_text.upper().replace(" ", ""),),
        )
        await self.db.commit()

    async def get_blacklist(self):
        """Get all blacklisted plates."""
        cursor = await self.db.execute(
            "SELECT id, plate_text, description, added_at FROM blacklist ORDER BY added_at DESC"
        )
        rows = await cursor.fetchall()
        return [
            {"id": r[0], "plate_text": r[1], "description": r[2], "added_at": r[3]}
            for r in rows
        ]

    async def get_today_stats(self):
        """Get stats for today's detections."""
        today = datetime.now().strftime("%Y-%m-%d")
        cursor = await self.db.execute(
            """SELECT COUNT(*) as count, AVG(confidence) as avg_conf
               FROM plates WHERE timestamp LIKE ?""",
            (f"{today}%",),
        )
        row = await cursor.fetchone()
        return {
            "total_today": row[0] or 0,
            "avg_confidence": round(row[1] or 0, 3),
        }
