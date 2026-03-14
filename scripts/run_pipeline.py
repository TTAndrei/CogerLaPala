import argparse
import asyncio
import json
from pathlib import Path

from cogerlapala.config import get_settings
from cogerlapala.models import PipelineRequest
from cogerlapala.services.pipeline import build_default_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CogerLaPala pipeline from a JSON file")
    parser.add_argument(
        "--request",
        default="examples/sample_request.json",
        help="Path to request payload JSON",
    )
    return parser.parse_args()


def load_request(path: str) -> PipelineRequest:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return PipelineRequest.model_validate(payload)


async def run(path: str) -> None:
    settings = get_settings()
    pipeline = build_default_pipeline(settings)
    request = load_request(path)
    response = await pipeline.run(request)
    print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    arguments = parse_args()
    asyncio.run(run(arguments.request))
