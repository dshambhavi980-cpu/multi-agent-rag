# API

FastAPI foundation for the Multi-Agent Hybrid RAG assistant.

## Local commands

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload --port 8000
```

Quality checks:

```powershell
python -m ruff check .
python -m ruff format --check .
python -m mypy app tests
python -m pytest
```
