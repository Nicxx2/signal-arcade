from __future__ import annotations

import asyncio
import base64
import secrets
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypeAlias
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response

from . import __version__
from .config import Settings, load_settings
from .models import (
    AiDecisionMode,
    LearningMode,
    ProfileTransitionStrategy,
    QuoteCurrency,
    RiskMode,
)
from .orchestrator import Orchestrator
from .provider_settings import ProviderConfiguration, validate_endpoint
from .providers.http import ProviderError
from .redaction import redact_secrets
from .risk_profiles import DrawdownPolicy, season_profile_catalog

_DATABASE_HEALTH_TIMEOUT_SECONDS = 0.5

if TYPE_CHECKING:
    RequestType: TypeAlias = Request[Any]  # noqa: UP040 - mypy 1.8 lacks PEP 695 support
    WebSocketType: TypeAlias = WebSocket[Any]  # noqa: UP040 - see above
else:
    RequestType = Request
    WebSocketType = WebSocket


class BasicAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, password: str | None) -> None:
        super().__init__(app)
        self.password = password

    async def dispatch(self, request: RequestType, call_next: RequestResponseEndpoint) -> Response:
        if not self.password or request.url.path == "/api/v1/health":
            return await call_next(request)
        if not _valid_basic_auth(request.headers.get("authorization"), self.password):
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Signal Arcade"'},
            )
        return await call_next(request)


class SameOriginMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: RequestType, call_next: RequestResponseEndpoint) -> Response:
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin and not _same_origin(origin, str(request.url)):
                return JSONResponse(
                    {"detail": "cross-origin state change rejected"}, status_code=403
                )
        return await call_next(request)


def _same_origin(origin: str, target: str) -> bool:
    try:
        source = urlparse(origin)
        destination = urlparse(target)
        destination_scheme = {"ws": "http", "wss": "https"}.get(
            destination.scheme, destination.scheme
        )
        source_port = source.port or (443 if source.scheme == "https" else 80)
        destination_port = destination.port or (443 if destination_scheme == "https" else 80)
    except ValueError:
        return False
    if source.scheme not in {"http", "https"} or source.scheme != destination_scheme:
        return False
    loopback_names = {"127.0.0.1", "localhost", "::1"}
    hosts_match = source.hostname == destination.hostname or (
        source.hostname in loopback_names and destination.hostname in loopback_names
    )
    return bool(hosts_match and source_port == destination_port)


def _valid_basic_auth(header: str | None, password: str) -> bool:
    if not header or not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
        _, supplied = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        return False
    return secrets.compare_digest(supplied, password)


class ModeRequest(BaseModel):
    demo_mode: bool


class RiskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: RiskMode
    drawdown_policy: DrawdownPolicy = Field(default_factory=DrawdownPolicy)
    transition_strategy: ProfileTransitionStrategy = ProfileTransitionStrategy.FINISH_SAFELY
    quote_currency: QuoteCurrency | None = None
    starting_amount: Decimal | None = Field(default=None, gt=0, le=1_000_000_000)


class AutoNewSeasonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    grace_hours: int | None = Field(default=None, ge=1, le=24)


class LearningRequest(BaseModel):
    mode: LearningMode


class AiDecisionModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: AiDecisionMode


class CoachContributionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class CoachResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class AiModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:/-]+$")


class ResetRequest(BaseModel):
    confirmation: str


class UpgradePreparationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: str


class PortfolioSetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote_currency: QuoteCurrency
    starting_amount: Decimal = Field(gt=0, le=1_000_000_000)
    risk_mode: RiskMode | None = None
    drawdown_policy: DrawdownPolicy = Field(default_factory=DrawdownPolicy)


def _portfolio_starting_minor(quote_currency: QuoteCurrency, starting_amount: Decimal) -> int:
    decimals = 9 if quote_currency == QuoteCurrency.SOL else 6
    scaled = starting_amount * (Decimal(10) ** decimals)
    if scaled != scaled.to_integral_value():
        raise HTTPException(
            status_code=422,
            detail=f"{quote_currency.value} supports at most {decimals} decimals",
        )
    if quote_currency == QuoteCurrency.SOL and starting_amount > 1_000_000:
        raise HTTPException(status_code=422, detail="SOL bankroll is unreasonably large")
    return int(scaled)


class StorageSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_database_gb: float = Field(ge=0.5, le=100)
    raw_trade_retention_hours: int = Field(ge=1, le=720)


ProviderSecretKey = Literal[
    "solana_http",
    "solana_ws",
    "jupiter_base",
    "jupiter_api_key",
    "ollama_url",
    "ollama_model",
]


class ProviderSecretChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    solana_http: str | None = Field(default=None, min_length=1, max_length=4_096)
    solana_ws: str | None = Field(default=None, min_length=1, max_length=4_096)
    jupiter_base: str | None = Field(default=None, min_length=1, max_length=4_096)
    jupiter_api_key: str | None = Field(default=None, min_length=1, max_length=4_096)
    ollama_url: str | None = Field(default=None, min_length=1, max_length=4_096)
    ollama_model: str | None = Field(default=None, min_length=1, max_length=200)
    clear: list[ProviderSecretKey] = Field(default_factory=list, max_length=6)


class ProviderSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configuration: ProviderConfiguration
    secrets: ProviderSecretChanges = Field(default_factory=ProviderSecretChanges)


def _secure_secret_transport(request: RequestType) -> bool:
    host = (request.url.hostname or "").lower()
    return request.url.scheme == "https" or host in {"127.0.0.1", "localhost", "::1"}


def _validated_provider_changes(body: ProviderSecretChanges) -> dict[str, str | None]:
    changes = body.model_dump(exclude_none=True, exclude={"clear"})
    overlap = set(changes).intersection(body.clear)
    if overlap:
        raise HTTPException(status_code=422, detail="a provider value cannot be set and cleared")
    for clear_key in body.clear:
        changes[clear_key] = None
    validators: dict[str, Callable[[str], str]] = {
        "solana_http": lambda value: validate_endpoint(
            value,
            allowed_schemes={"http", "https"},
            local_plaintext_schemes={"http"},
        ),
        "solana_ws": lambda value: validate_endpoint(
            value,
            allowed_schemes={"ws", "wss"},
            local_plaintext_schemes={"ws"},
        ),
        "jupiter_base": lambda value: validate_endpoint(
            value,
            allowed_schemes={"http", "https"},
            local_plaintext_schemes={"http"},
        ),
        "ollama_url": lambda value: validate_endpoint(
            value,
            allowed_schemes={"http", "https"},
        ),
    }
    for endpoint_key, validator in validators.items():
        value = changes.get(endpoint_key)
        if isinstance(value, str):
            try:
                changes[endpoint_key] = validator(value)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    for text_key in ("jupiter_api_key", "ollama_model"):
        value = changes.get(text_key)
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped or any(character in stripped for character in ("\r", "\n", "\0")):
                raise HTTPException(status_code=422, detail=f"{text_key} is invalid")
            changes[text_key] = stripped
    return changes


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    orchestrator = Orchestrator(settings)

    async def normal_operation() -> AsyncIterator[None]:
        """Serialize mutations with the upgrade boundary and reject them once it is crossed."""

        async with orchestrator.maintenance_mutation_lock:
            if orchestrator.maintenance_active:
                raise HTTPException(
                    status_code=409,
                    detail="the app is prepared for an update; cancel preparation or restart it",
                )
            yield

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await orchestrator.start()
        try:
            yield
        finally:
            await orchestrator.stop()

    app = FastAPI(
        title="Signal Arcade",
        version=__version__,
        description="Explainable, paper-only Solana market simulation.",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.state.orchestrator = orchestrator
    app.add_middleware(GZipMiddleware, minimum_size=1_024, compresslevel=4)
    app.add_middleware(SameOriginMiddleware)
    app.add_middleware(BasicAuthMiddleware, password=settings.admin_password)

    @app.get("/api/v1/health")
    async def health() -> dict[str, Any]:
        try:
            async with asyncio.timeout(_DATABASE_HEALTH_TIMEOUT_SECONDS):
                database_ok = await asyncio.to_thread(orchestrator.database.health_check)
        except TimeoutError:
            # A pathological filesystem/SQLite wait must never pin the server's event loop. The
            # container remains reachable and reports the database unhealthy while the next probe
            # gets an independent chance to recover.
            database_ok = False
        background_tasks = orchestrator.background_task_status()
        event_pipeline = orchestrator.event_pipeline_status()
        return {
            "ok": bool(
                database_ok and orchestrator.service_running and all(background_tasks.values())
            ),
            "running": orchestrator.running,
            "service_running": orchestrator.service_running,
            "database_ok": database_ok,
            "background_tasks": background_tasks,
            # Degraded feed quality is visible without turning a live process into a Docker
            # restart loop. `ok` remains a liveness signal.
            "degraded": event_pipeline["degraded"],
            "degraded_reasons": event_pipeline["degraded_reasons"],
            "event_pipeline": event_pipeline,
            "paper_only": True,
            "version": __version__,
        }

    @app.get("/api/v1/snapshot")
    async def snapshot() -> dict[str, Any]:
        # Snapshot assembly reads several tables. Keep those reads away from the HTTP event loop
        # while preserving a fill/portfolio boundary for an internally consistent P/L view.
        return await orchestrator.snapshot_view()

    @app.put("/api/v1/storage-settings", dependencies=[Depends(normal_operation)])
    async def update_storage_settings(body: StorageSettingsRequest) -> dict[str, Any]:
        result = await orchestrator.configure_storage(
            int(body.max_database_gb * 1024**3),
            body.raw_trade_retention_hours,
        )
        orchestrator.invalidate_snapshot_cache()
        return result

    @app.get("/api/v1/leaderboard")
    async def leaderboard(
        sort: Literal["profit", "loss", "recent"] = Query(default="profit"),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        return await orchestrator.leaderboard_view(sort=sort, limit=limit)

    @app.get("/api/v1/seasons")
    async def seasons() -> dict[str, Any]:
        return await orchestrator.seasons_view()

    @app.get("/api/v1/decisions/{decision_id}")
    async def decision(decision_id: str) -> dict[str, Any]:
        saved = orchestrator.database.get_decision(decision_id)
        if saved is None:
            raise HTTPException(status_code=404, detail="decision not found")
        return saved.model_dump(mode="json")

    @app.put("/api/v1/risk", dependencies=[Depends(normal_operation)])
    async def set_risk(body: RiskRequest) -> dict[str, Any]:
        if (body.quote_currency is None) != (body.starting_amount is None):
            raise HTTPException(
                status_code=422,
                detail="quote currency and starting amount must be changed together",
            )
        target_minor = (
            _portfolio_starting_minor(body.quote_currency, body.starting_amount)
            if body.quote_currency is not None and body.starting_amount is not None
            else None
        )
        try:
            result = await orchestrator.request_season_profile(
                body.mode,
                body.drawdown_policy,
                transition_strategy=body.transition_strategy,
                target_quote_currency=body.quote_currency,
                target_starting_minor=target_minor,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        orchestrator.invalidate_snapshot_cache()
        return {"mode": body.mode.value, **result}

    @app.get("/api/v1/risk-profiles")
    async def risk_profiles() -> dict[str, Any]:
        return {"schema_version": 1, "profiles": season_profile_catalog()}

    @app.put("/api/v1/season-automation", dependencies=[Depends(normal_operation)])
    async def set_season_automation(body: AutoNewSeasonRequest) -> dict[str, Any]:
        try:
            result = await orchestrator.configure_auto_new_season(
                body.enabled,
                body.grace_hours,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        orchestrator.invalidate_snapshot_cache()
        return result

    @app.put("/api/v1/learning", dependencies=[Depends(normal_operation)])
    async def set_learning(body: LearningRequest) -> dict[str, Any]:
        try:
            orchestrator.set_learning_mode(body.mode)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        orchestrator.invalidate_snapshot_cache()
        return orchestrator.learning.status(demo_mode=orchestrator.demo_mode)

    @app.get("/api/v1/ai-lab")
    async def ai_lab() -> dict[str, Any]:
        await orchestrator.ai_lab.refresh_models()
        return await asyncio.to_thread(orchestrator.ai_lab.status)

    @app.put("/api/v1/ai-lab/mode", dependencies=[Depends(normal_operation)])
    async def set_ai_mode(body: AiDecisionModeRequest) -> dict[str, Any]:
        try:
            orchestrator.set_ai_decision_mode(body.mode)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        orchestrator.invalidate_snapshot_cache()
        return orchestrator.ai_lab.status()

    @app.put(
        "/api/v1/ai-lab/coach-contribution",
        dependencies=[Depends(normal_operation)],
    )
    async def set_coach_contribution(body: CoachContributionRequest) -> dict[str, Any]:
        try:
            orchestrator.set_coach_contribution_enabled(body.enabled)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        orchestrator.invalidate_snapshot_cache()
        return orchestrator.coach.status()

    @app.put(
        "/api/v1/ai-lab/coach-research",
        dependencies=[Depends(normal_operation)],
    )
    async def set_coach_research(body: CoachResearchRequest) -> dict[str, Any]:
        try:
            orchestrator.set_coach_research_enabled(body.enabled)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        orchestrator.invalidate_snapshot_cache()
        return orchestrator.coach.status()

    @app.put("/api/v1/ai-lab/model", dependencies=[Depends(normal_operation)])
    async def select_ai_model(body: AiModelRequest) -> dict[str, Any]:
        try:
            result = orchestrator.select_ai_model(body.model)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        orchestrator.invalidate_snapshot_cache()
        return result

    @app.post("/api/v1/ai-lab/models/pull", dependencies=[Depends(normal_operation)])
    async def pull_ai_model(body: AiModelRequest) -> dict[str, Any]:
        try:
            result = orchestrator.download_ai_model(body.model)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        orchestrator.invalidate_snapshot_cache()
        return result

    @app.delete("/api/v1/ai-lab/models", dependencies=[Depends(normal_operation)])
    async def remove_ai_model(body: AiModelRequest) -> dict[str, Any]:
        try:
            result = await orchestrator.remove_ai_model(body.model)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ProviderError as exc:
            raise HTTPException(status_code=502, detail=redact_secrets(exc)) from exc
        orchestrator.invalidate_snapshot_cache()
        return result

    @app.put("/api/v1/mode", dependencies=[Depends(normal_operation)])
    async def set_mode(body: ModeRequest) -> dict[str, bool]:
        try:
            await orchestrator.set_demo_mode(body.demo_mode)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        orchestrator.invalidate_snapshot_cache()
        return {"demo_mode": body.demo_mode}

    @app.get("/api/v1/provider-settings")
    async def provider_settings() -> dict[str, Any]:
        return orchestrator.provider_settings_view()

    @app.put("/api/v1/provider-settings", dependencies=[Depends(normal_operation)])
    async def update_provider_settings(
        body: ProviderSettingsRequest, request: RequestType
    ) -> dict[str, Any]:
        changes = _validated_provider_changes(body.secrets)
        if any(value is not None for value in changes.values()) and not _secure_secret_transport(
            request
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Provider secrets can only be changed through HTTPS or a localhost URL. "
                    "Open Signal Arcade locally or put it behind HTTPS."
                ),
            )
        try:
            result = await orchestrator.configure_providers(body.configuration, changes)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        orchestrator.invalidate_snapshot_cache()
        return result

    @app.post("/api/v1/portfolio/setup", dependencies=[Depends(normal_operation)])
    async def setup_portfolio(body: PortfolioSetupRequest) -> dict[str, Any]:
        starting_minor = _portfolio_starting_minor(
            body.quote_currency,
            body.starting_amount,
        )
        try:
            await orchestrator.setup_portfolio(
                body.quote_currency,
                starting_minor,
                risk_mode=body.risk_mode,
                drawdown_policy=body.drawdown_policy,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        orchestrator.invalidate_snapshot_cache()
        return {
            "initialized": True,
            "quote_currency": body.quote_currency.value,
            "starting_minor": starting_minor,
            "running": False,
        }

    @app.post("/api/v1/engine/start", dependencies=[Depends(normal_operation)])
    async def start_engine() -> dict[str, bool]:
        try:
            await orchestrator.resume_trading()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        orchestrator.invalidate_snapshot_cache()
        return {"running": True}

    @app.post("/api/v1/engine/stop", dependencies=[Depends(normal_operation)])
    async def stop_engine() -> dict[str, Any]:
        try:
            cancelled = await orchestrator.pause_trading()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        orchestrator.invalidate_snapshot_cache()
        return {"running": False, "cancelled_pending_orders": cancelled}

    @app.get("/api/v1/maintenance-operation")
    async def maintenance_operation() -> dict[str, Any] | None:
        return orchestrator.maintenance_operation_status()

    @app.post("/api/v1/maintenance/prepare", status_code=202)
    async def prepare_for_upgrade(body: UpgradePreparationRequest) -> dict[str, Any]:
        if body.confirmation != "PREPARE FOR UPGRADE":
            raise HTTPException(status_code=400, detail="confirmation phrase did not match")
        try:
            return await orchestrator.begin_upgrade_preparation()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/maintenance/cancel")
    async def cancel_upgrade_preparation() -> dict[str, Any]:
        try:
            return await orchestrator.cancel_upgrade_preparation()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/v1/season-operation")
    async def season_operation() -> dict[str, Any] | None:
        return orchestrator.season_operation_status()

    @app.post(
        "/api/v1/reset",
        status_code=202,
        dependencies=[Depends(normal_operation)],
    )
    async def reset(body: ResetRequest) -> dict[str, Any]:
        if body.confirmation != "RESET PAPER PORTFOLIO":
            raise HTTPException(status_code=400, detail="confirmation phrase did not match")
        try:
            operation = await orchestrator.begin_reset_portfolio()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        orchestrator.invalidate_snapshot_cache()
        return operation

    @app.post(
        "/api/v1/decisions/{decision_id}/explain",
        dependencies=[Depends(normal_operation)],
    )
    async def explain(decision_id: str) -> dict[str, Any]:
        result = await orchestrator.explain(decision_id)
        if result is None:
            raise HTTPException(status_code=404, detail="decision not found")
        return result

    @app.websocket("/ws")
    async def websocket(websocket: WebSocketType) -> None:
        origin = websocket.headers.get("origin")
        if origin and not _same_origin(origin, str(websocket.url)):
            await websocket.close(code=4403)
            return
        if settings.admin_password and not _valid_basic_auth(
            websocket.headers.get("authorization"), settings.admin_password
        ):
            await websocket.close(code=4401)
            return
        await websocket.accept()
        try:
            async for message in orchestrator.bus.subscribe():
                await websocket.send_json(message)
        except WebSocketDisconnect:
            return

    frontend = settings.frontend_dir or (Path.cwd() / "frontend" / "dist")
    if not frontend.exists():
        frontend = Path(__file__).parents[2] / "frontend" / "dist"
    assets = frontend / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend_route(path: str) -> Response:
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        index = frontend / "index.html"
        if index.exists():
            return FileResponse(index)
        return JSONResponse(
            {
                "message": (
                    "Signal Arcade API is running; build the frontend for the web interface."
                ),
                "docs": "/api/docs",
            }
        )

    return app
