# Run from backend/ with venv activated
# No --reload: reload crashes if code changes during ingest
uvicorn app.main:app --host 127.0.0.1 --port 8000
