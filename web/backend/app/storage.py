from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from starlette.responses import StreamingResponse

TAIPEI = ZoneInfo("Asia/Taipei")
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
ARTIFACT_NAMES = {
    "tracks": "個體量測 CSV", "detections": "逐幀偵測 CSV",
    "water": "水質結果 CSV", "monitoring": "監測設定 JSON", "summary": "影片摘要 CSV",
}


def safe_path(root: Path, relative: str) -> Path:
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("Storage path is outside configured root")
    return resolved


def parse_recorded_at(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        if len(value) == 10:
            result = datetime.combine(date.fromisoformat(value), time.min, TAIPEI)
        else:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if result.tzinfo is None:
                raise ValueError("A timestamp needs a timezone offset")
        return result.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise HTTPException(422, "recorded_at 必須是 YYYY-MM-DD 或含時區的 ISO 日期時間") from exc


def day_bounds(start: date | None, end: date | None):
    if start and end and start > end:
        raise HTTPException(422, "開始日期不能晚於結束日期")
    try:
        return (
            datetime.combine(start, time.min, TAIPEI).astimezone(timezone.utc) if start else None,
            datetime.combine(end + timedelta(days=1), time.min, TAIPEI).astimezone(timezone.utc) if end else None,
        )
    except (ValueError, OverflowError) as exc:
        raise HTTPException(422, "日期超出可查詢範圍。") from exc


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def clean_filename(value: str) -> str:
    # Both slash styles are stripped even when running on a different platform.
    name = value.replace("\\", "/").rsplit("/", 1)[-1]
    return re.sub(r"[\x00-\x1f\x7f]", "", name)[:255] or "upload.mp4"


def video_response(path: Path, range_header: str | None, head: bool = False):
    if not path.is_file():
        raise HTTPException(404, "影片尚未準備完成")
    size = path.stat().st_size
    start, end = 0, max(size - 1, 0)
    status = 200
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=60"}
    if range_header:
        # Bound ASCII numeric fields before conversion (including huge suffix values).
        match = re.fullmatch(r"bytes=([0-9]{0,20})-([0-9]{0,20})", range_header.strip()) if len(range_header) <= 48 else None
        if not match or not any(match.groups()) or size == 0:
            raise HTTPException(416, "無法使用此影片範圍", headers={"Content-Range": f"bytes */{size}"})
        left, right = match.groups()
        if left:
            start, end = int(left), min(int(right), size - 1) if right else size - 1
        else:
            suffix = int(right)
            start, end = max(0, size - suffix), size - 1
            if suffix == 0:
                start = size
        if start >= size or start > end:
            raise HTTPException(416, "無法使用此影片範圍", headers={"Content-Range": f"bytes */{size}"})
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    length = end - start + 1 if size else 0
    headers["Content-Length"] = str(length)

    def chunks():
        if head:
            return
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(chunks(), status_code=status, media_type="video/mp4", headers=headers)
