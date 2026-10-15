"""FastAPI application factory and operational endpoints."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from pathlib import Path

from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.audit import InMemoryAuditSink, JsonlAuditSink
from app.auth.service import Identity, build_authenticator
from app.config import Settings, get_settings
from app.db.catalog import SAMPLE_QUERY_CATALOG
from app.db.service import DatabaseQueryService, create_read_only_engine
from app.documents.service import DocumentIndexer
from app.llm.service import InferenceOverloaded, InferenceUnavailable, LocalLLMClient
from app.logging_config import configure_logging
from app.orchestration.mcp import (
    DatabaseQueryMCPTool,
    DocumentSearchMCPTool,
    MCPAuthorizationError,
    MCPError,
    MCPExecutionError,
    MCPToolNotFoundError,
    MCPToolRegistry,
    MCPValidationError,
)
from app.orchestration.service import IntranetAssistantService
from app.schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    HealthResponse,
    MCPCallRequest,
    MCPCallResponse,
    MCPToolDescriptor,
    MCPToolsListResponse,
    SessionResponse,
    SourceCitationResponse,
)
from app.security import AuthorizationFailure, current_identity, require_permission

logger = logging.getLogger("app")


def safe_error_response(status_code: int, error: str, message: str, request_id: str) -> JSONResponse:
    """Return a client-safe error without exposing exception details."""
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=error, message=message, request_id=request_id).model_dump(),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    configure_logging()
    logger.info("application_starting", extra={"environment": settings.app_env.value})
    app.state.ready = True
    try:
        yield
    finally:
        app.state.ready = False
        logger.info("application_stopped")


def create_app(
    settings: Settings | None = None,
    llm_client: LocalLLMClient | None = None,
    document_indexer: DocumentIndexer | None = None,
    database_service: DatabaseQueryService | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title=settings.app_name, docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.settings = settings
    app.state.ready = False
    app.state.authenticator = build_authenticator(settings)
    audit_sink = (
        JsonlAuditSink(settings.audit_log_path) if settings.audit_log_path else InMemoryAuditSink()
    )
    app.state.audit_sink = audit_sink

    # Initialize Document Indexer if roots configured or explicitly provided
    if document_indexer is not None:
        app.state.document_indexer = document_indexer
    elif settings.document_roots:
        try:
            indexer = DocumentIndexer(
                roots=settings.document_roots,
                chunk_size=settings.document_chunk_size,
                chunk_overlap=settings.document_chunk_overlap,
            )
            indexer.reindex()
            app.state.document_indexer = indexer
        except Exception:
            logger.warning("document_indexer_init_failed", exc_info=True)
            app.state.document_indexer = None
    else:
        app.state.document_indexer = None

    # Initialize Database Service if URL configured or explicitly provided
    if database_service is not None:
        app.state.database_service = database_service
    elif settings.database_url:
        try:
            engine = create_read_only_engine(settings.database_url)
            app.state.database_service = DatabaseQueryService(
                engine=engine,
                catalog=SAMPLE_QUERY_CATALOG,
                audit_sink=audit_sink,
                max_result_rows=settings.database_max_result_rows,
                timeout_seconds=settings.database_query_timeout_seconds,
            )
        except Exception:
            logger.warning("database_service_init_failed", exc_info=True)
            app.state.database_service = None
    else:
        app.state.database_service = None

    # Initialize MCP Tool Registry and register tools
    tool_registry = MCPToolRegistry(audit_sink)
    if app.state.document_indexer is not None:
        tool_registry.register(DocumentSearchMCPTool(app.state.document_indexer, audit_sink))
    if app.state.database_service is not None:
        tool_registry.register(DatabaseQueryMCPTool(app.state.database_service, audit_sink))
    app.state.tool_registry = tool_registry

    # Initialize Local LLM Client if configured or explicitly provided
    if llm_client is not None:
        app.state.llm_client = llm_client
    elif settings.llm_enabled and settings.llm_base_url:
        try:
            app.state.llm_client = LocalLLMClient(settings)
        except Exception:
            logger.warning("llm_client_init_failed", exc_info=True)
            app.state.llm_client = None
    else:
        app.state.llm_client = None

    # Initialize Intranet Assistant Service
    if app.state.llm_client is not None:
        app.state.assistant_service = IntranetAssistantService(
            settings=settings,
            llm_client=app.state.llm_client,
            tool_registry=tool_registry,
            audit_sink=audit_sink,
        )
    else:
        app.state.assistant_service = None

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        supplied_request_id = request.headers.get("X-Request-ID")
        request_id = supplied_request_id if supplied_request_id and supplied_request_id.isprintable() else str(uuid.uuid4())
        supplied_correlation_id = request.headers.get("X-Correlation-ID")
        correlation_id = (
            supplied_correlation_id
            if supplied_correlation_id and supplied_correlation_id.isprintable()
            else request_id
        )
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Do not emit exception text or tracebacks: either may contain secrets, SQL, or paths.
            logger.error(
                "unhandled_request_error",
                extra={"request_id": request_id, "correlation_id": correlation_id},
            )
            response = safe_error_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "internal_error",
                "An unexpected error occurred.",
                request_id,
            )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        logger.info(
            "request_complete",
            extra={
                "request_id": request_id,
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _: RequestValidationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        return safe_error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_request",
            "The request could not be processed.",
            request_id,
        )

    @app.exception_handler(AuthorizationFailure)
    async def authorization_error(request: Request, error: AuthorizationFailure) -> JSONResponse:
        return safe_error_response(
            error.status_code,
            "authentication_required" if error.status_code == status.HTTP_401_UNAUTHORIZED else "forbidden",
            "Authentication is required or invalid."
            if error.status_code == status.HTTP_401_UNAUTHORIZED
            else "You do not have permission for this resource.",
            getattr(request.state, "request_id", str(uuid.uuid4())),
        )

    @app.exception_handler(InferenceOverloaded)
    async def inference_overloaded_handler(request: Request, _: InferenceOverloaded) -> JSONResponse:
        return safe_error_response(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "service_overloaded",
            "The assistant service is currently at capacity. Please try again shortly.",
            getattr(request.state, "request_id", str(uuid.uuid4())),
        )

    @app.exception_handler(InferenceUnavailable)
    async def inference_unavailable_handler(request: Request, _: InferenceUnavailable) -> JSONResponse:
        return safe_error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "service_unavailable",
            "The assistant inference service is currently unavailable.",
            getattr(request.state, "request_id", str(uuid.uuid4())),
        )

    @app.exception_handler(MCPAuthorizationError)
    async def mcp_auth_handler(request: Request, error: MCPAuthorizationError) -> JSONResponse:
        return safe_error_response(
            status.HTTP_403_FORBIDDEN,
            "forbidden",
            str(error),
            getattr(request.state, "request_id", str(uuid.uuid4())),
        )

    @app.exception_handler(MCPValidationError)
    async def mcp_validation_handler(request: Request, error: MCPValidationError) -> JSONResponse:
        return safe_error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_request",
            str(error),
            getattr(request.state, "request_id", str(uuid.uuid4())),
        )

    @app.exception_handler(MCPToolNotFoundError)
    async def mcp_not_found_handler(request: Request, error: MCPToolNotFoundError) -> JSONResponse:
        return safe_error_response(
            status.HTTP_404_NOT_FOUND,
            "tool_not_found",
            str(error),
            getattr(request.state, "request_id", str(uuid.uuid4())),
        )

    @app.exception_handler(MCPExecutionError)
    async def mcp_execution_handler(request: Request, _: MCPExecutionError) -> JSONResponse:
        return safe_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "tool_execution_failed",
            "An error occurred while executing the tool.",
            getattr(request.state, "request_id", str(uuid.uuid4())),
        )

    @app.get("/health/live", response_model=HealthResponse, tags=["operations"])
    async def liveness(request: Request) -> HealthResponse:
        return HealthResponse(status="alive", request_id=request.state.request_id)

    @app.get("/health/ready", response_model=HealthResponse, tags=["operations"])
    async def readiness(request: Request):
        if not app.state.ready:
            return safe_error_response(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "not_ready",
                "The service is not ready.",
                request.state.request_id,
            )
        return HealthResponse(status="ready", request_id=request.state.request_id)

    @app.get("/api/v1/session", response_model=SessionResponse, tags=["session"])
    async def session(identity: Identity = Depends(require_permission("chat:use"))) -> SessionResponse:
        return SessionResponse(subject=identity.subject, permissions=sorted(identity.permissions))

    @app.get("/api/v1/admin/audit-status", tags=["administration"])
    async def audit_status(identity: Identity = Depends(require_permission("admin:diagnostics"))) -> dict[str, str]:
        return {"status": "available", "actor": identity.subject}

    @app.get("/api/v1/admin/metrics", tags=["administration"])
    async def metrics_endpoint(
        identity: Identity = Depends(require_permission("admin:diagnostics")),
    ) -> dict[str, Any]:
        llm_client: LocalLLMClient | None = app.state.llm_client
        if llm_client is not None:
            snapshot = llm_client.metrics()
            avg_latency = (
                round(snapshot.total_latency_seconds / snapshot.completed, 3)
                if snapshot.completed > 0
                else 0.0
            )
            return {
                "in_flight": snapshot.in_flight,
                "queue_depth": snapshot.queue_depth,
                "accepted": snapshot.accepted,
                "rejected": snapshot.rejected,
                "failed": snapshot.failed,
                "completed": snapshot.completed,
                "total_latency_seconds": round(snapshot.total_latency_seconds, 2),
                "avg_latency_seconds": avg_latency,
            }
        return {"status": "llm_client_not_configured"}

    @app.post("/api/v1/chat", response_model=ChatResponse, tags=["chat"])
    async def chat_endpoint(
        request: Request,
        payload: ChatRequest,
        identity: Identity = Depends(require_permission("chat:use")),
    ) -> ChatResponse:
        assistant: IntranetAssistantService | None = app.state.assistant_service
        if assistant is None:
            return safe_error_response(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "service_unavailable",
                "The assistant inference service is not configured or available.",
                request.state.request_id,
            )
        result = assistant.ask(payload.message, identity, request.state.request_id)
        return ChatResponse(
            response=result.response,
            citations=[
                SourceCitationResponse(
                    document_id=c.document_id,
                    filename=c.filename,
                    page=c.page,
                )
                for c in result.citations
            ],
            request_id=request.state.request_id,
        )

    @app.get("/api/v1/mcp/tools", response_model=MCPToolsListResponse, tags=["mcp"])
    async def list_mcp_tools(
        identity: Identity = Depends(require_permission("chat:use")),
    ) -> MCPToolsListResponse:
        descriptors = app.state.tool_registry.list_descriptors()
        return MCPToolsListResponse(
            tools=[
                MCPToolDescriptor(
                    name=d["name"],
                    description=d["description"],
                    parameters=d["parameters"],
                    required_permission=d["required_permission"],
                )
                for d in descriptors
            ]
        )

    @app.post("/api/v1/mcp/tools/{tool_name}", response_model=MCPCallResponse, tags=["mcp"])
    async def call_mcp_tool(
        request: Request,
        tool_name: str,
        payload: MCPCallRequest,
        identity: Identity = Depends(current_identity),
    ) -> MCPCallResponse:
        result = app.state.tool_registry.execute(
            tool_name=tool_name,
            parameters=payload.parameters,
            identity=identity,
            request_id=request.state.request_id,
        )
        return MCPCallResponse(
            tool=tool_name,
            content=result.content,
            citations=[
                SourceCitationResponse(
                    document_id=c.document_id,
                    filename=c.filename,
                    page=c.page,
                )
                for c in result.citations
            ],
            request_id=request.state.request_id,
            truncated=result.truncated,
        )

    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @app.get("/", include_in_schema=False)
        async def serve_index():
            index_path = static_dir / "index.html"
            if index_path.is_file():
                return FileResponse(index_path)
            return JSONResponse({"status": "ready", "service": settings.app_name})

    return app
