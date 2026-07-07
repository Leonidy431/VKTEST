"""
Конечный автомат процесса сварки.

IDLE -> VALIDATE_CODE -> TEST_PULSE -> PRE_WELD -> HEATING -> COOLING_WAIT
  -> DONE_SUCCESS -> IDLE

Любое состояние может перейти в ERROR при нарушении защит.
"""

from enum import Enum, auto
from typing import Callable, Dict, Optional


class WeldingState(Enum):
    IDLE = auto()
    VALIDATE_CODE = auto()
    TEST_PULSE = auto()
    PRE_WELD = auto()
    HEATING = auto()
    COOLING_WAIT = auto()
    DONE_SUCCESS = auto()
    ERROR = auto()


class InvalidTransitionError(RuntimeError):
    pass


# Разрешенные переходы (кроме ERROR, который доступен из любого состояния)
_ALLOWED_TRANSITIONS: Dict[WeldingState, set] = {
    WeldingState.IDLE: {WeldingState.VALIDATE_CODE},
    WeldingState.VALIDATE_CODE: {WeldingState.TEST_PULSE, WeldingState.ERROR},
    WeldingState.TEST_PULSE: {WeldingState.PRE_WELD, WeldingState.ERROR},
    WeldingState.PRE_WELD: {WeldingState.HEATING, WeldingState.ERROR},
    WeldingState.HEATING: {WeldingState.COOLING_WAIT, WeldingState.ERROR},
    WeldingState.COOLING_WAIT: {WeldingState.DONE_SUCCESS, WeldingState.ERROR},
    WeldingState.DONE_SUCCESS: {WeldingState.IDLE},
    WeldingState.ERROR: {WeldingState.IDLE},
}


class WeldingStateMachine:
    def __init__(self, on_transition: Optional[Callable[[WeldingState, WeldingState], None]] = None) -> None:
        self._state = WeldingState.IDLE
        self._on_transition = on_transition
        self._error_reason: Optional[str] = None

    @property
    def state(self) -> WeldingState:
        return self._state

    @property
    def error_reason(self) -> Optional[str]:
        return self._error_reason

    def transition_to(self, new_state: WeldingState) -> None:
        allowed = _ALLOWED_TRANSITIONS.get(self._state, set())
        if new_state != WeldingState.ERROR and new_state not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition from {self._state.name} to {new_state.name}"
            )

        old_state = self._state
        self._state = new_state
        if new_state != WeldingState.ERROR:
            self._error_reason = None

        if self._on_transition:
            self._on_transition(old_state, new_state)

    def raise_error(self, reason: str) -> None:
        self._error_reason = reason
        self.transition_to(WeldingState.ERROR)

    def reset(self) -> None:
        self._state = WeldingState.IDLE
        self._error_reason = None
