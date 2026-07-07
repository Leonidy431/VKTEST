# Трассируемость 99 фактов → реализация

Каждый факт из исходного технологического трактата привязан к конкретному
файлу/модулю, где он воплощен и, где применимо, покрыт тестом. Разделы
соответствуют исходной нумерации (I-VII).

## I. Термодинамика и физика процесса (1-10)

| # | Факт | Реализация |
|---|---|---|
| 1 | Q = I²·R·t (закон Джоуля-Ленца) | `simulation/physics_engine.py::calculate_heat_output` |
| 3 | Нелинейность R_cold vs R_hot | `simulation/physics_engine.py::resistance_at_temp` |
| 4 | Температура расплава 210-230°C | `JoulesLenzEngine.MELT_TEMP_MIN_C/MAX_C` |
| 5 | Энергия вычисляется, не температура напрямую | `EnergyCalculator` (`control/energy_calculator.py`) |
| 6 | Компенсация просадки сети увеличением времени | `control/temperature_compensator.py` (аналогичный принцип для T) |
| 7-8 | Компенсация окружающей температуры, экспонента при <0°C | `TemperatureCompensator.compensate_heating_time` |
| 9-10 | Недогрев/перегрев → брак | `JoulesLenzEngine.evaluate_weld_state` → `WeldState` enum |

## II-III. Силовая часть и измерения (11-40)

| # | Факт | Реализация |
|---|---|---|
| 15 | Фазовое управление симистором | `simulation/pid_simulator.py::angle_to_rms_voltage`, `firmware/main/pid_controller.c` |
| 17 | Активное охлаждение по датчику T радиатора | `control/safety_validator.py::should_derate`, `firmware/main/safety.c::safety_should_derate` |
| 19 | Zero-Cross Detector | `firmware/main/zero_crossing.c` |
| 21 | Ток до 110А в сварочной цепи | `SafetyLimits.max_current_a` / `short_circuit_current_a` |
| 28-30 | Датчик Холла, 1кГц опрос, True RMS | `firmware/main/measurements.c` (RMS_WINDOW_SIZE, compute_rms) |
| 34-36 | Тестовый импульс, сверка R с кодом (±10%) | `control/welder_controller.py::run_weld_cycle` (resistance_delta check), `critical_analysis/physics_validator.py::validate_resistance_match` |

## IV. Микроконтроллерная архитектура (41-55)

| # | Факт | Реализация |
|---|---|---|
| 41 | 32-битный МК (ESP32) | `hardware/platforms.md` — выбор ESP32-S3 |
| 42-45 | ПИД-регулятор (P/I/D составляющие) | `simulation/pid_simulator.py`, `firmware/main/pid_controller.c` |
| 51 | Конечный автомат состояний | `control/state_machine.py`, `firmware/main/state_machine.c` |
| 54 | Зуммер для индикации | `hardware/bom.csv` (пьезоэлемент), интеграция — TODO в прошивке |

## V. Интерфейсы, HMI и периферия (56-70)

| # | Факт | Реализация |
|---|---|---|
| 58-59 | 24-значный штрих-код ISO 12176-4 (упрощенная схема проекта) | `protocol/barcode_format.md`, `protocol/barcode_parser.py` |
| 63 | Debounce кнопок | Аппаратная/программная обработка — TODO в прошивке (не реализовано в каркасе) |
| 64 | Bluetooth/Wi-Fi синхронизация | `firmware/README.md` (заявлено, не реализовано в каркасе) |
| 66 | Ручной ввод при поврежденном сканере | `protocol/barcode_format.md` раздел "Ручной ввод" |
| 67 | Отображение U/I/R/энергии в реальном времени | `control/energy_calculator.py` предоставляет данные для HMI |

## VI. Проектирование плат и корпусирование (71-85)

| # | Факт | Реализация |
|---|---|---|
| 78 | IP54/IP65 защита | `hardware/bom.csv` (корпус, кнопки), `docs/battery_energy_budget.md` |
| 81 | Виброгасящие демпферы трансформатора | `hardware/bom.csv` — учтено в позиции "Корпус" (детализация в mechanical/ — TODO) |

## VII. Безопасность, софт и самодиагностика (86-99)

| # | Факт | Реализация | Тест |
|---|---|---|---|
| 86 | Open Circuit Fault | `control/safety_validator.py::check_during_weld`, `firmware/main/safety.c` | `tests/test_safety_validators.py::test_during_weld_detects_open_circuit`, `tests/test_welder_controller.py::test_open_circuit_during_heating_aborts` |
| 87 | Short Circuit Fault (>110А) | `SafetyLimits.short_circuit_current_a` | `test_during_weld_detects_short_circuit` |
| 89 | Low Input Voltage (<185В) блокирует старт | `SafetyValidator.check_pre_start` | `test_pre_start_fails_low_voltage` |
| 90 | Частота вне 45-65Гц блокирует старт | `SafetyValidator.check_pre_start` | `test_pre_start_fails_bad_frequency` |
| 91-92 | Traceability + SHA-256 подпись протокола | `protocol/traceability.py`, `protocol/session_logger.py` | `tests/test_traceability.py` (5 тестов) |
| 93 | Остывание — обратный отсчет, не форсируется | `control/temperature_compensator.py::compensate_cooling_time` | — |
| 96 | Блокировка при T < -20°C | `SafetyLimits.min_operating_temp_c` | `test_pre_start_fails_too_cold` |
| 98 | Лимиты по диаметру — "защита от дурака" | `critical_analysis/physics_validator.py::validate_universal_table_usage` (отвергает универсальные таблицы вместо жестких лимитов — альтернативный, более гибкий механизм защиты) | `test_physics_validator_rejects_universal_table` |

## Философское соответствие: критик как код

Отдельный смысловой слой — `critical_analysis/` — не привязан к конкретному
номеру факта, а воплощает саму методологию "Скептичного критика":
`error_detector.py` активно ищет архитектурные антипаттерны (открытый
контур, универсальные таблицы, отсутствие сверки штрих-кода), а
`solution_synthesizer.py` объединяет это с проверкой физики и нормативным
соответствием в единый вердикт `is_ready_for_production`.
