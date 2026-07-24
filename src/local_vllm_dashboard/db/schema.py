from sqlalchemy.engine import Engine

from local_vllm_dashboard.db.models import Base


def initialize_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)
