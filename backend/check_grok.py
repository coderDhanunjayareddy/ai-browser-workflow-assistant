import httpx

from app.core.config import settings


def masked_key(value: str) -> str:
    if not value:
        return "<missing>"
    if len(value) <= 8:
        return "<configured>"
    return f"{value[:4]}...{value[-4:]}"


def main() -> int:
    print(f"GROK_MODEL={settings.grok_model}")
    print(f"GROK_API_KEY={masked_key(settings.grok_api_key)}")

    if not settings.grok_api_key:
        print("FAIL: GROK_API_KEY is not configured in backend/.env")
        return 1

    headers = {
        "Authorization": f"Bearer {settings.grok_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.grok_model,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "temperature": 0,
        "max_tokens": 10,
    }

    try:
        response = httpx.post(
            "https://api.grok.ai/v1/chat/completions",
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
        print(f"FAIL: Grok returned {exc.response.status_code}: {detail}")
        return 1
    except httpx.HTTPError as exc:
        print(f"FAIL: Grok request failed: {exc}")
        return 1

    payload = response.json()
    text = payload["choices"][0]["message"]["content"]
    print(f"PASS: Grok responded: {text.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
