from fastapi import FastAPI

from cogerlapala.config import get_settings
from cogerlapala.models import PipelineRequest, PipelineResponse
from cogerlapala.services.pipeline import build_default_pipeline

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
pipeline = build_default_pipeline(settings)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/pipeline/run", response_model=PipelineResponse)
async def run_pipeline(request: PipelineRequest) -> PipelineResponse:
    return await pipeline.run(request)


@app.post("/pipeline/preview", response_model=PipelineResponse)
async def preview_pipeline(request: PipelineRequest) -> PipelineResponse:
    preview_request = request.model_copy(deep=True)
    preview_request.execution.dry_run = True
    preview_request.execution.enable_browser_automation = False
    return await pipeline.run(preview_request)
