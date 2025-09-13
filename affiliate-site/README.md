# Affiliate Site (FastAPI + Vite/React)

## Prerequisites
```bash
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential libffi-dev
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs tmux
```

## Backend (port 8020)
```bash
cd ~/affiliate-site/backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python -m backend.manage create-user --username partner1 --password StrongPass123
uvicorn backend.main:app --host 0.0.0.0 --port 8020
```

## Frontend (port 5180)
```bash
cd ~/affiliate-site/frontend
npm install
npm run dev -- --host --port 5180
# or production:
npm run build
npx serve -s dist -l 5180
```
Set `frontend/.env.production` to:
```
VITE_API_URL=http://YOUR_SERVER_IP:8020
```

## tmux
```bash
tmux new -ds affiliates-api 'cd ~/affiliate-site/backend && source .venv/bin/activate && uvicorn backend.main:app --host 0.0.0.0 --port 8020'
tmux new -ds affiliates-fe  'cd ~/affiliate-site/frontend && npm run dev -- --host --port 5180'
tmux ls
```
