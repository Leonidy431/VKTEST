# Phased Array Robotics (ФАР) — MVP Module

Модуль для управления фазированной антенной решеткой (AESA) робототехнической платформы.

**Status:** Alpha (MVP Phase 1)  
**Version:** 1.0.0-alpha  
**Python:** ≥3.8 (PEP8 compliance)

---

## Overview

ФАР обеспечивает:
- 📡 Высокоскоростную связь `robot ↔ phone` (Wi-Fi 7 / 5.8 ГГц)
- 📊 Адаптивное управление мощностью TX/RX
- 🎯 Формирование луча (beamforming) для увеличения дальности
- 🌡️ Контроль температурного режима Power Amplifier
- 📝 Логирование метрик (RSSI, фаза, температура)

**MVP использует готовые RF модули:**
- Qorvo QPM56xx series (evaluation board)
- Wi-Fi 7 чипсеты (MediaTek / Qualcomm)
- Встроенное управление beamforming в чипсете

---

## Installation

### Требования
```bash
python3 -m pip install -r requirements.txt
# или для разработки:
python3 -m pip install -e ".[dev]"
```

### Структура модуля
```
phased_array/
├── __init__.py                 # Точка входа модуля
├── config.py                   # Конфиг RF параметров (PEP8)
├── rf_module.py               # API для RF чипсета
├── beamforming.py             # Алгоритмы формирования луча
├── power_manager.py           # Управление энергопотреблением
├── data_logger.py             # Логирование метрик
├── tests/
│   ├── test_rf_module.py
│   ├── test_beamforming.py
│   └── test_power_manager.py
├── docs/
│   └── antenna_patterns.md
└── README.md                  # Этот файл
```

---

## Quick Start

### Базовая инициализация

```python
from phased_array import RFModule, BeamForming, PowerManager

# Инициализировать RF модуль (Qorvo, Wi-Fi 7)
rf = RFModule(chip='Qorvo_QPM5680')
rf.initialize()

# Включить режим приема
rf.enable_rx()

# Получить RSSI (мощность сигнала)
rssi = rf.get_rssi()  # -85 дБм
print(f'Signal strength: {rssi} dBm')
```

### Управление формированием луча

```python
from phased_array import BeamForming

# Инициализировать beamforming (4-элементный массив)
bf = BeamForming(num_elements=4)

# Направить луч на целевой объект
beam = bf.point_beam(azimuth_deg=45.0, elevation_deg=0.0)
print(f'Beam pattern: {beam}')

# Сканировать для поиска оптимального луча
patterns = bf.scan_beam_pattern(step_deg=10.0)
best = max(patterns, key=lambda p: p.gain_dbi)
print(f'Best direction: {best.azimuth_deg}°')
```

### Управление мощностью TX

```python
from phased_array import PowerManager

# Создать менеджер мощности
pm = PowerManager(rf_module=rf)

# Адаптивное управление мощностью по RSSI
rssi = rf.get_rssi()
recommended_power = pm.optimize_tx_power(rssi_dbm=rssi)
pm.apply_tx_power(recommended_power)
```

### Логирование метрик

```python
from phased_array import DataLogger
from datetime import datetime

# Инициализировать логгер
logger = DataLogger()

# Логировать метрику
from phased_array.data_logger import LogEntry
entry = LogEntry(
    timestamp_s=datetime.now().timestamp(),
    rssi_dbm=-85.0,
    phase_error_deg=0.0,
    tx_power_dbm=20.0,
    frequency_hz=5.8e9,
    pa_temperature_c=35.0,
    thermal_state='normal'
)
logger.log_metric(entry)

# Экспортировать в CSV
logger.export_to_csv('/tmp/rf_metrics.csv')
```

---

## Configuration (PEP8 Style)

Все параметры конфига в `config.py` — классовые переменные с типами:

```python
from phased_array.config import Config

# Частота работы (SI units)
print(Config.FREQUENCY_CENTER_HZ)  # 5.5e9 (5.5 ГГц)

# Мощность TX (дБм)
print(Config.TX_POWER_DEFAULT_DBM)  # 20

# Температурные пределы (°C)
print(Config.TEMP_AMBIENT_C)  # 25
print(Config.TEMP_RISE_LIMIT_C)  # 15

# Параметры антенны
print(Config.NUM_ELEMENTS)  # 4
print(Config.ELEMENT_SPACING_LAMBDA)  # 0.5

# Валидация
Config.validate()  # True / False
```

---

## Development Phases

### ✅ Phase 1: MVP (неделя 1-3)
- Готовые RF модули (Qorvo / Wi-Fi 7)
- Управление TX/RX
- Адаптивная мощность
- Базовое логирование

### 🔜 Phase 2: Optimization (неделя 4-6)
- Встроенное управление фазой в чипсете
- Алгоритм scan_beam_pattern
- Тестирование в реальной среде
- Документирование RF параметров

### 🔜 Phase 3: Full Custom (неделя 7-12)
- Собственная ФАР плата (KiCad)
- FPGA управление фазовращателями
- Цифровое beamforming (DBF)
- Адаптивное формирование луча

---

## Testing

Запуск всех тестов:
```bash
python3 -m pytest phased_array/tests/ -v

# С покрытием:
python3 -m pytest phased_array/tests/ --cov=phased_array --cov-report=html

# Конкретный тест:
python3 -m pytest phased_array/tests/test_rf_module.py::TestRFModuleInit::test_initialization -v
```

**Текущее покрытие тестами:**
- ✅ RF Module: инициализация, TX/RX, мощность, RSSI
- ✅ BeamForming: расчет весов, сканирование, усиление
- ⏳ PowerManager: адаптивная мощность, тепловой контроль
- ⏳ DataLogger: логирование, экспорт, ротация

---

## RF Specifications (MVP)

### Частота и мощность
| Параметр | Значение |
|----------|----------|
| Рабочий диапазон | 5.15–5.85 ГГц |
| Мощность TX | 14–22 дБм |
| Чувствительность RX | -82 дБм @ 10 Mbps |
| Усиление антенны | 8 дBi |

### Интерфейсы
| Интерфейс | Параметр |
|-----------|----------|
| SPI | 10 МГц, режим 0 |
| I2C | 400 кГц, адрес 0x50 |
| UART | 115200 baud (отладка) |

### Тепловой режим
| Параметр | Значение |
|----------|----------|
| T окружающей | 25°C |
| Макс. повышение T | 15°C |
| Предел PA | 95°C |
| Постоянная времени | 60 s |

---

## Integration with VKTEST

### Подключение к основному контроллеру робота

```python
# robot_controller.py
from phased_array import RFModule, BeamForming
from control import MainController

class EnhancedRobotController(MainController):
    def __init__(self):
        super().__init__()
        self.rf_module = RFModule()
        self.rf_module.initialize()
        self.beamforming = BeamForming()
    
    def control_loop(self, dt):
        """Основной цикл с RF интеграцией."""
        super().control_loop(dt)
        
        # RF компонент: адаптивное управление лучом
        rssi = self.rf_module.get_rssi()
        if rssi < -80:
            self.beamforming.scan_beam_pattern()
```

### States в конечном автомате

Добавить RF состояния в `control/state_machine.py`:
- `RF_INIT` — инициализация модуля
- `RF_RX` — режим приема
- `RF_TX` — режим передачи
- `RF_SCAN` — сканирование луча

---

## Troubleshooting

### RF Module не инициализируется
```python
rf = RFModule()
if not rf.initialize():
    print(rf.state)  # RFState.ERROR
    # Проверить SPI интерфейс, питание
```

### Слабый сигнал (RSSI < -85 дБм)
```python
# 1. Повысить TX мощность
rf.set_tx_power(22.0)

# 2. Оптимизировать луч
bf.scan_beam_pattern()

# 3. Приблизить антенну к целевому устройству
# (проверить физическую разводку кабелей)
```

### Перегрев PA (T > 95°C)
```python
# Система автоматически дросселирует мощность TX
# Проверить теплоотвод (радиатор, вентиляция)
pm.thermal_state  # ThermalState.HOT
```

---

## API Reference

### RFModule
```python
class RFModule:
    def initialize() -> bool
    def enable_rx() -> bool
    def enable_tx() -> bool
    def disable_tx() -> bool
    def set_tx_power(power_dbm: float) -> bool
    def get_rssi() -> float
    def get_metrics() -> RFMetrics
    def get_state() -> RFState
    def get_chip_info() -> dict
```

### BeamForming
```python
class BeamForming:
    def point_beam(azimuth_deg: float, elevation_deg: float = 0.0) -> BeamPattern
    def scan_beam_pattern(step_deg: float = 10.0) -> List[BeamPattern]
    def get_phase_weights() -> List[float]
    def get_amplitude_weights() -> List[float]
    def calculate_gain_at_angle(azimuth_deg: float, elevation_deg: float = 0.0) -> float
```

### PowerManager
```python
class PowerManager:
    def optimize_tx_power(rssi_dbm: float, target_rssi_dbm: float = -75.0) -> float
    def apply_tx_power(power_dbm: float) -> bool
    def update_thermal_state(pa_temperature_c: float) -> ThermalState
    def get_power_metrics(tx_power_dbm: float, pa_temp_c: float) -> PowerMetrics
```

### DataLogger
```python
class DataLogger:
    def log_metric(entry: LogEntry) -> None
    def log_event(event_type: str, message: str, rssi_dbm: float = -100.0) -> None
    def get_recent_metrics(count: int = 100) -> List[LogEntry]
    def export_to_csv(output_file_path: str) -> None
    def get_statistics() -> dict
```

---

## Documentation

- 📋 [TZ_PHASED_ARRAY_MVP.md](../docs/TZ_PHASED_ARRAY_MVP.md) — Техническое задание
- 📊 [RF Parameters](docs/rf_parameters.md) — RF характеристики (будет добавлен)
- 🎯 [Antenna Patterns](docs/antenna_patterns.md) — Диаграммы направленности (будет добавлен)
- 🔧 [Installation Guide](docs/installation_guide.md) — Руководство монтажа (будет добавлен)

---

## Contributing

Для добавления функциональности фаз 2-3:

1. Создайте ветку: `git checkout -b feature/phase2-adaptive-beamforming`
2. Добавьте тесты в `tests/`
3. Следуйте PEP8: `black`, `flake8`, `mypy`
4. Pull Request в `main`

---

## License

Проект VKTEST. Внутреннее использование.

**Автор:** Robotics Team  
**Дата:** 2026-07-08
