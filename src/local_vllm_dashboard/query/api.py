from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from local_vllm_dashboard.query.models import (
    ConfigurationFilterOptions,
    ConfigurationFilters,
    ConfigurationPage,
    PageLimit,
    PageOffset,
    ReproductionResult,
)
from local_vllm_dashboard.query.service import QueryService


def create_query_router(service: QueryService) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["query"])

    @router.get("/configurations", response_model=ConfigurationPage)
    def configurations(
        hardware: Annotated[str | None, Query()] = None,
        model: Annotated[str | None, Query()] = None,
        input_tokens: Annotated[int | None, Query(ge=0)] = None,
        output_tokens: Annotated[int | None, Query(ge=0)] = None,
        prefix_cache_tokens: Annotated[int | None, Query(ge=0)] = None,
        concurrency: Annotated[int | None, Query(ge=1)] = None,
        precision: Annotated[str | None, Query()] = None,
        limit: PageLimit = 50,
        offset: PageOffset = 0,
    ) -> ConfigurationPage:
        return service.configurations(
            ConfigurationFilters(
                hardware=hardware,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                prefix_cache_tokens=prefix_cache_tokens,
                concurrency=concurrency,
                precision=precision,
            ),
            limit=limit,
            offset=offset,
        )

    @router.get("/configuration-filters", response_model=ConfigurationFilterOptions)
    def configuration_filters() -> ConfigurationFilterOptions:
        return service.configuration_filters()

    @router.get(
        "/configurations/{bundle_id}/reproduction",
        response_model=ReproductionResult,
    )
    def reproduction(bundle_id: UUID) -> ReproductionResult:
        result = service.reproduction(bundle_id)
        if result is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "bundle not found")
        return result

    return router
