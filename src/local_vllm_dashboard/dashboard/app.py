from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, sessionmaker

from local_vllm_dashboard.dashboard.chart import chart_json_data, performance_chart
from local_vllm_dashboard.dashboard.models import DashboardFilters
from local_vllm_dashboard.dashboard.repository import DashboardRepository

ROOT = Path(__file__).parent
TEMPLATES = Jinja2Templates(directory=ROOT / "templates")


def optional_int(value: str | None) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def create_dashboard_app(factory: sessionmaker[Session]) -> FastAPI:
    app = FastAPI(title="Local vLLM Dashboard")
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="dashboard-static")

    def get_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    @app.get("/", response_class=HTMLResponse, name="dashboard")
    def dashboard(
        request: Request,
        session: Annotated[Session, Depends(get_session)],
        tab: Literal["performance", "accuracy", "runs"] = "performance",
        hardware: Annotated[str | None, Query()] = None,
        model: Annotated[str | None, Query()] = None,
        input_tokens: Annotated[str | None, Query()] = None,
        output_tokens: Annotated[str | None, Query()] = None,
        concurrency: Annotated[str | None, Query()] = None,
        precision: Annotated[str | None, Query()] = None,
        task: Annotated[str | None, Query()] = None,
    ) -> HTMLResponse:
        filters = DashboardFilters(
            hardware=hardware or None,
            model=model or None,
            input_tokens=optional_int(input_tokens),
            output_tokens=optional_int(output_tokens),
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
