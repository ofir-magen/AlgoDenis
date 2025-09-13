# Affiliates React Minimal (single .env, pages/)

- Single **.env** at project root controls everything (backend + CORS).
- **Backend**: FastAPI, JWT, authenticates against your **existing SQLite users DB** (no SQLAlchemy).
- **Frontend**: React + Vite with **src/pages**: `Login.jsx` → `Dashboard.jsx`.

## Tree
```
affiliate-react-min/
  .env.example
  backend/
    main.py
    requirements.txt
  frontend/
    index.html
    package.json
    vite.config.js
    src/
      styles.css
      main.jsx
      App.jsx
      api.js
      pages/
        Login.jsx
        Dashboard.jsx
```

## Setup

### 1) Root env
```bash
cd affiliate-react-min
cp .env.example .env
# Edit .env (SECRET_KEY, FRONTEND_ORIGINS, USERS_DB_PATH mapping to your existing DB, etc.)
```

### 2) Backend
```bash
cd affiliate-react-min/backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8020
```

### 3) Frontend
```bash
cd affiliate-react-min/frontend
npm install
npm run dev -- --host --port 5180
```
The frontend computes API base by swapping port 5180→8020, so no extra env files.
If you deploy differently, adjust `apiBase()` in `src/api.js`.

## Notes
- `USERS_DB_PATH` must point to your existing SQLite DB file with users.
- Match `USERS_TABLE`, `USERNAME_COL`, `PASSWORD_HASH_COL`, `ACTIVE_COL`, `HASH_SCHEME` to your schema.
- Ensure `FRONTEND_ORIGINS` in `.env` includes the exact dev origin (e.g., http://localhost:5180).
