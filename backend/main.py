from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVENTS_FILE = PROJECT_ROOT / "events.json"


class Event(BaseModel):
    title: str = Field(..., min_length=1)
    description: Optional[str] = ""
    hour: int = Field(..., ge=0, le=23)
    duration: int = Field(1, ge=1, le=24)

    @validator("duration")
    def validate_duration(cls, value: int) -> int:
        if value < 1:
            raise ValueError("duration must be >= 1")
        return value


class AddEventRequest(BaseModel):
    day: str
    event: Event


class EventsResponse(BaseModel):
    events: Dict[str, List[Event]]


_file_lock = threading.Lock()


def _ensure_file_exists() -> None:
    if not EVENTS_FILE.exists():
        with _file_lock:
            if not EVENTS_FILE.exists():
                EVENTS_FILE.write_text(json.dumps({}, indent=2))


def _read_events() -> Dict[str, List[dict]]:
    _ensure_file_exists()
    with _file_lock:
        try:
            raw = EVENTS_FILE.read_text()
            data = json.loads(raw) if raw.strip() else {}
            if not isinstance(data, dict):
                return {}
            # Normalize to day -> list
            normalized: Dict[str, List[dict]] = {}
            for day, items in data.items():
                if isinstance(items, list):
                    normalized[day] = [i for i in items if isinstance(i, dict)]
            return normalized
        except Exception:
            return {}


def _write_events(events: Dict[str, List[dict]]) -> None:
    with _file_lock:
        EVENTS_FILE.write_text(json.dumps(events, indent=2))


app = FastAPI(title="Calendar Events API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local file:// or any origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/events", response_model=EventsResponse)
def get_events() -> EventsResponse:
    data = _read_events()
    # Coerce to Event model for response validation
    coerced: Dict[str, List[Event]] = {}
    for day, items in data.items():
        coerced[day] = [Event(**item) for item in items]
    return EventsResponse(events=coerced)


@app.post("/events", response_model=EventsResponse)
def add_event(payload: AddEventRequest) -> EventsResponse:
    data = _read_events()
    day_key = payload.day
    day_events = data.get(day_key, [])

    # Validate overlapping: event must not overlap existing entries
    new_event = payload.event
    new_start = int(new_event.hour)
    new_end = new_start + int(new_event.duration)
    for existing in day_events:
        existing_start = int(existing.get("hour", 0))
        existing_duration = int(existing.get("duration", 1))
        existing_end = existing_start + existing_duration
        if new_start < existing_end and new_end > existing_start:
            raise HTTPException(status_code=400, detail="Event overlaps with an existing event")

    day_events.append(new_event.dict())
    data[day_key] = day_events
    _write_events(data)

    # Return updated events
    coerced: Dict[str, List[Event]] = {}
    for day, items in data.items():
        coerced[day] = [Event(**item) for item in items]
    return EventsResponse(events=coerced)


@app.delete("/events", response_model=EventsResponse)
def delete_event(
    day: str = Query(..., description="Day name, e.g., Monday"),
    index: int = Query(..., ge=0, description="Index of the event in that day list"),
) -> EventsResponse:
    data = _read_events()
    if day not in data:
        raise HTTPException(status_code=404, detail="Day not found")
    day_events = data[day]
    if index < 0 or index >= len(day_events):
        raise HTTPException(status_code=404, detail="Event index not found")

    del day_events[index]
    if len(day_events) == 0:
        del data[day]
    else:
        data[day] = day_events
    _write_events(data)

    coerced: Dict[str, List[Event]] = {}
    for d, items in data.items():
        coerced[d] = [Event(**item) for item in items]
    return EventsResponse(events=coerced)


@app.get("/")
def root() -> dict:
    return {"status": "ok"}


