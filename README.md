### Fraun Test – Survey to Plan app

Small toolkit to: import survey results, generate AI-based recommendations and Maßnahmen, and interact with them via a local FastAPI backend and a static frontend.

### 1) Installation

- Create a virtualenv and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- Configure environment variables

```bash
export GROQ_API_KEY=your_api_key_here
# Optional: if you want the scripts to download the CSV themselves
export SURVEY_URL="https://example.com/path/to/your.csv"
```

### 2) Prepare survey data

- Quick way: place your survey CSV as `table.csv` in the project root.
- Alternate: set `SURVEY_URL` and adapt the scripts to call `load_survey_data(url)` (already implemented in both scripts; the read-from-file path is used by default for speed).

### 3) Generate AI recommendations from survey

Runs the survey summarization and creates a weekly event plan as `events.json`.

```bash
python get_AI_feedback_4_survey.py
```

Outputs:
- `table.csv` (input you provided)
- `events.json` (AI-generated weekly plan used by the app)

### 4) Generate Maßnahmen (action items)

Creates actionable Maßnahmen grouped by categories in `massnahmen.json`.

```bash
python get_AI_feedback_4_massnahmen.py
```

Outputs:
- `massnahmen.json` (AI-generated Maßnahmen with priority)

### 5) Start the backend

```bash
uvicorn backend.main:app --reload
```

- Serves on `http://127.0.0.1:8000`.
- Persists data in the project root: `events.json`, `notes.json`, `messages.json`, `massnahmen.json`.

### 6) Open the web app

- Open `index.html` directly in your browser (no build).
- The frontend talks to the backend at `http://127.0.0.1:8000` to load/add/delete events, manage notes, chat, and view/update Maßnahmen.

### Prompts and customization

- **System prompts**: `system_prompt_event.txt` and `system_prompt_massnahmen.txt`
- **Instructions**: `instructions_event.txt` and `instructions_massnahmen.txt`

Edit these files to steer tone, structure, or output formats. The scripts post-process AI output and validate it against JSON schemas (Pydantic), so keep field names consistent.

