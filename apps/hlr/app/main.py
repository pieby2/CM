from fastapi import FastAPI

from app.config import settings
from app.hlr_model import HlrModelService, SCHEDULER_VERSION
from app.schemas import PredictTransitionRequest, PredictTransitionResponse, WeightsPayload, WeightsResponse

app = FastAPI(
    title="Cue Math HLR Service",
    version="0.1.0",
    description="Half-Life Regression microservice for recall prediction and scheduling transitions.",
)

model_service = HlrModelService(settings)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "scheduler_version": SCHEDULER_VERSION}


@app.post("/predict-transition", response_model=PredictTransitionResponse)
def predict_transition(payload: PredictTransitionRequest) -> PredictTransitionResponse:
    return model_service.predict_transition(payload)


@app.get("/weights", response_model=WeightsResponse)
def get_weights() -> WeightsResponse:
    return WeightsResponse(
        scheduler_version=SCHEDULER_VERSION,
        weights=WeightsPayload.model_validate(model_service.weights.__dict__),
        model_path=settings.model_path,
    )


@app.put("/weights", response_model=WeightsResponse)
def put_weights(payload: WeightsPayload) -> WeightsResponse:
    weights = model_service.update_weights(payload)
    return WeightsResponse(
        scheduler_version=SCHEDULER_VERSION,
        weights=WeightsPayload.model_validate(weights.__dict__),
        model_path=settings.model_path,
    )
