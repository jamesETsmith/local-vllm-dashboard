import hashlib
import secrets
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.orm import Session, sessionmaker

from local_vllm_dashboard.artifacts import ArtifactContent
from local_vllm_dashboard.contracts import Bundle
from local_vllm_dashboard.dashboard import create_dashboard_app
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
    ingest_token: str
    max_request_bytes: int = 4_194_304
    max_artifact_bytes: int = 1_048_576
    upload_staging_dir: Path = Path(".upload-staging")


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
    app.mount(
        "/dashboard",
        create_dashboard_app(
            factory,
            ingest_token=selected_settings.ingest_token,
            upload_staging_dir=selected_settings.upload_staging_dir,
        ),
        name="dashboard",
    )

    @app.get("/", include_in_schema=False)
    def dashboard_redirect() -> RedirectResponse:
        return RedirectResponse("/dashboard/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    @app.get("/favicon.ico", include_in_schema=False, status_code=status.HTTP_204_NO_CONTENT)
    def favicon() -> Response:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    def get_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    def authenticate(authorization: Annotated[str | None, Header()] = None) -> None:
        scheme, _, credential = (authorization or "").partition(" ")
        valid = scheme.lower() == "bearer" and secrets.compare_digest(
            credential,
            selected_settings.ingest_token,
        )
        if not valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid or missing ingestion token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.post(
        "/v1/bundles",
        response_model=IngestResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def ingest_bundle(
        request: Request,
        response: Response,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        _authenticated: Annotated[None, Depends(authenticate)],
        session: Annotated[Session, Depends(get_session)],
        bundle_file: Annotated[UploadFile, File(alias="bundle")],
        artifact_files: Annotated[list[UploadFile] | None, File(alias="artifacts")] = None,
    ) -> IngestResponse:
        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > selected_settings.max_request_bytes:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "request is too large")
        bundle = Bundle.model_validate_json(await bundle_file.read())
        if idempotency_key != bundle.idempotency_key:
            raise HTTPException(status.HTTP_409_CONFLICT, "header and body idempotency keys differ")
        if not bundle.has_valid_idempotency_key():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid idempotency key")
        declarations = {
            (Path(item.path).name, item.role): item for item in bundle.run.source.artifacts
        }
        artifacts = []
        for upload in artifact_files or []:
            content = await upload.read(selected_settings.max_artifact_bytes + 1)
            if len(content) > selected_settings.max_artifact_bytes:
                raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "artifact is too large")
            role = upload.headers.get("X-Artifact-Role", "")
            filename = Path(upload.filename or "").name
            declaration = declarations.get((filename, role))
            digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
            if (
                declaration is None
                or len(content) != declaration.size_bytes
                or digest != declaration.digest
            ):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "artifact does not match declaration",
                )
            artifacts.append(
                ArtifactContent(
                    path=filename,
                    role=role,
                    media_type=upload.content_type or "application/octet-stream",
                    content=content,
                )
            )
        if len(artifacts) != len(declarations):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "declared artifacts are missing",
            )
        try:
            result = BundleRepository(session).save(bundle, tuple(artifacts))
        except IdempotencyConflictError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        if result.status == SaveStatus.DUPLICATE:
            response.status_code = status.HTTP_200_OK
        return IngestResponse(bundle_id=str(result.bundle_id), status=result.status)

    return app
