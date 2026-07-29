import secrets
import shutil
from pathlib import Path
from typing import Annotated

from fastapi import Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from local_vllm_dashboard.db import BundleRepository
from local_vllm_dashboard.ingest_directory import render_report
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

    def authenticate(token: str) -> None:
        if not secrets.compare_digest(token, ingest_token):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid ingestion token")

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
        authenticate(token)
        uploaded = []
        if archive and archive.filename:
            uploaded.extend(archive_files(await archive.read()))
        for item in files or []:
            if item.filename:
                uploaded.append(UploadedFile(item.filename, await item.read()))
        try:
            preview = stage_upload(tuple(uploaded), staging_root)
        except ValueError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
        confirmation = sessions.create(preview)
        report = render_report(preview.report, preview.root, preview.root)
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
        authenticate(token)
        preview = sessions.pop(confirmation)
        if preview is None:
            raise HTTPException(status.HTTP_410_GONE, "upload preview expired or was already used")
        try:
            result = ingest_preview(preview, BundleRepository(session))
        finally:
            shutil.rmtree(preview.root, ignore_errors=True)
        return templates.TemplateResponse(
            request,
            "upload-result.html",
            {"result": result},
        )
