import pytest

from control.state_machine import WeldingState, WeldingStateMachine, InvalidTransitionError


def test_initial_state_is_idle():
    sm = WeldingStateMachine()
    assert sm.state == WeldingState.IDLE


def test_happy_path_full_cycle():
    sm = WeldingStateMachine()
    sequence = [
        WeldingState.VALIDATE_CODE,
        WeldingState.TEST_PULSE,
        WeldingState.PRE_WELD,
        WeldingState.HEATING,
        WeldingState.COOLING_WAIT,
        WeldingState.DONE_SUCCESS,
        WeldingState.IDLE,
    ]
    for state in sequence:
        sm.transition_to(state)
        assert sm.state == state


def test_invalid_transition_raises():
    sm = WeldingStateMachine()
    with pytest.raises(InvalidTransitionError):
        sm.transition_to(WeldingState.HEATING)  # нельзя из IDLE сразу в HEATING


def test_error_can_be_raised_from_any_state():
    sm = WeldingStateMachine()
    sm.transition_to(WeldingState.VALIDATE_CODE)
    sm.transition_to(WeldingState.TEST_PULSE)
    sm.raise_error("Test fault")
    assert sm.state == WeldingState.ERROR
    assert sm.error_reason == "Test fault"


def test_error_transitions_back_to_idle():
    sm = WeldingStateMachine()
    sm.transition_to(WeldingState.VALIDATE_CODE)
    sm.raise_error("Fault")
    sm.transition_to(WeldingState.IDLE)
    assert sm.state == WeldingState.IDLE
    assert sm.error_reason is None


def test_on_transition_callback_invoked():
    calls = []
    sm = WeldingStateMachine(on_transition=lambda old, new: calls.append((old, new)))
    sm.transition_to(WeldingState.VALIDATE_CODE)
    assert calls == [(WeldingState.IDLE, WeldingState.VALIDATE_CODE)]


def test_reset_returns_to_idle():
    sm = WeldingStateMachine()
    sm.transition_to(WeldingState.VALIDATE_CODE)
    sm.raise_error("x")
    sm.reset()
    assert sm.state == WeldingState.IDLE
    assert sm.error_reason is None
