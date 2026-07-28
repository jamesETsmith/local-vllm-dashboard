from local_vllm_dashboard.cli import build_parser


def test_unified_cli_exposes_database_initialization() -> None:
    parser = build_parser()
    args = parser.parse_args(["init-db"])

    assert parser.prog == "local-vllm-dashboard"
    assert args.command == "init-db"
