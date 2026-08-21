import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import router as agents_router
from app.agents.base import AgentError

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("cyber-multi-agent service starting up")
    yield
    logging.info("cyber-multi-agent service shutting down")


app = FastAPI(title="Cyber Defense Multi-Agent Service", lifespan=lifespan)
app.include_router(agents_router)


@app.exception_handler(AgentError)
async def agent_error_handler(request: Request, exc: AgentError):
    logging.error(f"Agent error: {exc}")
    return JSONResponse(status_code=502, content={"error": {"code": "AGENT_FAILURE", "message": str(exc)}})


@app.get("/health/live")
async def liveness():
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness():
    # extend this to ping DB/Redis, as covered earlier
    return {"status": "ready"}
