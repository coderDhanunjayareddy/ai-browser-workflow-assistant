from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any, Callable

from pydantic import BaseModel


class SerializationValidator:
    def round_trip(self, value: Any, factory: Callable[[dict[str, Any]], Any] | None = None) -> dict[str, Any]:
        payload = self.to_jsonable(value)
        encoded = json.dumps(payload, sort_keys=True, default=str)
        decoded = json.loads(encoded)
        restored = factory(decoded) if factory else self.restore(type(value), decoded)
        restored_payload = self.to_jsonable(restored)
        return {
            "compatible": payload == restored_payload,
            "original": payload,
            "restored": restored_payload,
        }

    def restore(self, target: type, payload: dict[str, Any]) -> Any:
        if isinstance(target, type) and issubclass(target, BaseModel):
            return target.model_validate(payload)
        if is_dataclass(target):
            return target(**payload)
        return payload

    def to_jsonable(self, value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, dict):
            return {key: self.to_jsonable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.to_jsonable(item) for item in value]
        return value
