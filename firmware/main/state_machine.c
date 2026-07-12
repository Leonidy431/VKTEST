#include "state_machine.h"
#include <stddef.h>

static int is_allowed_transition(welding_state_t from, welding_state_t to)
{
    switch (from) {
        case WELD_STATE_IDLE:
            return to == WELD_STATE_VALIDATE_CODE;
        case WELD_STATE_VALIDATE_CODE:
            return to == WELD_STATE_TEST_PULSE;
        case WELD_STATE_TEST_PULSE:
            return to == WELD_STATE_PRE_WELD;
        case WELD_STATE_PRE_WELD:
            return to == WELD_STATE_HEATING;
        case WELD_STATE_HEATING:
            return to == WELD_STATE_COOLING_WAIT;
        case WELD_STATE_COOLING_WAIT:
            return to == WELD_STATE_DONE_SUCCESS;
        case WELD_STATE_DONE_SUCCESS:
            return to == WELD_STATE_IDLE;
        case WELD_STATE_ERROR:
            return to == WELD_STATE_IDLE;
        default:
            return 0;
    }
}

void wsm_init(welding_state_machine_t *sm)
{
    sm->state = WELD_STATE_IDLE;
    sm->error_reason = NULL;
}

int wsm_transition_to(welding_state_machine_t *sm, welding_state_t new_state)
{
    /* Переход в ERROR разрешен из любого состояния (кроме уже ERROR->ERROR, что бессмысленно). */
    if (new_state != WELD_STATE_ERROR && !is_allowed_transition(sm->state, new_state)) {
        return 0;
    }
    sm->state = new_state;
    if (new_state != WELD_STATE_ERROR) {
        sm->error_reason = NULL;
    }
    return 1;
}

void wsm_raise_error(welding_state_machine_t *sm, const char *reason)
{
    sm->error_reason = reason;
    sm->state = WELD_STATE_ERROR;
}

void wsm_reset(welding_state_machine_t *sm)
{
    sm->state = WELD_STATE_IDLE;
    sm->error_reason = NULL;
}
