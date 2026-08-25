import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.routes import router as agents_router
from app.agents.base import AgentError
from app.db import engine

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("cyber-multi-agent service starting up")
    yield
    logging.info("cyber-multi-agent service shutting down")


app = FastAPI(title="Cyber Defense Multi-Agent Service", lifespan=lifespan)
app.include_router(agents_router)
app.mount("/console", StaticFiles(directory="frontend", html=True), name="console")


@app.exception_handler(AgentError)
async def agent_error_handler(request: Request, exc: AgentError):
    logging.error(f"Agent error: {exc}")
    return JSONResponse(status_code=502, content={"error": {"code": "AGENT_FAILURE", "message": str(exc)}})


@app.get("/health/live")
async def liveness():
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness():
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready", "database": "unavailable"})

    return {"status": "ready", "database": "ok"}
