"""Single-user, loopback-only developer beta."""
import os
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
from . import beta

@asynccontextmanager
async def lifespan(app):
    beta.recover()
    yield

app = FastAPI(title="MemoryScope developer beta", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","),
    allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
)
app.include_router(beta.router)

@app.get("/api/health")
def health():
    return {"status": "ok", "product": "MemoryScope", "mode": "local-developer-beta"}
