import httpx

from app.core.config import settings


def masked_key(value: str) -> str:
    if not value:
        return "<missing>"
    if len(value) <= 8:
        return "<configured>"
    return f"{value[:6]}...{value[-4:]}"


def main() -> int:
    print(f"OPENROUTER_MODEL={settings.openrouter_model}")
    print(f"OPENROUTER_API_KEY={masked_key(settings.openrouter_api_key)}")

    if not settings.openrouter_api_key:
        print("FAIL: OPENROUTER_API_KEY is not configured in backend/.env")
        return 1

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.openrouter_site_url,
        "X-Title": settings.openrouter_app_name,
    }
    body = {
        "model": settings.openrouter_model,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "temperature": 0,
        "max_tokens": 10,
    }

    try:
        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=body,
            timeout=30.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("error", {}).get("message")
        except ValueError:
            detail = exc.response.text
        print(f"FAIL: OpenRouter returned {exc.response.status_code}: {detail}")
        return 1
    except httpx.HTTPError as exc:
        print(f"FAIL: OpenRouter request failed: {exc}")
        return 1

    payload = response.json()
    text = payload["choices"][0]["message"]["content"]
    print(f"PASS: OpenRouter responded: {text.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
