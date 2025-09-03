Run the backend

1) Create a virtualenv (recommended) and install deps:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Start the FastAPI server:

```
uvicorn backend.main:app --reload
```

It will listen on http://127.0.0.1:8000 and create `events.json` in the project root when the first request arrives.

Use the frontend

Open `index.html` directly in the browser (no build needed). It will call the backend at 127.0.0.1:8000 to load/add/delete events.


