from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger("cue.ai_client")

SUPPORTED_AI_PROVIDERS = {"gemini", "openai", "groq"}


class AIClientError(Exception):
    pass


def infer_provider_from_api_key(api_key: str | None) -> str | None:
    if not api_key:
        return None

    key = api_key.strip()
    if key.startswith("AIza"):
        return "gemini"
    if key.startswith("sk-"):
        return "openai"
    if key.startswith("gsk_"):
        return "groq"
    return None


def resolve_provider(provider: str | None, api_key: str | None) -> str:
    requested = (provider or "").strip().lower()
    if requested in {"", "auto"}:
        requested = infer_provider_from_api_key(api_key) or settings.default_ai_provider.strip().lower()

    if requested not in SUPPORTED_AI_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_AI_PROVIDERS))
        raise AIClientError(f"Unsupported AI provider '{requested}'. Use one of: {supported}")

    return requested


def resolve_api_key(provider: str, api_key: str | None) -> str:
    if api_key and api_key.strip():
        return api_key.strip()

    fallback_key = {
        "gemini": settings.gemini_api_key,
        "openai": settings.openai_api_key,
        "groq": settings.groq_api_key,
    }[provider]

    if fallback_key and fallback_key.strip():
        return fallback_key.strip()

    env_name = f"CUE_{provider.upper()}_API_KEY"
    raise AIClientError(
        f"{provider.capitalize()} API key not configured. Provide a key in the app or set {env_name}."
    )


def resolve_temperature(provider: str, temperature: float | None) -> float:
    if temperature is not None:
        return float(temperature)

    return {
        "gemini": settings.gemini_temperature,
        "openai": settings.openai_temperature,
        "groq": settings.groq_temperature,
    }[provider]


def resolve_model(provider: str, has_images: bool) -> str:
    if provider == "gemini":
        return settings.gemini_model
    if provider == "openai":
        return settings.openai_model

    # Groq vision requires a vision-capable model when images are included.
    if has_images:
        return settings.groq_vision_model
    return settings.groq_model


def encode_image_paths(image_paths: list[Path] | None) -> list[tuple[str, str]]:
    encoded: list[tuple[str, str]] = []
    for path in image_paths or []:
        if not path.exists() or not path.is_file():
            continue

        mime = guess_mime_type(path)
        encoded.append((mime, base64.b64encode(path.read_bytes()).decode("utf-8")))

    return encoded


def guess_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".gif":
        return "image/gif"
    return "image/png"


def parse_http_error(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase or f"HTTP {response.status_code}"

    if isinstance(data, dict):
        if isinstance(data.get("error"), dict):
            return str(data["error"].get("message") or data["error"])
        if "error" in data:
            return str(data["error"])
        if "detail" in data:
            return str(data["detail"])

    return str(data)


def generate_completion(
    system_prompt: str,
    user_prompt: str,
    api_key: str | None = None,
    provider: str | None = None,
    temperature: float | None = None,
    image_paths: list[Path] | None = None,
) -> str:
    resolved_provider = resolve_provider(provider, api_key)
    resolved_api_key = resolve_api_key(resolved_provider, api_key)
    resolved_temperature = resolve_temperature(resolved_provider, temperature)
    encoded_images = encode_image_paths(image_paths)
    model = resolve_model(resolved_provider, has_images=bool(encoded_images))

    if resolved_provider == "gemini":
        return _call_gemini(
            api_key=resolved_api_key,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=resolved_temperature,
            encoded_images=encoded_images,
        )

    if resolved_provider == "openai":
        return _call_openai_compatible(
            endpoint="https://api.openai.com/v1/chat/completions",
            provider_name="OpenAI",
            api_key=resolved_api_key,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=resolved_temperature,
            encoded_images=encoded_images,
        )

    if resolved_provider == "groq":
        return _call_openai_compatible(
            endpoint="https://api.groq.com/openai/v1/chat/completions",
            provider_name="Groq",
            api_key=resolved_api_key,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=resolved_temperature,
            encoded_images=encoded_images,
        )

    raise AIClientError("Unsupported AI provider")


def _call_openai_compatible(
    endpoint: str,
    provider_name: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    encoded_images: list[tuple[str, str]],
) -> str:
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    if encoded_images:
        user_content = [{"type": "text", "text": user_prompt}]
        for mime, data in encoded_images:
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{data}"},
                }
            )
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": user_prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }

    try:
        with httpx.Client(timeout=settings.ai_timeout_seconds) as client:
            response = client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise AIClientError(f"{provider_name} request failed: {exc}") from exc

    if response.status_code >= 400:
        detail = parse_http_error(response)
        raise AIClientError(f"{provider_name} API error: {detail}")

    try:
        data = response.json()
        return str(data["choices"][0]["message"]["content"]).strip()
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        logger.error("Invalid %s response format: %s", provider_name, response.text)
        raise AIClientError(f"{provider_name} response format was unexpected") from exc


def _call_gemini(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    encoded_images: list[tuple[str, str]],
) -> str:
    parts: list[dict] = [{"text": user_prompt}]
    for mime, data in encoded_images:
        parts.append({"inlineData": {"mimeType": mime, "data": data}})

    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": temperature,
        },
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    try:
        with httpx.Client(timeout=settings.ai_timeout_seconds) as client:
            response = client.post(
                url,
                params={"key": api_key},
                headers={"Content-Type": "application/json"},
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise AIClientError(f"Gemini request failed: {exc}") from exc

    if response.status_code >= 400:
        detail = parse_http_error(response)
        raise AIClientError(f"Gemini API error: {detail}")

    try:
        data = response.json()
    except ValueError as exc:
        raise AIClientError("Gemini returned invalid JSON") from exc

    candidates = data.get("candidates") or []
    if not candidates:
        prompt_feedback = data.get("promptFeedback")
        if prompt_feedback:
            raise AIClientError(f"Gemini returned no candidates: {prompt_feedback}")
        raise AIClientError("Gemini returned no candidates")

    response_parts = candidates[0].get("content", {}).get("parts", [])
    text_chunks = [part.get("text", "") for part in response_parts if isinstance(part, dict)]
    combined = "\n".join(chunk for chunk in text_chunks if chunk).strip()

    if not combined:
        raise AIClientError("Gemini response did not contain text output")

    return combined
