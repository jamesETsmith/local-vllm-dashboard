import argparse
from pathlib import Path

from local_vllm_dashboard.adapter import build_performance_bundle
from local_vllm_dashboard.contracts import Bundle
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
    publish.add_argument("--endpoint", required=True)

    adapt_publish = commands.add_parser("adapt-and-publish")
    adapt_publish.add_argument("--recipe", type=Path, required=True)
    adapt_publish.add_argument("--result", type=Path, required=True)
    adapt_publish.add_argument("--endpoint", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "adapt-perf":
        bundle = build_performance_bundle(args.recipe, args.result)
        args.output.write_bytes(bundle.canonical_json() + b"\n")
        return
    if args.command == "publish":
        bundle = Bundle.model_validate_json(args.bundle.read_bytes())
    else:
        bundle = build_performance_bundle(args.recipe, args.result)
    with Publisher(args.endpoint) as publisher:
        result = publisher.publish(bundle)
    print(f"{result.status}: {result.bundle_id}")


if __name__ == "__main__":
    main()
