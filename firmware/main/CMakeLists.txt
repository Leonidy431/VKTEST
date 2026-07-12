idf_component_register(
    SRCS
        "app_main.c"
        "pid_controller.c"
        "state_machine.c"
        "safety.c"
        "zero_crossing.c"
        "measurements.c"
    INCLUDE_DIRS "."
    REQUIRES
        driver
        esp_adc
        esp_timer
)
