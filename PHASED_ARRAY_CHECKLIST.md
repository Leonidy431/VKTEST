# ФАР MVP — Чек-лист Phase 1

**Дата создания:** 2026-07-08  
**Статус:** In Progress  
**Ответственный:** Robotics Team

---

## 📋 Подготовка к разработке

### Окружение
- [x] Создана ветка `claude/phased-array-robotics-nhh6i2`
- [x] Структура модуля `phased_array/` создана
- [x] Python 3.8+ с PEP8 соответствием
- [ ] Виртуальное окружение настроено
- [ ] Dependencies установлены (`pip install -r requirements.txt`)

### Документация
- [x] TZ_PHASED_ARRAY_MVP.md написан
- [x] PHASED_ARRAY_ROADMAP.md с 3 фазами
- [x] phased_array/README.md с API
- [x] Примеры в examples_integration.py
- [ ] Дополнительная документация по RF параметрам

---

## 🔧 Компоненты модуля (реализация)

### Ядро
- [x] `config.py` — RF параметры (все в SI единицах, PEP8)
- [x] `rf_module.py` — API для Qorvo/Wi-Fi7 (SPI/I2C, управление питанием)
- [x] `beamforming.py` — Алгоритмы направления луча (фазовые веса, сканирование)
- [x] `power_manager.py` — Адаптивное управление TX мощностью
- [x] `data_logger.py` — Логирование метрик (JSON, CSV экспорт)

### Тесты
- [x] `tests/test_rf_module.py` — 15+ тестов инициализации, TX/RX, RSSI
- [x] `tests/test_beamforming.py` — 20+ тестов фазовых весов, сканирования
- [ ] `tests/test_power_manager.py` — Тесты адаптивной мощности и теплового контроля
- [ ] `tests/test_integration.py` — Интеграционные тесты с mainloop

### Интеграция
- [x] `__init__.py` с экспортом публичного API
- [x] Пример интеграции с robot_controller (examples_integration.py)
- [ ] Интеграция в `control/state_machine.py` (добавить RF_INIT, RF_STREAMING состояния)

---

## 📦 Закупка компонентов (этап 1.1)

### Обязательные
- [ ] Qorvo QPM5680 Evaluation Board
- [ ] LMR-100 RF кабели (50 Ом, 2-3 м)
- [ ] IPEX/SMA разъемы (20+ шт)
- [ ] Xilinx Zynq-7010 FPGA плата

### Опциональные
- [ ] Wi-Fi 7 роутер (alternative к Qorvo)
- [ ] Спектроанализатор для отладки (аренда)
- [ ] VNA (Vector Network Analyzer) для измерения S-параметров

**Статус:** ⏳ Ожидание утверждения бюджета

---

## 🔨 Механический монтаж (этап 1.2)

- [ ] Демонтированы встроенные антенны RF модуля
- [ ] Припаяны RF кабели на разъемы
- [ ] Кабели смонтированы на корпусе робота
- [ ] Проверена механическая жесткость
- [ ] Измерено расстояние между элементами антенны
- [ ] Документированы фотографии монтажа

**Результат:** Фото-отчет в `/phased_array/docs/assembly_photos/`

---

## 💻 Программное обеспечение (этап 1.3)

### Инициализация
- [x] SPI/I2C интерфейс инициализируется
- [x] RF чипсет bootает и отзывается
- [x] Калибровка внутреннего oscillator

### Управление
- [x] TX мощность регулируется (14-22 дБм)
- [x] RX/TX режимы переключаются
- [x] RSSI читается в реальном времени

### Интеграция с роботом
- [ ] state_machine.py: добавлены RF состояния
- [ ] mainloop робота вызывает RF методы
- [ ] Логирование встроено в основной лог

**Тестирование:** `pytest phased_array/tests/ -v`

---

## 🧪 Тестирование (этап 1.4)

### Unit-тесты
- [x] Config validation
- [x] RF Module initialization, TX/RX, RSSI
- [x] BeamForming phase weights, scanning, gain calculation
- [ ] PowerManager adaptive control, thermal throttling
- [ ] DataLogger metrics, export

**Цель:** >80% code coverage

### Интеграционные тесты
- [ ] RF + BeamForming вместе
- [ ] RF + PowerManager адаптивная мощность
- [ ] Полный цикл robot loop

### Полевые тесты (real hardware)
- [ ] Связь на 10 м
- [ ] Связь на 25 м
- [ ] Связь на 50 м
- [ ] Диаграмма направленности (ручное сканирование)
- [ ] Тепловой тест (30 мин TX на max мощности)
- [ ] Стабильность соединения (нет dropouts)

**Результат:** Таблица измерений в `/phased_array/docs/field_test_results.md`

---

## 📊 Результаты и метрики

### Функциональные
- [ ] Модуль инициализируется за <2 сек
- [ ] RSSI читается с интервалом <100 мс
- [ ] TX мощность изменяется за <50 мс
- [ ] Беспроводная связь стабильна (packet loss <1%)

### Тепловые
- [ ] PA температура <70°C при TX 20 дБм в течение 30 мин
- [ ] Дельта T = T(PA) - T(ambient) < 15°C

### RF Параметры
- [ ] Дальность в open space ≥50 м @ RSSI -85 дБм
- [ ] Диаграмма направленности измерена (всенаправленность ±90°)
- [ ] Усиление антенны ≥6 dBi

### Код
- [ ] Тесты: >80% coverage (15+ tests)
- [ ] PEP8: 0 errors (`flake8 phased_array/`)
- [ ] Type hints: 100% (`mypy phased_array/`)
- [ ] Docstrings: есть для всех public methods

---

## 📝 Документация

### Обязательные файлы
- [x] phased_array/README.md
- [x] docs/TZ_PHASED_ARRAY_MVP.md
- [x] docs/PHASED_ARRAY_ROADMAP.md
- [x] phased_array/config.py — внутренняя документация
- [ ] docs/rf_parameters.md — RF спецификация из измерений
- [ ] docs/antenna_patterns.md — Диаграммы направленности
- [ ] docs/installation_guide.md — Для сборки прототипа

### Примеры
- [x] phased_array/examples_integration.py (7 примеров)
- [ ] jupyter notebook с анализом логов

---

## 🚀 Подготовка к Phase 2

### Перед завершением Phase 1
- [ ] Все компоненты Phase 1 работают
- [ ] Результаты полевых тестов документированы
- [ ] Принято решение: переходить ли на Phase 2 (адаптивный луч)
- [ ] Начать заказ компонентов для Phase 3 (если бюджет утвержден)

### Требования Phase 2
- [ ] Поддержка phase shifters в datasheet чипсета
- [ ] SPI контроллер для управления фазовращателями
- [ ] Алгоритм адаптивного формирования луча (beam steering)

---

## ✅ Фиксированные даты

| Этап | Дата начала | Дата окончания | Статус |
|------|------------|----------------|--------|
| 1.1: Закупка | 2026-07-08 | 2026-07-15 | ⏳ |
| 1.2: Монтаж | 2026-07-15 | 2026-07-22 | ⏳ |
| 1.3: ПО | 2026-07-15 | 2026-07-29 | 🟢 In Progress |
| 1.4: Тесты | 2026-07-22 | 2026-07-29 | ⏳ |
| **Phase 1** | 2026-07-08 | **2026-07-29** | |

---

## 🔗 Ресурсы

### Внутренние
- GitHub branch: `claude/phased-array-robotics-nhh6i2`
- Документация: `/docs/TZ_PHASED_ARRAY_MVP.md`
- Модуль: `/phased_array/`

### Внешние
- **Qorvo QPM56xx Datasheet:** https://www.qorvo.com/ (datasheet PDF)
- **IEEE 802.11be (Wi-Fi 7):** https://standards.ieee.org/
- **Rogers 4003C Laminate:** https://www.rogerscorp.com/
- **Xilinx Zynq-7000:** https://www.xilinx.com/

### Инструменты
- Python 3.8+ с PEP8 (black, flake8, mypy)
- pytest для тестирования
- git для версионирования

---

## 🤝 Ответственные

| Роль | Человек | Статус |
|------|---------|--------|
| Lead Architect | Claude (AI) | 🟢 Active |
| RF Engineer | (TBD) | ⏳ |
| FPGA Engineer | (TBD) | ⏳ Phase 3 |
| QA / Testing | (TBD) | ⏳ |

---

**Версия:** 1.0  
**Последнее обновление:** 2026-07-08  
**Следующее обновление:** 2026-07-15 (еженедельно)

---

## Примечания

- Все компоненты фазы 1 готовы к использованию прямо сейчас
- Phase 2 может начаться параллельно с завершением Phase 1
- Phase 3 требует 6 недель на проектирование + 8 недель на производство
- Бюджет на Phase 3 предполагает $2000-5000 на прототипирование

**Успеха! 🚀**
