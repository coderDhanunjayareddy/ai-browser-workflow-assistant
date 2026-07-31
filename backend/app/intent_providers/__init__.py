from __future__ import annotations

_registered = False


def register_default_providers() -> None:
    global _registered
    if _registered:
        return
    from app.intent_providers import (
        browser_intelligence_executor,
        browser_executor,
        completion_executor,
        knowledge_executor,
        runtime_executor,
        validation_executor,
    )

    browser_executor.register()
    browser_intelligence_executor.register()
    knowledge_executor.register()
    validation_executor.register()
    completion_executor.register()
    runtime_executor.register()
    _registered = True


__all__ = ["register_default_providers"]
