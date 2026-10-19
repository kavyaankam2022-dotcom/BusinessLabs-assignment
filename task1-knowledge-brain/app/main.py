from contextlib import asynccontextmanager
import asyncio
import hmac
import logging
import os
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from .answering import generate_answer
from .config import settings
from .ingestion import run_ingestion
from .schemas import (
    APIError,
    EscalationCreate,
    EscalationResolve,
    EvaluationCaseReview,
    ExpertKnowledgeRevision,
    IngestionRequest,
    QueryRequest,
    QueryResponse,
)
from .store import KnowledgeStore
from .vectors import Embedder

store = KnowledgeStore(settings.database_path)
embedder = Embedder(settings.embedding_model)
logger = logging.getLogger(__name__)
ingestion_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.initialize()
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        scheduled_ingestion_run,
        "cron",
        hour=settings.daily_ingestion_hour,
        minute=settings.daily_ingestion_minute,
        id="daily-knowledge-refresh",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="Knowledge Brain API",
    version="1.0.0",
    description="Grounded product knowledge search with citations and human escalation.",
    lifespan=lifespan,
)
WEB_ROOT = Path(__file__).resolve().parents[1] / "web"


@app.get("/")
def home() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/styles.css")
def styles() -> FileResponse:
    return FileResponse(WEB_ROOT / "styles.css", media_type="text/css")


@app.get("/ui.js")
def ui_script() -> FileResponse:
    return FileResponse(WEB_ROOT / "ui.js", media_type="text/javascript")


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, error: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        headers=error.headers,
        content=APIError(
            code="http_error",
            message=str(error.detail),
            request_id=request.state.request_id,
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, error: RequestValidationError) -> JSONResponse:
    errors = [
        {
            "field": ".".join(str(part) for part in item["loc"] if part != "body"),
            "message": item["msg"],
            "type": item["type"],
        }
        for item in error.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=APIError(
            code="validation_error",
            message="Request validation failed.",
            request_id=request.state.request_id,
            errors=errors,
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
    logger.exception("Unhandled API error", exc_info=error)
    return JSONResponse(
        status_code=500,
        content=APIError(
            code="internal_error",
            message="The request could not be completed.",
            request_id=request.state.request_id,
        ).model_dump(),
    )


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    expected_key = os.getenv("KB_API_KEY")
    if expected_key and (x_api_key is None or not hmac.compare_digest(x_api_key, expected_key)):
        raise HTTPException(
            status_code=401,
            detail="A valid API key is required.",
            headers={"WWW-Authenticate": "ApiKey"},
        )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "knowledge-brain"}


@app.post(
    "/query",
    response_model=QueryResponse,
    summary="Answer a product question using indexed evidence",
    responses={401: {"model": APIError}, 422: {"model": APIError}, 500: {"model": APIError}},
)
def query(request: QueryRequest, _: None = Depends(require_api_key)) -> QueryResponse:
    if not store.is_initialized:
        store.initialize()
    evidence = store.search(request.question, embedder, request.top_k, request.customer_id)
    if not evidence:
        reason = "No relevant indexed evidence was found."
        escalation_id = store.create_escalation(EscalationCreate(
            question=request.question,
            reason=reason,
            customer_context=request.customer_context,
            customer_id=request.customer_id,
        ))
        return QueryResponse(
            answer="I could not find sufficient evidence in the knowledge base to answer this question.",
            status="insufficient_evidence",
            sources=[],
            image_references=[],
            needs_human=True,
            escalation_reason=reason,
            escalation_id=escalation_id,
        )

    answer = generate_answer(request.question, evidence)
    if answer is None:
        reason = "Answer generation is not configured or failed."
        escalation_id = store.create_escalation(EscalationCreate(
            question=request.question,
            reason=reason,
            evidence=evidence,
            customer_context=request.customer_context,
            customer_id=request.customer_id,
        ))
        return QueryResponse(
            answer="Relevant source material was found, but answer generation is unavailable. Please review the cited evidence or escalate to an expert.",
            status="needs_human",
            sources=evidence,
            image_references=_image_references(evidence),
            needs_human=True,
            escalation_reason=reason,
            escalation_id=escalation_id,
        )
    return QueryResponse(
        answer=answer,
        status="answered",
        sources=evidence,
        image_references=_image_references(evidence),
        needs_human=False,
    )


@app.post("/ingestion/run", responses={401: {"model": APIError}, 400: {"model": APIError}, 502: {"model": APIError}, 504: {"model": APIError}})
async def start_ingestion(request: IngestionRequest, _: None = Depends(require_api_key)) -> dict[str, object]:
    if not store.is_initialized:
        store.initialize()
    try:
        return await run_ingestion_tracked("manual", request.sitemap_url or settings.sitemap_url, request.max_pages)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except asyncio.TimeoutError as error:
        raise HTTPException(status_code=504, detail="Ingestion exceeded the configured time limit.") from error
    except (httpx.HTTPError, ET.ParseError) as error:
        raise HTTPException(status_code=502, detail="The sitemap or an article could not be fetched or parsed.") from error


@app.get("/ingestion/status", responses={401: {"model": APIError}})
def ingestion_status(_: None = Depends(require_api_key)) -> dict[str, object]:
    if not store.is_initialized:
        store.initialize()
    return store.ingestion_status()


@app.get("/escalations", responses={401: {"model": APIError}})
def list_escalations(status: str = "open", limit: int = 50,
                     _: None = Depends(require_api_key)) -> list[dict[str, object]]:
    if status not in {"open", "resolved"} or not 1 <= limit <= 200:
        raise HTTPException(status_code=422, detail="status must be open or resolved and limit must be 1-200")
    if not store.is_initialized:
        store.initialize()
    return store.list_escalations(status, limit)


@app.get("/evaluation/cases", responses={401: {"model": APIError}})
def list_evaluation_cases(status: str = "pending", limit: int = 100,
                          _: None = Depends(require_api_key)) -> list[dict[str, object]]:
    if status not in {"pending", "reviewed"} or not 1 <= limit <= 500:
        raise HTTPException(status_code=422, detail="status must be pending or reviewed and limit must be 1-500")
    if not store.is_initialized:
        store.initialize()
    return store.evaluation_cases(status, limit)


@app.post("/evaluation/cases/{escalation_id}/review", responses={401: {"model": APIError}, 404: {"model": APIError}})
def review_evaluation_case(escalation_id: str, request: EvaluationCaseReview,
                           _: None = Depends(require_api_key)) -> dict[str, object]:
    if not store.is_initialized:
        store.initialize()
    updated = store.mark_evaluation_case(
        escalation_id, request.actual_result, request.passed, request.reviewed_by
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Pending evaluation case not found")
    return {"escalation_id": escalation_id, "status": "reviewed", "passed": request.passed}


@app.post("/escalations", responses={401: {"model": APIError}, 422: {"model": APIError}})
def create_escalation(request: EscalationCreate, _: None = Depends(require_api_key)) -> dict[str, object]:
    if not store.is_initialized:
        store.initialize()
    escalation_id = store.create_escalation(request)
    return {"id": escalation_id, "status": "open"}


@app.post("/escalations/{escalation_id}/resolve", responses={401: {"model": APIError}, 404: {"model": APIError}})
def resolve_escalation(escalation_id: str, request: EscalationResolve, _: None = Depends(require_api_key)) -> dict[str, object]:
    if not store.is_initialized:
        store.initialize()
    version = store.resolve_escalation(escalation_id, request, embedder.encode(request.answer))
    if version is None:
        raise HTTPException(status_code=404, detail="Open escalation not found")
    return {"id": escalation_id, "status": "resolved", "knowledge_id": f"expert-{escalation_id}",
            "version": version, "indexed": True}


@app.get("/expert-knowledge/{knowledge_id}/versions", responses={401: {"model": APIError}})
def expert_knowledge_versions(knowledge_id: str, _: None = Depends(require_api_key)) -> list[dict[str, object]]:
    if not store.is_initialized:
        store.initialize()
    versions = store.expert_knowledge_versions(knowledge_id)
    if not versions:
        raise HTTPException(status_code=404, detail="Expert knowledge record not found")
    return versions


@app.post("/expert-knowledge/{knowledge_id}/revise", responses={401: {"model": APIError}, 404: {"model": APIError}})
def revise_expert_knowledge(knowledge_id: str, request: ExpertKnowledgeRevision,
                            _: None = Depends(require_api_key)) -> dict[str, object]:
    if not store.is_initialized:
        store.initialize()
    version = store.revise_expert_knowledge(knowledge_id, request, embedder.encode(request.answer))
    if version is None:
        raise HTTPException(status_code=404, detail="Expert knowledge record not found")
    return {"knowledge_id": knowledge_id, "version": version, "status": "revised", "indexed": True}


async def run_ingestion_tracked(trigger: str, sitemap_url: str | None = None,
                                max_pages: int | None = None) -> dict[str, object]:
    if not store.is_initialized:
        store.initialize()
    async with ingestion_lock:
        run_id = store.start_ingestion_run(trigger)
        try:
            report = await asyncio.wait_for(
                run_ingestion(
                    store=store,
                    embedder=embedder,
                    sitemap_url=sitemap_url or settings.sitemap_url,
                    max_pages=max_pages,
                ),
                timeout=settings.ingestion_job_timeout_seconds,
            )
        except asyncio.TimeoutError:
            store.finish_ingestion_run(run_id, "timeout", error="Ingestion exceeded the configured time limit.")
            raise
        except asyncio.CancelledError:
            store.finish_ingestion_run(run_id, "cancelled", error="Ingestion was cancelled.")
            raise
        except Exception as error:
            store.finish_ingestion_run(run_id, "failed", error=str(error)[:1000])
            raise
        store.finish_ingestion_run(run_id, "completed", report=report)
        return {"run_id": run_id, **report}


async def scheduled_ingestion_run() -> None:
    try:
        await run_ingestion_tracked("daily")
    except Exception:
        logger.exception("Scheduled Knowledge Brain ingestion failed")


def _image_references(evidence: list[dict[str, object]]) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    for source in evidence:
        for image in source.get("images", []):
            if isinstance(image, dict) and image.get("url"):
                references.append({"url": str(image["url"]), "description": str(image.get("description", ""))})
    return references
