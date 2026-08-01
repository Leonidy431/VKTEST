# Голосовая связь через ФАР (Audio Streaming Specification)

**Версия:** 1.0  
**Статус:** MVP Phase 1 (планируется неделя 1-3)  
**Дата:** 2026-07-08

---

## 1. Обзор функционала

### Цель
Реализовать двусторонние голосовые звонки между робототехнической платформой и смартфоном через Wi-Fi 5.8 ГГц с адаптацией к качеству радиоканала.

### Область применения
- 🤖 Голосовое управление роботом оператором
- 📱 Видеоконференция на смартфоне (вместе с видеопотоком)
- 🔊 Оповещения в реальном времени
- 📡 Связь при отсутствии мобильной сети

### Поддерживаемые режимы

| Режим | Задержка | Качество | Сценарий |
|-------|----------|----------|----------|
| **VoIP Standard** | 80–150 мс | Высокое (MOS 3.5–4.5) | Стандартные звонки, видеоконференции |
| **Low-Latency** | 30–50 мс | Среднее (MOS 3.0–4.0) | Управление в реальном времени |
| **Network-Adaptive** | Варьируется | Адаптивное | При слабом сигнале (автоматический downgrade) |

---

## 2. Архитектура

### Стек протоколов

```
┌─────────────────────────────────────────┐
│       Application Layer                 │
│  (VoIP App, Telegram, WhatsApp, etc)   │
└────────────┬────────────────────────────┘
             │
┌────────────▼────────────────────────────┐
│    Transport Layer                      │
│  RTP (Real-time Protocol)               │
│  Port: 5004-5005 (audio)                │
└────────────┬────────────────────────────┘
             │
┌────────────▼────────────────────────────┐
│    Codec Layer (AudioStreamer)          │
│  • Opus (переменный битрейт)           │
│  • GSM AMR (адаптивный)                │
│  • PCMU (VoIP стандарт)                │
└────────────┬────────────────────────────┘
             │
┌────────────▼────────────────────────────┐
│    RF Management (BeamForming)          │
│  • Адаптивный луч (максимизировать RSSI)|
│  • Мониторинг качества сигнала         │
│  • Автоматическая смена кодека         │
└────────────┬────────────────────────────┘
             │
┌────────────▼────────────────────────────┐
│    Physical Layer (Wi-Fi 5.8 GHz)       │
│  RF Module (Qorvo/Wi-Fi 7)              │
└─────────────────────────────────────────┘
```

### Компоненты MVP

| Компонент | Файл | Назначение |
|-----------|------|-----------|
| **AudioStreamer** | `audio_streamer.py` | Захват/кодирование/передача аудио |
| **AudioCodec** | `audio_streamer.py` | Выбор кодека (Opus, GSM AMR, PCMU) |
| **AudioMode** | `audio_streamer.py` | Режим работы (VoIP, low-latency, adaptive) |
| **RFModule** | `rf_module.py` | Мониторинг RSSI и управление мощностью TX |
| **BeamForming** | `beamforming.py` | Адаптивное направление луча |
| **PowerManager** | `power_manager.py` | Контроль энергопотребления |

---

## 3. Технические требования

### 3.1 Функциональные требования

| Требование | Значение | Приоритет |
|-----------|----------|-----------|
| Поддерживаемые кодеки | Opus, GSM AMR, PCMU | P0 |
| Минимальный битрейт | 4.75 кбит/сек (GSM AMR) | P0 |
| Максимальный битрейт | 128 кбит/сек (Opus) | P1 |
| Задержка (VoIP mode) | <150 мс | P0 |
| Задержка (Low-latency) | <50 мс | P1 |
| Поддержка duplex | Full-duplex (одновременная передача и приём) | P0 |
| Адаптация к сигналу | Автоматический выбор кодека по RSSI | P1 |
| Sample rate | 16 кHz (телефонный стандарт) | P0 |

### 3.2 Нефункциональные требования

| Требование | Значение |
|-----------|----------|
| CPU на робот | <15% использования (MCU/SoC) |
| Память | <10 МБ ОЗУ для буферизации |
| Формат аудио | WAV, PCM (16-бит, 16 кHz) |
| Платформы поддержки | Linux (ESP32/Zynq/Raspberry Pi) |
| Совместимость | SIP, RTP (RFC 3550) |

---

## 4. Алгоритмы адаптации

### 4.1 Выбор кодека по качеству сигнала

```python
RSSI (дБм)  | Кодек       | Битрейт | MOS
-----------+-------------+---------+------
> -70       | Opus        | 24–128 к| 4–5
-70 to -80  | GSM AMR     | 8–12 к  | 3–4
< -80       | GSM AMR min | 4.75 к  | 2–3
```

**Алгоритм:**
```
if RSSI > -70 dBm:
    codec = Opus (максимальное качество)
elif RSSI > -80 dBm:
    codec = GSM AMR (8–12 kbps)
else:
    codec = GSM AMR (4.75 kbps, экономия пропускной способности)
```

### 4.2 Оценка максимального битрейта

Формула Шеннона (упрощенная):
```
C = BW * log2(1 + S/N)

где:
  C = пропускная способность (бит/сек)
  BW = ширина полосы (20 МГц для Wi-Fi)
  S/N = отношение сигнал/шум (зависит от RSSI)
```

**Практическая оценка:**
```
bitrate = 300 kbps * 10^((RSSI + 100) / 20)
```

### 4.3 Контроль качества (MOS Score)

**Mean Opinion Score (MOS)** — субъективная оценка качества голоса (1–5):
- **5** = Отличное качество (отсутствие артефактов)
- **4** = Хорошее качество (минимальные артефакты)
- **3** = Приемлемое качество (заметные, но не раздражающие артефакты)
- **2** = Плохое качество (значительные артефакты)
- **1** = Невозможно использовать

**Оценка MOS:**
```
MOS = 4.5 - RSSI_factor - latency_factor

RSSI_factor:
  0.0 если RSSI > -70 dBm (отличный сигнал)
  1.0 если -80 < RSSI ≤ -70 dBm (хороший сигнал)
  2.0 если RSSI ≤ -80 dBm (слабый сигнал)

latency_factor:
  0.0 если latency < 50 ms (отличная задержка)
  0.5 если 50 ≤ latency < 100 ms (хорошая задержка)
  1.0 если latency ≥ 100 ms (плохая задержка)
```

### 4.4 Адаптивное управление лучом

При падении RSSI ниже порога (-80 дБм):
1. Активировать `BeamForming.scan_beam_pattern()`
2. Найти направление с максимальным усилением
3. Направить луч в сторону телефона: `BeamForming.point_beam(azimuth, elevation)`
4. Переоценить RSSI и MOS

**Результат:** Усиление +3–6 дБ → повышение дальности на 50%.

---

## 5. API Reference

### 5.1 Инициализация

```python
from phased_array import AudioStreamer, AudioMode, AudioCodec, RFModule

# Инициализировать RF и audio
rf = RFModule()
rf.initialize()

streamer = AudioStreamer(
    rf_module=rf,
    mode=AudioMode.VOIP_STANDARD,
    codec=AudioCodec.OPUS
)
```

### 5.2 Захват и передача аудио

```python
# Начать захват микрофона
streamer.start_streaming()

# В основном цикле: захватить фрейм PCM (20ms @ 16kHz)
pcm_frame = capture_audio_frame()  # 320 байт (16-бит стерео)

# Адаптировать к условиям сети
current_codec = streamer.adapt_to_network_conditions()

# Создать пакет для передачи
packet = streamer.create_audio_packet(pcm_frame, current_codec)

# Отправить по сети
send_rtp_packet(packet.payload, packet.sequence_number)

# Получить метрики качества
metrics = streamer.get_quality_metrics()
print(f"MOS: {metrics.mos_score:.2f}, Latency: {metrics.latency_ms:.1f}ms")
```

### 5.3 Прием аудио

```python
# На стороне телефона: декодировать пакет
received_packet = receive_rtp_packet()

# Декодировать аудиоданные
audio_data = decode_audio(
    received_packet.payload,
    codec=received_packet.codec
)

# Воспроизвести
play_audio(audio_data)
```

### 5.4 Останов

```python
streamer.stop_streaming()
```

---

## 6. Интеграция с контроллером робота

### 6.1 State Machine

Добавить в `control/state_machine.py`:

```python
class RobotState(Enum):
    IDLE = 'idle'
    RF_INIT = 'rf_init'              # NEW: Инициализация RF
    RF_AUDIO_STREAMING = 'rf_audio'  # NEW: Передача голоса
    RF_VIDEO_STREAMING = 'rf_video'  # NEW: Видеопоток
    MOTION_CONTROL = 'motion'
    # ...

class RobotController:
    def __init__(self):
        # Инициализировать RF
        self.rf_module = RFModule()
        self.rf_module.initialize()
        self.state = RobotState.RF_INIT
        
        # Инициализировать аудио
        self.audio_streamer = AudioStreamer(rf_module=self.rf_module)
```

### 6.2 Основной цикл управления

```python
def control_loop(self, dt):
    """Основной цикл с интеграцией аудио."""
    
    # Получить текущий RSSI
    rssi = self.rf_module.get_rssi()
    
    # Если телефон подключен и запрашивает голос
    if self.incoming_audio_request:
        if self.state != RobotState.RF_AUDIO_STREAMING:
            self.audio_streamer.start_streaming()
            self.state = RobotState.RF_AUDIO_STREAMING
        
        # Адаптировать параметры к условиям сети
        self.audio_streamer.adapt_to_network_conditions()
        
        # Если сигнал слабый — направить луч оптимально
        if rssi < -80:
            self.beamforming.scan_beam_pattern()
        
        # Захватить и отправить аудиофрейм
        pcm_frame = self.microphone.capture(duration_ms=20)
        packet = self.audio_streamer.create_audio_packet(
            pcm_frame,
            self.audio_streamer.preferred_codec
        )
        self.network.send_rtp_packet(packet)
    
    # Если звонок завершен
    else:
        if self.state == RobotState.RF_AUDIO_STREAMING:
            self.audio_streamer.stop_streaming()
            self.state = RobotState.IDLE
    
    # Логирование метрик
    if self.state == RobotState.RF_AUDIO_STREAMING:
        metrics = self.audio_streamer.get_quality_metrics()
        self.logger.debug(f"Audio QoS: MOS={metrics.mos_score:.2f}, "
                         f"loss={metrics.packet_loss_percent:.1f}%")
```

---

## 7. Тестирование

### 7.1 Unit Tests (12 тестов)

```bash
pytest phased_array/tests/test_audio_streamer.py -v

# Примеры тестов:
# ✓ test_codec_selection_strong_signal
# ✓ test_bitrate_estimation
# ✓ test_mos_score_range
# ✓ test_network_adaptation
```

### 7.2 Интеграционные тесты (неделя 2)

```python
# Тест 1: Захват микрофона + передача Opus
def test_microphone_capture_and_encode():
    streamer = AudioStreamer(mode=AudioMode.LOW_LATENCY)
    streamer.start_streaming()
    # Ожидаемо: пакеты не потеряны, задержка <50ms

# Тест 2: Адаптация при падении RSSI
def test_adaptive_codec_switch():
    # Симуляция: RSSI упал с -65 до -85 дБм
    # Ожидаемо: кодек автоматически переключился на GSM AMR

# Тест 3: MOS score calculation
def test_mos_score_degradation():
    # Симуляция: RSSI -85, задержка 150ms
    # Ожидаемо: MOS < 3.0
```

### 7.3 Полевые тесты (неделя 3)

| Тест | Условия | Критерий приемки |
|------|---------|------------------|
| **Дальность 50m** | Open space, LoS | MOS > 3.5, loss < 1% |
| **Дальность 80m** | Open space, LoS | MOS > 3.0, loss < 3% |
| **С препятствиями** | Деревья, кусты | MOS > 2.5, loss < 5% |
| **Помехи** | Соседние Wi-Fi | Работает, MOS > 2.0 |
| **Динамика** | Робот движется | Не более 5 разрывов соединения |

---

## 8. Фазы разработки

### Phase 1: MVP (неделя 1-3) ✅ IN PROGRESS

**Что реализуется:**
- ✅ AudioStreamer с поддержкой Opus, GSM AMR
- ✅ Адаптивный выбор кодека по RSSI
- ✅ Расчет MOS и метрик качества
- ✅ 12 unit тестов (все passing)
- ✅ Интеграция с RFModule и BeamForming

**Deliverables:**
- Python модуль (300 строк кода)
- 12 passing тестов
- Документация (этот файл)

### Phase 2: Optimization (неделя 4-6)

**Что добавится:**
- Реальный захват микрофона (PyAudio, ALSA)
- RTP/SDP интеграция (RFC 3550, RFC 4566)
- Буферизация и frame synchronization
- JitterBuffer для компенсации дрожания задержки
- Шумоподавление (noise gate, echo cancellation)
- Тестирование в полевых условиях

**Deliverables:**
- Работающая система звонков robot ↔ phone
- Расчет диаграммы битрейта vs. дальность
- Отчет о полевых тестах

### Phase 3: Advanced Features (неделя 7-12)

**Что добавится:**
- Поддержка видеопотока вместе с аудио
- Многопользовательские конференции
- Компрессия с переменным битрейтом (VBR)
- Защита от потери пакетов (FEC — Forward Error Correction)
- Интеграция с SIP сервером (VoIP)
- Сертификация на соответствие ITU-T G.131

---

## 9. Критерии приемки

### MVP Phase 1

- [x] AudioStreamer модуль реализован
- [x] Поддержка кодеков (Opus, GSM AMR, PCMU)
- [x] 12 unit тестов, все passing
- [ ] Интеграция в state_machine.py
- [ ] Документация на русском и английском

### Phase 1 Hardware Validation

- [ ] Звонок работает на дальности 50 м (open space)
- [ ] MOS score > 3.5 при RSSI -75 дБм
- [ ] Потеря пакетов < 2% при нормальных условиях
- [ ] Задержка < 150 мс (VoIP mode)
- [ ] Адаптация кодека работает при изменении RSSI

---

## 10. Нормативные ссылки

- **RFC 3550** — Real-time Transport Protocol (RTP)
- **RFC 3551** — RTP Payload Format
- **ITU-T G.711** — PCM кодирование (64 kbps)
- **ITU-T G.729** — Кодирование 8 kbps
- **RFC 3389** — RTP Comfort Noise (CN)
- **ITU-T G.131** — ITU Delay and Transmission Media (рекомендация по задержкам)
- **3GPP TS 26.090** — AMR (Adaptive Multi-Rate) кодирование

---

## 11. Глоссарий

| Термин | Определение |
|--------|----------|
| **RTP** | Real-time Transport Protocol — протокол передачи реального времени |
| **VoIP** | Voice over IP — передача голоса по IP сети |
| **MOS** | Mean Opinion Score — субъективная оценка качества (1–5) |
| **Opus** | Современный кодек переменного битрейта (от 6 до 510 kbps) |
| **GSM AMR** | Adaptive Multi-Rate — кодек мобильных сетей (4.75–12.2 kbps) |
| **RSSI** | Received Signal Strength Indicator — мощность полученного сигнала |
| **Jitter** | Дрожание задержки (вариативность задержки пакетов) |
| **FEC** | Forward Error Correction — коррекция ошибок вперед |
| **Latency** | Общая задержка передачи пакета (мс) |

---

**Версия:** 1.0  
**Статус:** Ready for Phase 1 implementation  
**Автор:** Claude Code AI  
**Дата последнего обновления:** 2026-07-08
