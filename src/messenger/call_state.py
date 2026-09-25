"""Deterministic call lifecycle rules independent of WebSocket signaling."""


class InvalidCallTransition(ValueError):
    pass


ALLOWED_TRANSITIONS = {
    "ringing": {"active", "ended", "missed", "declined", "no_answer"},
    "active": {"ended", "missed"},
    "ended": set(),
    "missed": set(),
    "declined": set(),
    "no_answer": set(),
}


def transition_call(session, target: str) -> bool:
    current = str(session.status)
    target = str(target)
    if current == target:
        return False
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidCallTransition(f"Cannot transition call from {current!r} to {target!r}.")
    session.status = target
    return True
