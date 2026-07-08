"""
Модуль для передачи голоса и аудиопотока через ФАР систему.

Features:
- Захват аудио с микрофона робота
- Кодирование (GSM AMR, Opus, PCMU)
- Передача по Wi-Fi с адаптивным битрейтом
- Декодирование на телефоне
- Контроль качества и задержки (latency monitoring)
- Адаптивный алгоритм при слабом сигнале

Поддерживает три режима:
1. VoIP Mode: стандартные кодеки SIP/RTP
2. Low-Latency Mode: минимизация задержки (<50ms)
3. Network-Adaptive Mode: автоматическая адаптация к качеству сигнала
"""

import logging
import time
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Callable

from .config import Config
from .rf_module import RFModule


class AudioCodec(Enum):
    """Поддерживаемые аудиокодеки."""
    PCM_16BIT = 'pcm_16bit'      # Без сжатия (256 kbps @ 16kHz)
    GSM_AMR = 'gsm_amr'          # GSM AMR (4.75–12.2 kbps)
    OPUS = 'opus'                # Opus (8–128 kbps, переменный битрейт)
    PCMU = 'pcmu'                # μ-law (64 kbps, стандарт VoIP)


class AudioMode(Enum):
    """Режимы работы аудиопотока."""
    VOIP_STANDARD = 'voip_standard'        # SIP/RTP (качество >90%)
    LOW_LATENCY = 'low_latency'            # Минимальная задержка (<50ms)
    NETWORK_ADAPTIVE = 'network_adaptive'  # Адаптивная работа при плохом сигнале


@dataclass
class AudioPacket:
    """Пакет аудиоданных для передачи."""
    sequence_number: int          # Номер пакета (для восстановления порядка)
    timestamp_ms: float           # Временная метка (миллисекунды)
    codec: AudioCodec             # Использованный кодек
    bitrate_kbps: float           # Битрейт (кбит/сек)
    frame_duration_ms: int        # Длительность фрейма (типично 20ms)
    payload: bytes                # Закодированные аудиоданные
    rssi_dbm: float               # RSSI на момент передачи


@dataclass
class AudioQualityMetrics:
    """Метрики качества аудиопотока."""
    packet_loss_percent: float    # Потеря пакетов (%)
    latency_ms: float             # Задержка end-to-end (мс)
    jitter_ms: float              # Дрожание задержки (мс)
    mos_score: float              # MOS (Mean Opinion Score, 1-5)
    bitrate_kbps: float           # Текущий битрейт
    rssi_dbm: float               # Текущий RSSI


class AudioStreamer:
    """
    Управление голосовой связью через ФАР систему.

    MVP поддерживает:
    - Захват PCM с микрофона
    - Простое кодирование (GSM AMR, Opus)
    - RTP пакетизацию
    - Адаптивный выбор кодека по RSSI
    """

    def __init__(self, rf_module: Optional[RFModule] = None,
                 mode: AudioMode = AudioMode.VOIP_STANDARD,
                 codec: AudioCodec = AudioCodec.OPUS):
        """
        Инициализация audio streamer.

        Args:
            rf_module: Ссылка на RFModule для мониторинга качества сигнала
            mode: Режим работы (VoIP, low-latency, adaptive)
            codec: Предпочтительный кодек
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.rf_module = rf_module
        self.mode = mode
        self.preferred_codec = codec
        self.is_streaming = False

        # Параметры потока
        self.sample_rate_hz = 16000  # 16 kHz (стандарт для VoIP)
        self.frame_duration_ms = 20  # Стандартный фрейм
        self.sequence_number = 0

        # История для расчета метрик
        self.packet_timestamps = []
        self.rssi_history = []
        self.max_history = 100

        # Callback для приложения
        self.on_packet_received: Optional[Callable[[AudioPacket], None]] = None
        self.on_quality_degraded: Optional[Callable[[AudioQualityMetrics], None]] = None

        self.logger.info(
            f'AudioStreamer initialized: mode={mode.value}, codec={codec.value}'
        )

    def start_streaming(self) -> bool:
        """
        Начать захват и передачу аудио.

        Returns:
            True если успешно, False если ошибка
        """
        if self.is_streaming:
            self.logger.warning('Audio streaming already active')
            return False

        try:
            self.logger.info('Starting audio streaming...')
            # Симуляция инициализации аудиоустройства
            self._init_audio_device()
            self.is_streaming = True
            self.logger.info('Audio streaming started')
            return True

        except Exception as e:
            self.logger.error(f'Failed to start streaming: {e}')
            return False

    def stop_streaming(self) -> bool:
        """Остановить захват аудио."""
        if not self.is_streaming:
            return False

        try:
            self._cleanup_audio_device()
            self.is_streaming = False
            self.logger.info('Audio streaming stopped')
            return True
        except Exception as e:
            self.logger.error(f'Failed to stop streaming: {e}')
            return False

    def select_codec_by_signal_quality(self, rssi_dbm: float) -> AudioCodec:
        """
        Выбрать оптимальный кодек в зависимости от качества сигнала (RSSI).

        Алгоритм адаптации:
        - RSSI >= -70 dBm: высокое качество → Opus (переменный битрейт)
        - RSSI -70 to -80: среднее качество → GSM AMR (8-12 kbps)
        - RSSI < -80 dBm: низкое качество → GSM AMR минимум (4.75 kbps)

        Args:
            rssi_dbm: Текущий RSSI (дБм)

        Returns:
            Рекомендуемый кодек
        """
        if rssi_dbm >= -70:
            selected = AudioCodec.OPUS
        elif rssi_dbm >= -80:
            selected = AudioCodec.GSM_AMR
        else:
            selected = AudioCodec.GSM_AMR  # Минимум, но всё ещё работает

        self.logger.debug(f'Selected codec {selected.value} for RSSI={rssi_dbm:.1f} dBm')
        return selected

    def estimate_bitrate_by_rssi(self, rssi_dbm: float) -> float:
        """
        Оценить максимально возможный битрейт для аудио.

        Формула упрощенная (в продакшене нужна полная модель канала):
        bitrate = 300 kbps * 10^((RSSI + 100) / 20)

        Args:
            rssi_dbm: Текущий RSSI (дБм)

        Returns:
            Максимальный битрейт (кбит/сек)
        """
        import math
        # Нормализация RSSI (-100 до 0 дБм)
        rssi_norm = max(-100, min(0, rssi_dbm))
        # Экспоненциальная зависимость
        bitrate = 4.0 * math.pow(10, (rssi_norm + 100) / 40)
        return bitrate

    def create_audio_packet(self, pcm_data: bytes, codec: AudioCodec) -> AudioPacket:
        """
        Создать RTP пакет с аудиоданными.

        Args:
            pcm_data: Необработанные PCM данные (16-бит, 16 кHz)
            codec: Кодек для сжатия

        Returns:
            AudioPacket готовый к передаче
        """
        # Получить текущий RSSI если RF модуль доступен
        rssi = self.rf_module.get_rssi() if self.rf_module else -80.0

        # Кодирование (симуляция)
        encoded_data = self._encode_audio(pcm_data, codec)
        bitrate = self.estimate_bitrate_by_rssi(rssi)

        packet = AudioPacket(
            sequence_number=self.sequence_number,
            timestamp_ms=time.time() * 1000,
            codec=codec,
            bitrate_kbps=bitrate,
            frame_duration_ms=self.frame_duration_ms,
            payload=encoded_data,
            rssi_dbm=rssi,
        )

        self.sequence_number += 1
        self.logger.debug(
            f'Audio packet created: seq={packet.sequence_number}, '
            f'codec={codec.value}, size={len(encoded_data)} bytes'
        )

        return packet

    def get_quality_metrics(self) -> AudioQualityMetrics:
        """
        Расчет метрик качества аудиопотока.

        Returns:
            AudioQualityMetrics с текущими показателями
        """
        # Средний RSSI
        avg_rssi = sum(self.rssi_history) / len(self.rssi_history) if self.rssi_history else -80.0
        self.rssi_history = self.rssi_history[-self.max_history:]

        # Расчет задержки и jitter
        if len(self.packet_timestamps) > 1:
            deltas = [
                self.packet_timestamps[i+1] - self.packet_timestamps[i]
                for i in range(len(self.packet_timestamps)-1)
            ]
            avg_latency = sum(deltas) / len(deltas)
            jitter = max(deltas) - min(deltas) if deltas else 0
        else:
            avg_latency = 20.0  # Один фрейм
            jitter = 0.0

        # MOS (Mean Opinion Score) на основе RSSI и задержки
        # Упрощенная модель
        mos = self._estimate_mos(avg_rssi, avg_latency)

        # Потеря пакетов (симуляция)
        packet_loss = max(0, (avg_rssi + 85) / 50) if avg_rssi < -85 else 0.0

        return AudioQualityMetrics(
            packet_loss_percent=packet_loss,
            latency_ms=avg_latency,
            jitter_ms=jitter,
            mos_score=mos,
            bitrate_kbps=self.estimate_bitrate_by_rssi(avg_rssi),
            rssi_dbm=avg_rssi,
        )

    def adapt_to_network_conditions(self) -> AudioCodec:
        """
        Адаптировать параметры потока к текущим условиям сети.

        Returns:
            Новый рекомендуемый кодек
        """
        if not self.rf_module:
            return self.preferred_codec

        rssi = self.rf_module.get_rssi()
        self.rssi_history.append(rssi)
        self.rssi_history = self.rssi_history[-self.max_history:]

        metrics = self.get_quality_metrics()

        # Проверка деградации качества
        if metrics.packet_loss_percent > 5 or metrics.latency_ms > 150:
            self.logger.warning(f'Network quality degraded: {metrics}')
            if self.on_quality_degraded:
                self.on_quality_degraded(metrics)

        # Выбрать кодек
        new_codec = self.select_codec_by_signal_quality(rssi)
        if new_codec != self.preferred_codec:
            self.logger.info(f'Codec changed: {self.preferred_codec.value} → {new_codec.value}')
            self.preferred_codec = new_codec

        return new_codec

    # === PRIVATE METHODS ===

    def _init_audio_device(self) -> None:
        """Инициализация аудиоустройства (микрофон + динамик)."""
        self.logger.debug('Initializing audio device (microphone & speaker)...')
        # В продакшене: инициализация PyAudio, ALSA или встроенного аудиокодека

    def _cleanup_audio_device(self) -> None:
        """Очистка аудиоресурсов."""
        self.logger.debug('Cleaning up audio device...')

    def _encode_audio(self, pcm_data: bytes, codec: AudioCodec) -> bytes:
        """Кодирование PCM данных (симуляция)."""
        # В продакшене: использовать pydub, opus, gsm библиотеки
        # Здесь просто возвращаем первые N байт для симуляции
        if codec == AudioCodec.PCM_16BIT:
            return pcm_data
        elif codec == AudioCodec.OPUS:
            return pcm_data[:len(pcm_data)//4]  # Симуляция сжатия 4:1
        elif codec == AudioCodec.GSM_AMR:
            return pcm_data[:len(pcm_data)//8]  # Симуляция сжатия 8:1
        else:
            return pcm_data

    def _estimate_mos(self, rssi_dbm: float, latency_ms: float) -> float:
        """
        Оценка MOS (Mean Opinion Score, 1-5) на основе RSSI и задержки.

        MOS = 4.5 - (RSSI_factor) - (latency_factor)
        где:
            RSSI_factor: 0 если >-70, 1 если -70 to -85, 2 если <-85
            latency_factor: 0 если <50ms, 0.5 если 50-100ms, 1 если >100ms
        """
        rssi_factor = 0.0 if rssi_dbm > -70 else (1.0 if rssi_dbm > -85 else 2.0)
        latency_factor = 0.0 if latency_ms < 50 else (0.5 if latency_ms < 100 else 1.0)
        mos = max(1.0, min(5.0, 4.5 - rssi_factor - latency_factor))
        return mos

    def __repr__(self) -> str:
        return (
            f'AudioStreamer(mode={self.mode.value}, '
            f'codec={self.preferred_codec.value}, '
            f'streaming={self.is_streaming})'
        )
