from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.orm import Session, sessionmaker

from local_vllm_dashboard.contracts import Bundle
from local_vllm_dashboard.db import (
    BundleRepository,
    IdempotencyConflictError,
    SaveStatus,
    make_engine,
    make_session_factory,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DASHBOARD_")

    database_url: str
    max_request_bytes: int = 1_048_576


class IngestResponse(BaseModel):
    bundle_id: str
    status: SaveStatus


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    selected_settings = settings or Settings()
    factory = session_factory or make_session_factory(make_engine(selected_settings.database_url))
    app = FastAPI(title="Local vLLM Dashboard Ingestion API")

    def get_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    @app.post(
        "/v1/bundles",
        response_model=IngestResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def ingest_bundle(
        request: Request,
        response: Response,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        session: Annotated[Session, Depends(get_session)],
    ) -> IngestResponse:
        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > selected_settings.max_request_bytes:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "request is too large")
        body = await request.body()
        if len(body) > selected_settings.max_request_bytes:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "request is too large")
        bundle = Bundle.model_validate_json(body)
        if idempotency_key != bundle.idempotency_key:
            raise HTTPException(status.HTTP_409_CONFLICT, "header and body idempotency keys differ")
        if not bundle.has_valid_idempotency_key():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid idempotency key")
        try:
            result = BundleRepository(session).save(bundle)
        except IdempotencyConflictError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        if result.status == SaveStatus.DUPLICATE:
            response.status_code = status.HTTP_200_OK
        return IngestResponse(bundle_id=str(result.bundle_id), status=result.status)

    return app
