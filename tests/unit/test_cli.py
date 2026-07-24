from local_vllm_dashboard.cli import build_parser


def test_unified_cli_exposes_database_initialization() -> None:
    args = build_parser().parse_args(["init-db"])

    assert args.command == "init-db"
