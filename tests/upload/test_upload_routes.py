import io
import tarfile
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from local_vllm_dashboard.api import Settings, create_app
from local_vllm_dashboard.db import Base, make_session_factory

FIXTURES = Path(__file__).parents[1] / "fixtures" / "perf_eval"


def client(tmp_path: Path) -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        ingest_token="test-token",
        upload_staging_dir=tmp_path,
    )
    return TestClient(create_app(settings, factory))


def archive() -> bytes:
    buffer = io.BytesIO()
    paths = (
        FIXTURES / "prefix_cache_workload.yaml",
        FIXTURES / "prefix_cache_partial_failure_bench.json",
    )
    with tarfile.open(fileobj=buffer, mode="w:gz") as output:
        for path in paths:
            content = path.read_bytes()
            name = "workloads/demo.yaml" if path.suffix == ".yaml" else "results/demo/bench.json"
            info = tarfile.TarInfo(name)
            info.size = len(content)
            output.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def test_upload_requires_token(tmp_path: Path) -> None:
    with client(tmp_path) as dashboard:
        response = dashboard.post(
            "/dashboard/upload/preview",
            data={"token": "wrong"},
            files={"archive": ("results.tar.gz", archive(), "application/gzip")},
        )

    assert response.status_code == 401


def test_upload_validation_error_renders_clear_html(tmp_path: Path) -> None:
    bad_archive = io.BytesIO()
    with tarfile.open(fileobj=bad_archive, mode="w:gz") as output:
        info = tarfile.TarInfo("link.yaml")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        output.addfile(info)

    with client(tmp_path) as dashboard:
        response = dashboard.post(
            "/dashboard/upload/preview",
            data={"token": "test-token"},
            files={
                "archive": (
                    "results.tar.gz",
                    bad_archive.getvalue(),
                    "application/gzip",
                )
            },
        )

    assert response.status_code == 422
    assert "Upload could not be processed" in response.text
    assert "unsupported archive member: link.yaml" in response.text
    assert "Internal Server Error" not in response.text


def test_archive_preview_then_confirmation(tmp_path: Path) -> None:
    with client(tmp_path) as dashboard:
        preview = dashboard.post(
            "/dashboard/upload/preview",
            data={"token": "test-token"},
            files={"archive": ("results.tar.gz", archive(), "application/gzip")},
        )
        marker = 'name="confirmation" value="'
        confirmation = preview.text.split(marker, 1)[1].split('"', 1)[0]
        result = dashboard.post(
            "/dashboard/upload/confirm",
            data={"token": "test-token", "confirmation": confirmation},
        )
        dashboard_page = dashboard.get("/dashboard/")

    assert preview.status_code == 200
    assert "matched" in preview.text
    assert "upload-summary" in preview.text
    assert "upload-config-list" in preview.text
    assert result.status_code == 200
    assert "Accepted 1" in result.text
    assert "prefix-cache-performance-mi355x" in dashboard_page.text
