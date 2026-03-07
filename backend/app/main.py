from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.extraction import router as extraction_router
from app.api.health import router as health_router
from app.api.templates import router as templates_router
from app.services.paddle_engine import initialize_paddle_ocr
from app.storage.template_store import TemplateStore

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

store = TemplateStore(DATA_DIR)

app = FastAPI(title="Document Template Extractor")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")


@app.on_event("startup")
def startup_event() -> None:
    initialize_paddle_ocr()

app.include_router(health_router)
app.include_router(templates_router)
app.include_router(extraction_router)
