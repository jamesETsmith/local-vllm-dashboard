from pathlib import Path
from unittest.mock import Mock

from local_vllm_dashboard.api import Settings
from local_vllm_dashboard.cli import build_parser, serve_dashboard


def test_unified_cli_exposes_database_initialization() -> None:
    parser = build_parser()
    args = parser.parse_args(["init-db"])

    assert parser.prog == "local-vllm-dashboard"
    assert args.command == "init-db"


def test_unified_cli_exposes_initialized_server_startup() -> None:
    args = build_parser().parse_args(
        [
            "serve",
            "--host",
            "192.0.2.10",
            "--port",
            "8010",
            "--public-url",
            "http://192.0.2.10:8010",
        ]
    )

    assert args.command == "serve"
    assert args.host == "192.0.2.10"
    assert args.port == 8010
    assert args.public_url == "http://192.0.2.10:8010"


def test_serve_initializes_database_before_starting_server(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("DASHBOARD_INGEST_TOKEN", "test-token")
    events: list[str] = []
    application = object()
    initialize = Mock(side_effect=lambda _engine: events.append("initialize"))
    create_application = Mock(return_value=application)
    run = Mock(side_effect=lambda *_args, **_kwargs: events.append("serve"))

    serve_dashboard(
        host="192.0.2.10",
        port=8010,
        public_url="http://192.0.2.10:8010",
        initialize=initialize,
        create_application=create_application,
        run=run,
    )

    assert events == ["initialize", "serve"]
    settings = create_application.call_args.args[0]
    assert settings.public_url == "http://192.0.2.10:8010"
    assert run.call_args.args == (application,)
    assert run.call_args.kwargs == {"host": "192.0.2.10", "port": 8010}


def test_settings_load_dotenv_without_shell_sourcing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    Path(".env").write_text(
        "DASHBOARD_DATABASE_URL=sqlite+pysqlite:///./dashboard.db\n"
        "DASHBOARD_INGEST_TOKEN=test-token\n"
        "DASHBOARD_PUBLIC_URL=http://192.0.2.10:8010\n",
        encoding="utf-8",
    )

    settings = Settings()

    assert settings.database_url == "sqlite+pysqlite:///./dashboard.db"
    assert len(settings.ingest_token) == 10
    assert settings.public_url == "http://192.0.2.10:8010"
