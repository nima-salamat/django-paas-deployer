import pytest

from .call_state import InvalidCallTransition, transition_call


class Call:
    def __init__(self, status):
        self.status = status


def test_call_state_accepts_normal_lifecycle():
    call = Call("ringing")
    assert transition_call(call, "active") is True
    assert transition_call(call, "ended") is True
    assert call.status == "ended"


def test_call_state_rejects_resurrection_and_allows_duplicate_delivery():
    call = Call("ended")
    assert transition_call(call, "ended") is False
    with pytest.raises(InvalidCallTransition):
        transition_call(call, "active")
