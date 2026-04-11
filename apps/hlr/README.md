# Cue Math HLR Service

This service predicts review transitions using a first Half-Life Regression style model.

## Endpoints

- `GET /health`
- `POST /predict-transition`
- `GET /weights`
- `PUT /weights`

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8010
```

## Model behavior

- Computes half-life from card/user/review features.
- Estimates current recall from elapsed lag.
- Suggests next interval targeting recall threshold.
- Updates reps/status/ease-factor in a scheduler-compatible format.
