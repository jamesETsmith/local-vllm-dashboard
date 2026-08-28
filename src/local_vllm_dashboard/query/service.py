from sqlalchemy.orm import Session, sessionmaker

from local_vllm_dashboard.dashboard.models import DashboardFilters
from local_vllm_dashboard.dashboard.repository import DashboardRepository
from local_vllm_dashboard.query.models import (
    ConfigurationFilterOptions,
    ConfigurationFilters,
    ConfigurationPage,
    ConfigurationResult,
)


class QueryService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def configurations(
        self,
        filters: ConfigurationFilters | None = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> ConfigurationPage:
        selected = filters or ConfigurationFilters()
        with self.session_factory() as session:
            data = DashboardRepository(session).load(
                DashboardFilters(
                    hardware=(selected.hardware,) if selected.hardware else (),
                    model=(selected.model,) if selected.model else (),
                    input_tokens=(selected.input_tokens,)
                    if selected.input_tokens is not None
                    else (),
                    output_tokens=(selected.output_tokens,)
                    if selected.output_tokens is not None
                    else (),
                    prefix_cache_tokens=(selected.prefix_cache_tokens,)
                    if selected.prefix_cache_tokens is not None
                    else (),
                    concurrency=(selected.concurrency,) if selected.concurrency is not None else (),
                    precision=(selected.precision,) if selected.precision else (),
                )
            )
        results = tuple(ConfigurationResult.model_validate(item) for item in data.performance)
        return ConfigurationPage(
            items=results[offset : offset + limit],
            total=len(results),
            limit=limit,
            offset=offset,
        )

    def configuration_filters(self) -> ConfigurationFilterOptions:
        with self.session_factory() as session:
            options = DashboardRepository(session).load().options
        return ConfigurationFilterOptions(
            hardware=options.hardware,
            models=options.models,
            input_tokens=options.input_tokens,
            output_tokens=options.output_tokens,
            prefix_cache_tokens=options.prefix_cache_tokens,
            concurrencies=options.concurrencies,
            precisions=options.precisions,
        )
