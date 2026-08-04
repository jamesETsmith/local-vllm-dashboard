import csv
import io
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, sessionmaker

from local_vllm_dashboard.dashboard.chart import chart_json_data, performance_chart
from local_vllm_dashboard.dashboard.models import DashboardFilters
from local_vllm_dashboard.dashboard.repository import DashboardRepository
from local_vllm_dashboard.dashboard.upload_routes import register_upload_routes
from local_vllm_dashboard.usage_docs import usage_html

ROOT = Path(__file__).parent
TEMPLATES = Jinja2Templates(directory=ROOT / "templates")


def optional_int(value: str | None) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def create_dashboard_app(
    factory: sessionmaker[Session],
    *,
    ingest_token: str,
    upload_staging_dir: Path,
) -> FastAPI:
    app = FastAPI(title="Local vLLM Dashboard")
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="dashboard-static")

    def get_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    register_upload_routes(
        app,
        TEMPLATES,
        get_session,
        ingest_token,
        upload_staging_dir,
    )

    @app.get("/", response_class=HTMLResponse, name="dashboard")
    def dashboard(
        request: Request,
        session: Annotated[Session, Depends(get_session)],
        tab: Literal["performance", "accuracy", "runs"] = "performance",
        hardware: Annotated[str | None, Query()] = None,
        model: Annotated[str | None, Query()] = None,
        input_tokens: Annotated[str | None, Query()] = None,
        output_tokens: Annotated[str | None, Query()] = None,
        prefix_cache_tokens: Annotated[str | None, Query()] = None,
        concurrency: Annotated[str | None, Query()] = None,
        precision: Annotated[str | None, Query()] = None,
        task: Annotated[str | None, Query()] = None,
    ) -> HTMLResponse:
        filters = DashboardFilters(
            hardware=hardware or None,
            model=model or None,
            input_tokens=optional_int(input_tokens),
            output_tokens=optional_int(output_tokens),
            prefix_cache_tokens=optional_int(prefix_cache_tokens),
            concurrency=optional_int(concurrency),
            precision=precision or None,
            task=task or None,
        )
        data = DashboardRepository(session).load(filters)
        chart = performance_chart(data.performance)
        return TEMPLATES.TemplateResponse(
            request,
            "dashboard.html",
            {
                "tab": tab,
                "filters": filters,
                "data": data,
                "performance_chart": chart,
                "performance_chart_json": chart_json_data(chart),
            },
        )

    @app.get("/help", response_class=HTMLResponse, name="dashboard-help")
    def help_page(request: Request) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            request,
            "help.html",
            {"help_html": usage_html(str(request.base_url).removesuffix("/dashboard/"))},
        )

    @app.get("/raw-data.csv", name="raw-data-download")
    def raw_data_download(
        session: Annotated[Session, Depends(get_session)],
        hardware: Annotated[str | None, Query()] = None,
        model: Annotated[str | None, Query()] = None,
    ) -> Response:
        filters = DashboardFilters(hardware=hardware or None, model=model or None)
        rows = DashboardRepository(session).load(filters).run_data
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            (
                "completed_at",
                "vllm_image",
                "vllm_commit",
                "dependency_commits",
                "hardware",
                "accelerator_count",
                "model",
                "precision",
                "tensor_parallel_size",
                "data_parallel_size",
                "expert_parallel",
                "input_tokens",
                "output_tokens",
                "prefix_cache_tokens",
                "concurrency",
                "completed_requests",
                "failed_requests",
                "total_token_throughput_per_gpu",
                "output_token_throughput_per_gpu",
                "request_throughput_per_gpu",
                "mean_ttft_s",
                "p99_ttft_s",
                "mean_tpot_s",
                "p99_tpot_s",
                "mean_itl_s",
                "p99_itl_s",
                "mean_e2el_s",
                "p99_e2el_s",
                "bundle_id",
            )
        )
        for row in rows:
            writer.writerow(
                (
                    row.completed_at.isoformat(),
                    row.vllm_image,
                    row.vllm_commit,
                    ";".join(f"{name}={revision}" for name, revision in row.dependency_revisions),
                    row.hardware,
                    row.accelerator_count,
                    row.model,
                    row.precision,
                    row.tensor_parallel_size,
                    row.data_parallel_size,
                    row.expert_parallel,
                    row.input_tokens,
                    row.output_tokens,
                    row.prefix_cache_tokens,
                    row.concurrency,
                    row.completed_requests,
                    row.failed_requests,
                    row.total_token_throughput_per_gpu,
                    row.output_token_throughput_per_gpu,
                    row.request_throughput_per_gpu,
                    row.mean_ttft,
                    row.p99_ttft,
                    row.mean_tpot,
                    row.p99_tpot,
                    row.mean_itl,
                    row.p99_itl,
                    row.mean_e2el,
                    row.p99_e2el,
                    row.bundle_id,
                )
            )
        return Response(
            output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="vllm-raw-data.csv"'},
        )

    @app.get("/runs/{bundle_id}", response_class=HTMLResponse, name="run-detail")
    def run_detail(
        request: Request,
        bundle_id: UUID,
        session: Annotated[Session, Depends(get_session)],
    ) -> HTMLResponse:
        detail = DashboardRepository(session).detail(bundle_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="run not found")
        return TEMPLATES.TemplateResponse(request, "run-detail.html", {"detail": detail})

    return app
