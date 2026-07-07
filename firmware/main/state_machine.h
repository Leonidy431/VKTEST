#ifndef STATE_MACHINE_H
#define STATE_MACHINE_H

/* Конечный автомат сварки — портирован из control/state_machine.py. */

typedef enum {
    WELD_STATE_IDLE = 0,
    WELD_STATE_VALIDATE_CODE,
    WELD_STATE_TEST_PULSE,
    WELD_STATE_PRE_WELD,
    WELD_STATE_HEATING,
    WELD_STATE_COOLING_WAIT,
    WELD_STATE_DONE_SUCCESS,
    WELD_STATE_ERROR,
} welding_state_t;

typedef struct {
    welding_state_t state;
    const char *error_reason;
} welding_state_machine_t;

void wsm_init(welding_state_machine_t *sm);

/* Возвращает 0 при недопустимом переходе (кроме перехода в ERROR — он разрешен всегда). */
int wsm_transition_to(welding_state_machine_t *sm, welding_state_t new_state);

void wsm_raise_error(welding_state_machine_t *sm, const char *reason);
void wsm_reset(welding_state_machine_t *sm);

#endif /* STATE_MACHINE_H */
