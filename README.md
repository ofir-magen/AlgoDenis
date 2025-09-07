# GPT + PDF Chat (React + FastAPI WebSocket)

Build date: 2025-08-23T20:17:52

This project combines your GPT+PDF code with a WebSocket full-stack app.

- **Backend (FastAPI)** exposes `/ws` and returns GPT answers with incremental ids.
- **Frontend (React + Vite)** connects via WebSocket and shows a chat-like history, newest on top.

## Folder Structure

```
gpt-pdf-chat/
├─ backend/
│  ├─ ai.py                 # YOUR file: GPT integration (ask_text, ask_with_pdf). Reads .env for keys.
│  ├─ exportForWeb.py       # YOUR file: Maya PDF downloader. Should return a local PDF path.
│  ├─ .env                  # Your secrets (API keys). Not for git.
│  ├─ main.py               # FastAPI WebSocket server. Calls ai.py & exportForWeb.py.
│  ├─ requirements.txt      # Backend dependencies (fastapi, uvicorn, python-dotenv).
│  ├─ pdf_store/            # Created at runtime to store downloaded PDFs.
│  └─ _examples/
│     └─ user_main_example.py  # Your original main.py for reference (won't be executed).
│
└─ frontend/
   ├─ index.html
   ├─ package.json          # Vite + React dev setup
   ├─ vite.config.js
   └─ src/
      ├─ main.jsx
      └─ App.jsx            # Chat UI: supports optional report_id; saves history (max 1000) to localStorage.
```

## Run (Local)

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

- WebSocket endpoint: `ws://localhost:8000/ws`
- Health check: `http://localhost:8000/api/health`

### Frontend

```bash
cd frontend
npm i
npm run dev
```

Open http://localhost:5173

### Using the App

- Optionally fill **Report ID** (Maya id, e.g. `P1687146`). If provided, backend will download the PDF and call `ask_with_pdf(prompt, pdf_path)`.
- If left empty, backend calls `ask_text(prompt)`.
- Responses include a server-wide `id`, the original `asked` prompt, optional `report_id`, and timestamp.
- The UI keeps the latest 1000 messages in localStorage (persist across refresh).

## Notes

- If your `exportForWeb.py` uses a specific function name for PDF download different from common ones, edit `find_export_fn()` in `backend/main.py` to match.
- If your `ai.py` functions are already async, you can call them directly (remove the run_in_executor wrappers).
- Ensure `.env` contains your required keys. It is loaded on backend startup.

back:
uvicorn main:app --reload --port 8000
front:
npm i
npm run dev

uvicorn app:app --host $(grep ^HOST .env | cut -d= -f2) --port $(grep ^PORT .env | cut -d= -f2)
