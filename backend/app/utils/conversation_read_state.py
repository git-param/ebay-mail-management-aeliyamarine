"""Keep ACES read-state overrides scoped to the latest message."""

READ_STATE_KEY = 'aces_read_state'


def latest_conversation_message(conversation):
    return max(
        conversation.messages or [],
        key=lambda message: (message.sent_at, str(getattr(message, 'id', '') or '')),
        default=None,
    )


def read_state_override(conversation) -> bool | None:
    payload = getattr(conversation, 'raw_payload', None)
    state = payload.get(READ_STATE_KEY) if isinstance(payload, dict) else None
    if not isinstance(state, dict) or not isinstance(state.get('is_read'), bool):
        return None
    message = latest_conversation_message(conversation)
    message_id = str(message.id) if message and getattr(message, 'id', None) else ''
    return state['is_read'] if state.get('message_id') == message_id else None


def apply_read_state(conversation, is_read: bool):
    message = latest_conversation_message(conversation)
    stored_payload = getattr(conversation, 'raw_payload', None)
    payload = stored_payload if isinstance(stored_payload, dict) else {}
    conversation.raw_payload = {
        **payload,
        READ_STATE_KEY: {
            'is_read': is_read,
            'message_id': str(message.id) if message and getattr(message, 'id', None) else '',
        },
    }
    if is_read:
        conversation.unread_count = 0
        for row in conversation.messages:
            if row.is_inbound:
                row.read_status = True
