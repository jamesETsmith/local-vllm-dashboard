import argparse
import os
from pathlib import Path

from local_vllm_dashboard.adapter import build_performance_bundle
from local_vllm_dashboard.api import Settings
from local_vllm_dashboard.artifacts import artifact_contents
from local_vllm_dashboard.contracts import Bundle
from local_vllm_dashboard.db import initialize_schema, make_engine
from local_vllm_dashboard.ingest_directory import ingest_directories, render_report
from local_vllm_dashboard.publisher import Publisher


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="benchmark-results")
    commands = parser.add_subparsers(dest="command", required=True)

    adapt = commands.add_parser("adapt-perf")
    adapt.add_argument("--recipe", type=Path, required=True)
    adapt.add_argument("--result", type=Path, required=True)
    adapt.add_argument("--output", type=Path, required=True)

    publish = commands.add_parser("publish")
    publish.add_argument("--bundle", type=Path, required=True)
    publish.add_argument("--artifact", type=Path, action="append", default=[])
    publish.add_argument("--endpoint", required=True)
    publish.add_argument("--token")

    adapt_publish = commands.add_parser("adapt-and-publish")
    adapt_publish.add_argument("--recipe", type=Path, required=True)
    adapt_publish.add_argument("--result", type=Path, required=True)
    adapt_publish.add_argument("--endpoint", required=True)
    adapt_publish.add_argument("--token")

    ingest_directory = commands.add_parser("ingest-directory")
    ingest_directory.add_argument("--workloads-dir", type=Path, required=True)
    ingest_directory.add_argument("--results-dir", type=Path, required=True)
    ingest_directory.add_argument("--endpoint")
    ingest_directory.add_argument("--token")
    ingest_directory.add_argument("--container")

    commands.add_parser("init-db")
    return parser


def ingestion_token(args: argparse.Namespace) -> str:
    token = getattr(args, "token", None) or os.environ.get("DASHBOARD_INGEST_TOKEN")
    if not token:
        raise SystemExit("ingestion token required: use --token or DASHBOARD_INGEST_TOKEN")
    return token


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "init-db":
        initialize_schema(make_engine(Settings().database_url))
        return
    if args.command == "ingest-directory":
        report, summary = ingest_directories(
            args.workloads_dir,
            args.results_dir,
            args.endpoint,
            token=ingestion_token(args) if args.endpoint else None,
            container=args.container,
        )
        print(render_report(report, args.workloads_dir, args.results_dir))
        if summary:
            print(
                f"\nPublish report\n  Accepted: {summary.accepted}"
                f"\n  Duplicates: {summary.duplicate}\n  Failed: {len(summary.failed)}"
            )
            for path, error in summary.failed:
                print(f"  - {path}: {error}")
        return
    if args.command == "adapt-perf":
        bundle = build_performance_bundle(args.recipe, args.result)
        args.output.write_bytes(bundle.canonical_json() + b"\n")
        return
    if args.command == "publish":
        bundle = Bundle.model_validate_json(args.bundle.read_bytes())
        artifacts = artifact_contents(bundle, tuple(args.artifact))
    else:
        bundle = build_performance_bundle(args.recipe, args.result)
        artifacts = artifact_contents(bundle, (args.recipe, args.result))
    with Publisher(args.endpoint, token=ingestion_token(args)) as publisher:
        result = publisher.publish(bundle, artifacts)
    print(f"{result.status}: {result.bundle_id}")


if __name__ == "__main__":
    main()
