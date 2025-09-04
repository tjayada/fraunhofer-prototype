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
NOTES_FILE = PROJECT_ROOT / "notes.json"
CHAT_FILE = PROJECT_ROOT / "messages.json"


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
    if not NOTES_FILE.exists():
        with _file_lock:
            if not NOTES_FILE.exists():
                NOTES_FILE.write_text(json.dumps({"notes": [], "next_id": 1}, indent=2))
    if not CHAT_FILE.exists():
        with _file_lock:
            if not CHAT_FILE.exists():
                CHAT_FILE.write_text(json.dumps({"messages": []}, indent=2))


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


# Notes models and helpers
class Note(BaseModel):
    id: int
    text: str = Field("", max_length=10000)


class NotesResponse(BaseModel):
    notes: List[Note]


def _read_notes() -> Dict[str, object]:
    _ensure_file_exists()
    with _file_lock:
        try:
            raw = NOTES_FILE.read_text()
            data = json.loads(raw) if raw.strip() else {"notes": [], "next_id": 1}
            if not isinstance(data, dict):
                return {"notes": [], "next_id": 1}
            notes = data.get("notes", [])
            next_id = data.get("next_id", 1)
            if not isinstance(notes, list):
                notes = []
            normalized_notes: List[dict] = []
            for item in notes:
                if isinstance(item, dict) and "id" in item and "text" in item:
                    normalized_notes.append({"id": int(item["id"]), "text": str(item["text"])})
            return {"notes": normalized_notes, "next_id": int(next_id) if isinstance(next_id, int) else 1}
        except Exception:
            return {"notes": [], "next_id": 1}


def _write_notes(payload: Dict[str, object]) -> None:
    with _file_lock:
        NOTES_FILE.write_text(json.dumps(payload, indent=2))


# Chat models and helpers
class ChatMessage(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant)$")
    text: str = Field("", max_length=10000)


class ChatResponse(BaseModel):
    messages: List[ChatMessage]


def _read_chat() -> Dict[str, object]:
    _ensure_file_exists()
    with _file_lock:
        try:
            raw = CHAT_FILE.read_text()
            data = json.loads(raw) if raw.strip() else {"messages": []}
            if not isinstance(data, dict):
                return {"messages": []}
            msgs = data.get("messages", [])
            if not isinstance(msgs, list):
                msgs = []
            normalized: List[dict] = []
            for item in msgs:
                if isinstance(item, dict) and "role" in item and "text" in item:
                    normalized.append({"role": str(item["role"]), "text": str(item["text"])})
            return {"messages": normalized}
        except Exception:
            return {"messages": []}


def _write_chat(payload: Dict[str, object]) -> None:
    with _file_lock:
        CHAT_FILE.write_text(json.dumps(payload, indent=2))


app = FastAPI(title="Calendar Events API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all origins, including file:// via wildcard
    allow_credentials=False,  # must be False when allow_origins is "*"
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


# Notes endpoints
@app.get("/notes", response_model=NotesResponse)
def get_notes() -> NotesResponse:
    data = _read_notes()
    notes = [Note(**n) for n in data["notes"]]
    return NotesResponse(notes=notes)


class CreateNoteRequest(BaseModel):
    text: str = Field("", max_length=10000)


@app.post("/notes", response_model=NotesResponse)
def create_note(payload: CreateNoteRequest) -> NotesResponse:
    state = _read_notes()
    notes: List[dict] = state["notes"]  # type: ignore[assignment]
    next_id: int = state["next_id"]  # type: ignore[assignment]
    new_note = {"id": next_id, "text": payload.text}
    notes.append(new_note)
    state["notes"] = notes
    state["next_id"] = next_id + 1
    _write_notes(state)
    return NotesResponse(notes=[Note(**n) for n in notes])


class UpdateNoteRequest(BaseModel):
    text: str = Field("", max_length=10000)


@app.put("/notes/{note_id}", response_model=NotesResponse)
def update_note(note_id: int, payload: UpdateNoteRequest) -> NotesResponse:
    state = _read_notes()
    notes: List[dict] = state["notes"]  # type: ignore[assignment]
    updated = False
    for n in notes:
        if int(n.get("id")) == note_id:
            n["text"] = payload.text
            updated = True
            break
    if not updated:
        raise HTTPException(status_code=404, detail="Note not found")
    _write_notes(state)
    return NotesResponse(notes=[Note(**n) for n in notes])


@app.delete("/notes/{note_id}", response_model=NotesResponse)
def delete_note(note_id: int) -> NotesResponse:
    state = _read_notes()
    notes: List[dict] = state["notes"]  # type: ignore[assignment]
    filtered = [n for n in notes if int(n.get("id")) != note_id]
    if len(filtered) == len(notes):
        raise HTTPException(status_code=404, detail="Note not found")
    state["notes"] = filtered
    _write_notes(state)
    return NotesResponse(notes=[Note(**n) for n in filtered])


# Chat endpoints
@app.get("/chat", response_model=ChatResponse)
def get_chat() -> ChatResponse:
    state = _read_chat()
    msgs = [ChatMessage(**m) for m in state["messages"]]  # type: ignore[index]
    return ChatResponse(messages=msgs)


class CreateChatMessageRequest(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant)$")
    text: str = Field("", max_length=10000)


@app.post("/chat", response_model=ChatResponse)
def add_chat_message(payload: CreateChatMessageRequest) -> ChatResponse:
    state = _read_chat()
    msgs: List[dict] = state["messages"]  # type: ignore[index]
    msgs.append({"role": payload.role, "text": payload.text})
    state["messages"] = msgs
    _write_chat(state)
    return ChatResponse(messages=[ChatMessage(**m) for m in msgs])

