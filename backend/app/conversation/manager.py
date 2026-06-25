from app.conversation.store import ConversationStore, Turn

_store = ConversationStore()


def append_turn(conversation_id: str, role: str, intent: str, content: object) -> None:
    _store.append_turn(conversation_id, role=role, intent=intent, content=content)


def get_thread(conversation_id: str) -> list[Turn]:
    return _store.get_turns(conversation_id)


def _reset_store_for_testing() -> None:
    _store.clear()
