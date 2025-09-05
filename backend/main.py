from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, List, Optional
import os
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from groq import Groq

# Load environment variables
load_dotenv()

# Initialize Groq client
client = Groq(
    api_key=os.getenv("GROQ_API_KEY"),
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVENTS_FILE = PROJECT_ROOT / "events.json"
NOTES_FILE = PROJECT_ROOT / "notes.json"
CHAT_FILE = PROJECT_ROOT / "messages.json"
MASSNAHMEN_FILE = PROJECT_ROOT / "massnahmen.json"
TABLE_CSV_FILE = PROJECT_ROOT / "table.csv"


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
    category: str = Field("personal", pattern=r"^(personal|work|free time)$")


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
                    category = item.get("category", "personal")
                    if category not in ["personal", "work", "free time"]:
                        category = "personal"
                    normalized_notes.append({"id": int(item["id"]), "text": str(item["text"]), "category": category})
            return {"notes": normalized_notes, "next_id": int(next_id) if isinstance(next_id, int) else 1}
        except Exception:
            return {"notes": [], "next_id": 1}


def _write_notes(payload: Dict[str, object]) -> None:
    with _file_lock:
        NOTES_FILE.write_text(json.dumps(payload, indent=2))


def _read_table_csv_text() -> str:
    """Read the entire table.csv as UTF-8 text; return empty string if missing/error."""
    try:
        if not TABLE_CSV_FILE.exists():
            return ""
        return TABLE_CSV_FILE.read_text(encoding="utf-8")
    except Exception:
        return ""


# Chat models and helpers
class ChatMessage(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant)$")
    text: str = Field("", max_length=10000)


class ChatResponse(BaseModel):
    messages: List[ChatMessage]


# Massnahmen models
class Massnahme(BaseModel):
    title: str
    description: str
    priority: str = Field(..., pattern=r"^(hoch|mittel|niedrig)$")


class MassnahmenResponse(BaseModel):
    einmalige_massnahmen: List[Massnahme]
    arbeitsplatz: List[Massnahme]
    work_life_balance: List[Massnahme]


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


# Massnahmen helpers
def _read_massnahmen() -> Dict[str, List[dict]]:
    _ensure_file_exists()
    with _file_lock:
        try:
            if not MASSNAHMEN_FILE.exists():
                return {"einmalige_massnahmen": [], "arbeitsplatz": [], "work_life_balance": []}
            raw = MASSNAHMEN_FILE.read_text()
            data = json.loads(raw) if raw.strip() else {}
            if not isinstance(data, dict):
                return {"einmalige_massnahmen": [], "arbeitsplatz": [], "work_life_balance": []}
            
            # Ensure all three categories exist
            result = {
                "einmalige_massnahmen": data.get("einmalige_massnahmen", []),
                "arbeitsplatz": data.get("arbeitsplatz", []),
                "work_life_balance": data.get("work_life_balance", [])
            }
            
            # Validate that each category is a list
            for category in result:
                if not isinstance(result[category], list):
                    result[category] = []
            
            return result
        except Exception:
            return {"einmalige_massnahmen": [], "arbeitsplatz": [], "work_life_balance": []}


def get_ai_chat_completion(user_message: str) -> str:
    """Get AI response using Groq API with context from events and notes."""
    try:
        # Load system prompt
        #system_prompt_file = PROJECT_ROOT / "system_prompt.txt"
        system_prompt = "Du beantwortest nur Fragen zum modernen Arbeiten und Hybriden Arbeiten, zu den geplanten Events und Maßnahmen sowie zu den Umfrageergebnissen (table.csv). Halte deine Antworten kurz und prägnant."
        #if system_prompt_file.exists():
        #    system_prompt = system_prompt_file.read_text()
        
        # Load events and notes for context
        events_data = _read_events()
        notes_data = _read_notes()
        survey_csv_text = _read_table_csv_text()
        
        # Create context string
        context = f"""
Momentane Events (events.json):
{json.dumps(events_data, indent=2, ensure_ascii=False)}

Momentane Maßnahmen (notes.json):
{json.dumps(notes_data, indent=2, ensure_ascii=False)}

Umfrageergebnisse (table.csv, roher CSV-Inhalt):
{survey_csv_text}

User Input: {user_message}
"""
        
        # Get AI response
        response = client.chat.completions.create(
            model="meta-llama/llama-4-maverick-17b-128e-instruct",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            temperature=0.7,
            max_tokens=1000,
        )
        
        return response.choices[0].message.content
    except Exception as e:
        return f"I apologize, but I encountered an error while processing your request: {str(e)}"


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
    category: str = Field("personal", pattern=r"^(personal|work|free time)$")


@app.post("/notes", response_model=NotesResponse)
def create_note(payload: CreateNoteRequest) -> NotesResponse:
    state = _read_notes()
    notes: List[dict] = state["notes"]  # type: ignore[assignment]
    next_id: int = state["next_id"]  # type: ignore[assignment]
    new_note = {"id": next_id, "text": payload.text, "category": payload.category}
    notes.append(new_note)
    state["notes"] = notes
    state["next_id"] = next_id + 1
    _write_notes(state)
    return NotesResponse(notes=[Note(**n) for n in notes])


class UpdateNoteRequest(BaseModel):
    text: str = Field("", max_length=10000)
    category: str = Field("personal", pattern=r"^(personal|work|free time)$")


@app.put("/notes/{note_id}", response_model=NotesResponse)
def update_note(note_id: int, payload: UpdateNoteRequest) -> NotesResponse:
    state = _read_notes()
    notes: List[dict] = state["notes"]  # type: ignore[assignment]
    updated = False
    for n in notes:
        if int(n.get("id")) == note_id:
            n["text"] = payload.text
            n["category"] = payload.category
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
    
    # Add user message
    msgs.append({"role": payload.role, "text": payload.text})
    
    # If it's a user message, get AI response
    if payload.role == "user":
        ai_response = get_ai_chat_completion(payload.text)
        msgs.append({"role": "assistant", "text": ai_response})
    
    state["messages"] = msgs
    _write_chat(state)
    return ChatResponse(messages=[ChatMessage(**m) for m in msgs])


# Massnahmen endpoints
@app.get("/massnahmen", response_model=MassnahmenResponse)
def get_massnahmen() -> MassnahmenResponse:
    data = _read_massnahmen()
    
    # Convert to Massnahme objects for validation
    einmalige_massnahmen = [Massnahme(**item) for item in data["einmalige_massnahmen"]]
    arbeitsplatz = [Massnahme(**item) for item in data["arbeitsplatz"]]
    work_life_balance = [Massnahme(**item) for item in data["work_life_balance"]]
    
    return MassnahmenResponse(
        einmalige_massnahmen=einmalige_massnahmen,
        arbeitsplatz=arbeitsplatz,
        work_life_balance=work_life_balance
    )


def _write_massnahmen(data: Dict[str, List[dict]]) -> None:
    with _file_lock:
        MASSNAHMEN_FILE.write_text(json.dumps(data, indent=2))


class UpdateMassnahmeRequest(BaseModel):
    title: str
    description: str
    priority: str = Field(..., pattern=r"^(hoch|mittel|niedrig)$")


@app.put("/massnahmen/{category}/{index}", response_model=MassnahmenResponse)
def update_massnahme(category: str, index: int, payload: UpdateMassnahmeRequest) -> MassnahmenResponse:
    if category not in ["einmalige_massnahmen", "arbeitsplatz", "work_life_balance"]:
        raise HTTPException(status_code=400, detail="Invalid category")
    
    data = _read_massnahmen()
    category_items = data.get(category, [])
    
    if index < 0 or index >= len(category_items):
        raise HTTPException(status_code=404, detail="Massnahme not found")
    
    # Update the massnahme
    category_items[index] = payload.dict()
    data[category] = category_items
    _write_massnahmen(data)
    
    # Return updated data
    einmalige_massnahmen = [Massnahme(**item) for item in data["einmalige_massnahmen"]]
    arbeitsplatz = [Massnahme(**item) for item in data["arbeitsplatz"]]
    work_life_balance = [Massnahme(**item) for item in data["work_life_balance"]]
    
    return MassnahmenResponse(
        einmalige_massnahmen=einmalige_massnahmen,
        arbeitsplatz=arbeitsplatz,
        work_life_balance=work_life_balance
    )


class CreateMassnahmeRequest(BaseModel):
    title: str
    description: str
    priority: str = Field(..., pattern=r"^(hoch|mittel|niedrig)$")


@app.post("/massnahmen/{category}", response_model=MassnahmenResponse)
def create_massnahme(category: str, payload: CreateMassnahmeRequest) -> MassnahmenResponse:
    if category not in ["einmalige_massnahmen", "arbeitsplatz", "work_life_balance"]:
        raise HTTPException(status_code=400, detail="Invalid category")

    data = _read_massnahmen()
    category_items = data.get(category, [])

    category_items.append(payload.dict())
    data[category] = category_items
    _write_massnahmen(data)

    einmalige_massnahmen = [Massnahme(**item) for item in data["einmalige_massnahmen"]]
    arbeitsplatz = [Massnahme(**item) for item in data["arbeitsplatz"]]
    work_life_balance = [Massnahme(**item) for item in data["work_life_balance"]]

    return MassnahmenResponse(
        einmalige_massnahmen=einmalige_massnahmen,
        arbeitsplatz=arbeitsplatz,
        work_life_balance=work_life_balance
    )


@app.delete("/massnahmen/{category}/{index}", response_model=MassnahmenResponse)
def delete_massnahme(category: str, index: int) -> MassnahmenResponse:
    if category not in ["einmalige_massnahmen", "arbeitsplatz", "work_life_balance"]:
        raise HTTPException(status_code=400, detail="Invalid category")
    
    data = _read_massnahmen()
    category_items = data.get(category, [])
    
    if index < 0 or index >= len(category_items):
        raise HTTPException(status_code=404, detail="Massnahme not found")
    
    # Remove the massnahme
    del category_items[index]
    data[category] = category_items
    _write_massnahmen(data)
    
    # Return updated data
    einmalige_massnahmen = [Massnahme(**item) for item in data["einmalige_massnahmen"]]
    arbeitsplatz = [Massnahme(**item) for item in data["arbeitsplatz"]]
    work_life_balance = [Massnahme(**item) for item in data["work_life_balance"]]
    
    return MassnahmenResponse(
        einmalige_massnahmen=einmalige_massnahmen,
        arbeitsplatz=arbeitsplatz,
        work_life_balance=work_life_balance
    )

