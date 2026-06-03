from google import genai
from google.genai import errors

from app.core.config import settings


def masked_key(value: str) -> str:
    if not value:
        return "<missing>"
    if len(value) <= 8:
        return "<configured>"
    return f"{value[:4]}...{value[-4:]}"


def main() -> int:
    print(f"GEMINI_MODEL={settings.gemini_model}")
    print(f"GEMINI_API_KEY={masked_key(settings.gemini_api_key)}")

    if not settings.gemini_api_key:
        print("FAIL: GEMINI_API_KEY is not configured in backend/.env")
        return 1

    client = genai.Client(api_key=settings.gemini_api_key)

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents="Reply with OK.",
        )
    except errors.APIError as exc:
        code = exc.code or "unknown"
        message = exc.message or str(exc)
        print(f"FAIL: Gemini API returned {code}: {message}")

        if code == 401:
            print("Fix: Create a new Gemini API key and update backend/.env.")
        elif code == 403:
            print(
                "Fix: Confirm this key has Gemini API access, billing/project access "
                "is allowed if required, and the model is available to the account."
            )
        elif code == 429:
            print("Fix: Rate limit reached. Wait and try again.")
        return 1

    print(f"PASS: Gemini responded: {(response.text or '').strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
