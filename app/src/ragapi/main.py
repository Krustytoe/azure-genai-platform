"""HTTP API. Run with: uvicorn --factory ragapi.main:create_app"""

import logging
import time
import uuid
from dataclasses import asdict
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .config import Settings
from .pipeline import RagPipeline
from .providers import build_providers
from .providers.base import ProviderError, ProviderThrottledError
from .telemetry import Telemetry, configure_from_env

log = logging.getLogger("ragapi")

TENANT_PATTERN = r"^[a-z0-9][a-z0-9-]{0,62}$"


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)


class CitationOut(BaseModel):
    id: int
    source: str
    score: float
    snippet: str


class UsageOut(BaseModel):
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


class ChatResponse(BaseModel):
    request_id: str
    answer: str
    grounded: bool
    blocked: bool
    citations: list[CitationOut]
    usage: UsageOut | None
    redactions: dict[str, int]


def create_app(settings: Settings | None = None, pipeline: RagPipeline | None = None) -> FastAPI:
    settings = settings or Settings()
    if pipeline is None:
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
        )
        configure_from_env()
        retriever, model = build_providers(settings)
        pipeline = RagPipeline(retriever, model, settings, Telemetry())

    app = FastAPI(title="RAG API", version="0.1.0")

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response

    @app.exception_handler(ProviderThrottledError)
    async def throttled(request: Request, exc: ProviderThrottledError) -> JSONResponse:
        return JSONResponse(
            {"detail": "Upstream model is rate limited, retry shortly."},
            status_code=429,
            headers={"Retry-After": "5"},
        )

    @app.exception_handler(ProviderError)
    async def upstream(request: Request, exc: ProviderError) -> JSONResponse:
        log.error("provider error request_id=%s: %s", request.state.request_id, exc)
        return JSONResponse({"detail": "Upstream model service failed."}, status_code=502)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/chat")
    def chat(
        body: ChatRequest,
        request: Request,
        x_tenant_id: Annotated[str, Header(pattern=TENANT_PATTERN)] = "default",
    ) -> ChatResponse:
        question = body.question.strip()
        if not question:
            raise HTTPException(422, "question must not be blank")
        if len(question) > settings.max_question_chars:
            raise HTTPException(422, f"question exceeds {settings.max_question_chars} characters")

        start = time.perf_counter()
        result = pipeline.ask(question, tenant=x_tenant_id)
        # Log outcome and cost, never the question or answer text.
        log.info(
            "chat request_id=%s tenant=%s outcome=%s tokens_in=%s tokens_out=%s ms=%.0f",
            request.state.request_id,
            x_tenant_id,
            result.outcome,
            result.usage.input_tokens if result.usage else 0,
            result.usage.output_tokens if result.usage else 0,
            (time.perf_counter() - start) * 1000,
        )
        return ChatResponse(
            request_id=request.state.request_id,
            answer=result.answer,
            grounded=result.grounded,
            blocked=result.blocked,
            citations=[CitationOut(**asdict(c)) for c in result.citations],
            usage=UsageOut(**asdict(result.usage)) if result.usage else None,
            redactions=result.redactions,
        )

    return app
