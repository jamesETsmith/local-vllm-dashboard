import csv
import io
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
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


def query_values(request: Request, name: str) -> tuple[str, ...]:
    return tuple(value for value in request.query_params.getlist(name) if value)


def query_ints(request: Request, name: str) -> tuple[int, ...]:
    values = []
    for value in query_values(request, name):
        try:
            values.append(int(value))
        except ValueError:
            continue
    return tuple(values)


def query_date(request: Request, name: str) -> date | None:
    value = request.query_params.get(name)
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def request_filters(request: Request, *, default_date_range: bool = False) -> DashboardFilters:
    default_end_date = date.today() if default_date_range else None
    default_start_date = default_end_date - timedelta(weeks=4) if default_end_date else None
    return DashboardFilters(
        hardware=query_values(request, "hardware"),
        model=query_values(request, "model"),
        input_tokens=query_ints(request, "input_tokens"),
        output_tokens=query_ints(request, "output_tokens"),
        prefix_cache_tokens=query_ints(request, "prefix_cache_tokens"),
        concurrency=query_ints(request, "concurrency"),
        precision=query_values(request, "precision"),
        task=query_values(request, "task"),
        start_date=(
            query_date(request, "start_date")
            if "start_date" in request.query_params
            else default_start_date
        ),
        end_date=(
            query_date(request, "end_date")
            if "end_date" in request.query_params
            else default_end_date
        ),
    )


def create_dashboard_app(
    factory: sessionmaker[Session],
    *,
    ingest_token: str,
    upload_staging_dir: Path,
    public_url: str | None = None,
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
    ) -> HTMLResponse:
        filters = request_filters(request, default_date_range=True)
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

    @app.get("/comparison", response_class=HTMLResponse, name="dashboard-comparison")
    def comparison_page(
        request: Request,
        session: Annotated[Session, Depends(get_session)],
    ) -> HTMLResponse:
        data = DashboardRepository(session).load(DashboardFilters())
        chart = performance_chart(data.performance)
        return TEMPLATES.TemplateResponse(
            request,
            "comparison.html",
            {
                "comparison_chart": chart,
                "comparison_chart_json": chart_json_data(chart),
            },
        )

    @app.get("/help", response_class=HTMLResponse, name="dashboard-help")
    def help_page(request: Request) -> HTMLResponse:
        base_url = public_url or str(request.base_url).removesuffix("/dashboard/")
        help_html, help_toc = usage_html(base_url)
        return TEMPLATES.TemplateResponse(
            request,
            "help.html",
            {"help_html": help_html, "help_toc": help_toc},
        )

    @app.get("/raw-data.csv", name="raw-data-download")
    def raw_data_download(
        request: Request,
        session: Annotated[Session, Depends(get_session)],
    ) -> Response:
        filters = request_filters(request)
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
