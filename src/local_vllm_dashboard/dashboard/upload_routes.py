import secrets
import shutil
import tarfile
from pathlib import Path
from typing import Annotated

from fastapi import Depends, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from local_vllm_dashboard.dashboard.upload_view import upload_report_view
from local_vllm_dashboard.db import BundleRepository
from local_vllm_dashboard.upload import UploadedFile, archive_files, ingest_preview, stage_upload
from local_vllm_dashboard.upload_sessions import UploadSessionStore


def register_upload_routes(
    app,
    templates: Jinja2Templates,
    get_session,
    ingest_token: str,
    staging_root: Path,
) -> None:
    sessions = UploadSessionStore(staging_root)

    def error_response(
        request: Request,
        message: str,
        *,
        status_code: int = status.HTTP_422_UNPROCESSABLE_CONTENT,
        details: str | None = None,
    ) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "upload-error.html",
            {"message": message, "details": details},
            status_code=status_code,
        )

    def valid_token(token: str) -> bool:
        return secrets.compare_digest(token, ingest_token)

    @app.get("/upload", response_class=HTMLResponse, name="upload-results")
    def upload_form(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "upload.html", {})

    @app.post("/upload/preview", response_class=HTMLResponse)
    async def upload_preview(
        request: Request,
        token: Annotated[str, Form()],
        archive: Annotated[UploadFile | None, File()] = None,
        files: Annotated[list[UploadFile] | None, File()] = None,
    ) -> HTMLResponse:
        if not valid_token(token):
            return error_response(
                request,
                "The ingestion token was not accepted.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        uploaded = []
        try:
            if archive and archive.filename:
                uploaded.extend(archive_files(await archive.read()))
            for item in files or []:
                if item.filename:
                    uploaded.append(UploadedFile(item.filename, await item.read()))
            preview = stage_upload(tuple(uploaded), staging_root)
        except (ValueError, tarfile.TarError) as error:
            return error_response(request, str(error))
        confirmation = sessions.create(preview)
        report = upload_report_view(preview.report, preview.root)
        return templates.TemplateResponse(
            request,
            "upload-preview.html",
            {
                "confirmation": confirmation,
                "token": token,
                "report": report,
                "preview": preview,
            },
        )

    @app.post("/upload/confirm", response_class=HTMLResponse)
    def upload_confirm(
        request: Request,
        token: Annotated[str, Form()],
        confirmation: Annotated[str, Form()],
        session: Annotated[Session, Depends(get_session)],
    ) -> HTMLResponse:
        if not valid_token(token):
            return error_response(
                request,
                "The ingestion token was not accepted.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        preview = sessions.pop(confirmation)
        if preview is None:
            return error_response(
                request,
                "This upload preview expired or was already used.",
                status_code=status.HTTP_410_GONE,
            )
        try:
            result = ingest_preview(preview, BundleRepository(session))
        finally:
            shutil.rmtree(preview.root, ignore_errors=True)
        return templates.TemplateResponse(
            request,
            "upload-result.html",
            {"result": result},
        )
