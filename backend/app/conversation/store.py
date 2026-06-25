from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

MAX_CONVERSATIONS = 100
MAX_TURNS_PER_CONVERSATION = 20


@dataclass
class Turn:
    role: str
    intent: str
    content: object
    created_at: datetime = field(default_factory=datetime.utcnow)


class ConversationStore:
    def __init__(self) -> None:
        self._conversations: dict[str, deque[Turn]] = {}
        self._insertion_order: deque[str] = deque()

    def append_turn(self, conversation_id: str, role: str, intent: str, content: object) -> None:
        if conversation_id not in self._conversations:
            if len(self._conversations) >= MAX_CONVERSATIONS:
                oldest = self._insertion_order.popleft()
                self._conversations.pop(oldest, None)
            self._conversations[conversation_id] = deque(maxlen=MAX_TURNS_PER_CONVERSATION)
            self._insertion_order.append(conversation_id)
        self._conversations[conversation_id].append(
            Turn(role=role, intent=intent, content=content)
        )

    def get_turns(self, conversation_id: str) -> list[Turn]:
        return list(self._conversations.get(conversation_id, []))

    def clear(self) -> None:
        self._conversations.clear()
        self._insertion_order.clear()
