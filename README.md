# Project Deployment & Run Instructions

This README explains how to set up and run your project on a fresh Ubuntu server. 
It includes steps for the backend, admin backend, frontend apps, and the Telegram worker.

---

## 0) Initial Server Setup (One-time)
```bash
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential libffi-dev libssl-dev
sudo apt install -y python-is-python3

# Install Node.js (v20)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Optional: tmux for persistent sessions
sudo apt install -y tmux

# Open ports (if firewall is enabled)
sudo ufw allow 8000,8010,5173,5174/tcp
sudo ufw status
```

---

## 1) Backend (port 8000)
```bash
cd ~/main_algo/AlgoDenis/backend
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 2) Admin Backend (port 8010)
```bash
cd ~/main_algo/AlgoDenis/admin_backend
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8010
```

---

## 3) Admin Frontend
1. Create `.env.production` in `admin_frontend/`:
```
VITE_ADMIN_API_URL=http://YOUR_SERVER_IP:8010
```
2. Install and run:

```bash
cd ~/main_algo/AlgoDenis/admin_frontend
npm ci || npm install
npm run dev -- --host --port 5174
# or build for production:
npm run build
npx serve -s dist -l 5174
```

---

## 4) Frontend
1. Create `.env.production` in `frontend/`:
```
VITE_API_URL=http://YOUR_SERVER_IP:8000
```
2. Install and run:

```bash
cd ~/main_algo/AlgoDenis/frontend
npm ci || npm install
npm run dev -- --host --port 5173
# or build for production:
npm run build
npx serve -s dist -l 5173
```

---

## 5) Telegram Worker
```bash
cd ~/main_algo/AlgoDenis/telegram-ai-worker
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

---

## 6) Run Services with tmux (Recommended)
```bash
tmux new -ds api-main   'cd ~/main_algo/AlgoDenis/backend && source .venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 8000'
tmux new -ds api-admin  'cd ~/main_algo/AlgoDenis/admin_backend && source .venv/bin/activate && uvicorn app:app --host 0.0.0.0 --port 8010'
tmux new -ds fe-admin   'cd ~/main_algo/AlgoDenis/admin_frontend && npm run dev -- --host --port 5174'
tmux new -ds fe-main    'cd ~/main_algo/AlgoDenis/frontend && npm run dev -- --host --port 5173'
tmux new -ds tg-worker  'cd ~/main_algo/AlgoDenis/telegram-ai-worker && source .venv/bin/activate && python main.py'
tmux ls
```

---

## Notes
- Always use `.env.production` for correct API URLs.

- Use `curl http://YOUR_SERVER_IP:8000/docs` or `:8010/docs` to check API availability.

- Consider Nginx reverse proxy for production deployment.

