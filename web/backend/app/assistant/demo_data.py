"""Deterministic, in-memory interface examples; never insert these into a database."""
from datetime import date, datetime, time, timedelta

from ..storage import TAIPEI

DEMO_TODAY = date(2026, 9, 20)


def make_demo_jobs():
    jobs = []
    for day_index in range(60):
        day = DEMO_TODAY - timedelta(days=59 - day_index)
        for pond_index, pond in enumerate(("A-01", "B-02")):
            job_id = f"demo-{day.isoformat()}-{pond_index}"
            tracks = []
            for index in range(12 + (day_index * 3 + pond_index * 5) % 17):
                length = round(76 + day_index * .22 + ((index * 7) % 23) + pond_index * 3, 1)
                tracks.append({
                    "track_id": str(index + 1), "job_id": job_id,
                    "label": "Unknown" if index % 13 == 0 else "Male" if index % 3 == 0 else "Female",
                    "observations": 20 + index,
                    "length_mm": None if index == 7 and day_index % 11 == 0 else length,
                    "width_mm": round(length * .14 + (index % 4) * .4, 1),
                    "weight_g": round(length ** 3 / 120_000 + (index % 3) * .2, 1),
                })
            jobs.append({
                "id": job_id, "filename": f"示範_{day.isoformat()}_{pond}.mp4", "pond": pond,
                "recorded_at": datetime.combine(day, time(8 + pond_index * 6, 15), TAIPEI),
                "water_label": "turbid" if (day_index + pond_index) % 9 == 0 else "clear",
                "details": {"sample": True}, "tracks": tracks,
            })
    return jobs
