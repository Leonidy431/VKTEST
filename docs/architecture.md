# Архитектура

## Слои системы

```
simulation/          физическая модель (Python) — истина в последней инстанции
  physics_engine.py    закон Джоуля-Ленца, состояние полиэтилена
  pid_simulator.py      ПИД-регулятор напряжения (валидирован тестами)
  power_network.py      батарея LiFePO4 + сеть 220В с просадками

control/             управляющая логика (Python, эталон для C-порта)
  state_machine.py      конечный автомат IDLE->...->DONE_SUCCESS/ERROR
  welder_controller.py  главный оркестратор цикла сварки
  energy_calculator.py  интегратор мгновенной мощности в джоули
  temperature_compensator.py  компенсация времени на T окружающей среды
  safety_validator.py   защиты (99 факт #86-90)

critical_analysis/   "Скептичный критик" как код
  error_detector.py     обнаружение архитектурных антипаттернов
  physics_validator.py  проверка против закона Джоуля-Ленца
  standards_checker.py  ГОСТ Р 52779-2007 / ГОСТ 32415-2013 / СП 42-103-2003
  solution_synthesizer.py  синтез итогового вердикта готовности

protocol/             формат данных и прослеживаемость
  barcode_parser.py      парсер 24-значного кода (упрощенная схема на базе ISO 12176-4)
  traceability.py         HMAC-SHA256 подпись протоколов сварки (секретный ключ)
  session_logger.py       JSONL append-only логирование

firmware/             C-порт для ESP32-S3 (esp-idf) — см. firmware/README.md
  main/pid_controller.c   зеркалирует simulation/pid_simulator.py
  main/state_machine.c    зеркалирует control/state_machine.py
  main/safety.c           зеркалирует control/safety_validator.py
  main/zero_crossing.c    аппаратная синхронизация с фазой сети
  main/measurements.c     АЦП, True RMS, датчик Холла

hardware/              выбор компонентов
  platforms.md            топ-5 ESP32 плат из 10+ исследованных, 12 параметров
  bom.csv                  перечень компонентов, ~$1326 без учета сборки

tests/                70 тестов, покрывающих все Python-модули выше
```

## Поток данных при одной сварке

```
Штрих-код муфты
  → protocol/barcode_parser.parse_barcode()
  → control/welder_controller.run_weld_cycle()
      1. safety_validator.check_pre_start()      — блокировка при плохих условиях
      2. Тестовый импульс → сверка R (±10%)
      3. temperature_compensator.compensate_heating_time()
      4. Цикл нагрева:
           energy_calculator.add_sample()         — интеграция мощности
           pid.update()                            — коррекция угла симистора
           safety_validator.check_during_weld()   — мониторинг обрыва/КЗ
      5. physics_engine.evaluate_weld_state()      — итоговый вердикт
  → protocol/traceability.finalize_record()        — подпись HMAC-SHA256
  → protocol/session_logger.log()                  — запись в JSONL
```

## Почему два языка (Python + C)

Python-версия — это **исполняемая спецификация**: она формально описывает
поведение системы и проверяется 70 тестами, включая нетривиальные
регрессионные случаи (интегральный виндап ПИД, согласованность физической
модели). C-версия для ESP32 портирует те же константы и алгоритмы, но не
может быть скомпилирована/протестирована в среде разработки без
инструментария esp-idf (см. `firmware/README.md`). Табличное соответствие
констант между версиями снижает риск рассинхронизации при доработке.
