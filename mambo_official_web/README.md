# Project Mambo Official Web App

Mobile-friendly hosted dashboard for KTM Adventure 390 restoration + sales tracking.

## Local run
```bash
pip install -r requirements.txt
uvicorn app:app --reload
```
Open http://127.0.0.1:8000

## Deploy
This app is ready for Render/Railway/Fly.io style deployment.
Start command:
```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

## Data
SQLite database: `mambo.db`
Uploads: `static/uploads`

For serious production use, move uploads to cloud storage and use Postgres.
