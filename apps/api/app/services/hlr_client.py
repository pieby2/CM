from __future__ import annotations

from importlib import import_module
from typing import Any

from app.config import settings


def request_hlr_transition(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not settings.hlr_enabled:
        return None

    httpx = _load_httpx()
    if httpx is None:
        return None

    base_url = settings.hlr_service_url.rstrip("/")

    try:
        with httpx.Client(timeout=settings.hlr_timeout_seconds) as client:
            response = client.post(f"{base_url}/predict-transition", json=payload)
        if response.status_code != 200:
            return None

        data = response.json()
        required = {"ease_factor", "reps", "interval_days", "status", "scheduler_version"}
        if not required.issubset(set(data.keys())):
            return None
        return data
    except Exception:
        return None


def _load_httpx():
    try:
        return import_module("httpx")
    except ModuleNotFoundError:
        return None
