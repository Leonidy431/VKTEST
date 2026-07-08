"""
Tests для аудиомодуля голосовой связи.

Проверяет:
- Инициализацию audio streamer
- Выбор кодека по качеству сигнала
- Оценку битрейта
- Расчет метрик качества (MOS, jitter, latency)
- Адаптацию к условиям сети
"""

import pytest
import time

from phased_array.audio_streamer import (
    AudioStreamer, AudioCodec, AudioMode, AudioPacket, AudioQualityMetrics
)
from phased_array.rf_module import RFModule


class TestAudioStreamerInit:
    """Тесты инициализации AudioStreamer."""

    def test_creation_default(self):
        """Создание с параметрами по умолчанию."""
        streamer = AudioStreamer()
        assert streamer.mode == AudioMode.VOIP_STANDARD
        assert streamer.preferred_codec == AudioCodec.OPUS
        assert streamer.is_streaming is False

    def test_creation_with_mode(self):
        """Создание с указанным режимом."""
        streamer = AudioStreamer(mode=AudioMode.LOW_LATENCY)
        assert streamer.mode == AudioMode.LOW_LATENCY

    def test_sample_rate(self):
        """Проверка sample rate (16 kHz для VoIP)."""
        streamer = AudioStreamer()
        assert streamer.sample_rate_hz == 16000

    def test_frame_duration(self):
        """Проверка длительности фрейма (20ms стандарт)."""
        streamer = AudioStreamer()
        assert streamer.frame_duration_ms == 20


class TestAudioCodecSelection:
    """Тесты адаптивного выбора кодека."""

    def test_codec_selection_strong_signal(self):
        """Выбор Opus при сильном сигнале (RSSI > -70)."""
        streamer = AudioStreamer()
        codec = streamer.select_codec_by_signal_quality(rssi_dbm=-65.0)
        assert codec == AudioCodec.OPUS

    def test_codec_selection_medium_signal(self):
        """Выбор GSM AMR при среднем сигнале (-70 to -80)."""
        streamer = AudioStreamer()
        codec = streamer.select_codec_by_signal_quality(rssi_dbm=-75.0)
        assert codec == AudioCodec.GSM_AMR

    def test_codec_selection_weak_signal(self):
        """Выбор GSM AMR при слабом сигнале (RSSI < -80)."""
        streamer = AudioStreamer()
        codec = streamer.select_codec_by_signal_quality(rssi_dbm=-85.0)
        assert codec == AudioCodec.GSM_AMR

    def test_codec_selection_boundary_minus_70(self):
        """Граница -70 dBm (>=)."""
        streamer = AudioStreamer()
        # Точно на границе: RSSI >= -70 → Opus
        codec_at_boundary = streamer.select_codec_by_signal_quality(rssi_dbm=-70.0)
        # Немного ниже: RSSI < -70 → GSM AMR
        codec_below = streamer.select_codec_by_signal_quality(rssi_dbm=-70.1)
        # На граница -80: RSSI >= -80 → GSM AMR
        codec_at_minus_80 = streamer.select_codec_by_signal_quality(rssi_dbm=-80.0)

        assert codec_at_boundary == AudioCodec.OPUS
        assert codec_below == AudioCodec.GSM_AMR
        assert codec_at_minus_80 == AudioCodec.GSM_AMR


class TestBitrateEstimation:
    """Тесты оценки битрейта."""

    def test_bitrate_strong_signal(self):
        """Битрейт при сильном сигнале."""
        streamer = AudioStreamer()
        bitrate = streamer.estimate_bitrate_by_rssi(rssi_dbm=-65.0)
        # При -65 дБм должен быть высокий битрейт (Opus может до 128 kbps)
        assert bitrate > 20  # кбит/сек

    def test_bitrate_weak_signal(self):
        """Битрейт при слабом сигнале ниже при слабом сигнале."""
        streamer = AudioStreamer()
        bitrate_strong = streamer.estimate_bitrate_by_rssi(rssi_dbm=-65.0)
        bitrate_weak = streamer.estimate_bitrate_by_rssi(rssi_dbm=-85.0)
        # Битрейт должен быть ниже при слабом сигнале
        assert bitrate_weak < bitrate_strong

    def test_bitrate_minimum(self):
        """Битрейт имеет минимальное значение (для GSM AMR)."""
        streamer = AudioStreamer()
        bitrate = streamer.estimate_bitrate_by_rssi(rssi_dbm=-100.0)
        # GSM AMR минимум 4.75 kbps
        assert bitrate > 0


class TestAudioStreaming:
    """Тесты управления потоком аудио."""

    def test_start_streaming(self):
        """Начать передачу аудио."""
        streamer = AudioStreamer()
        result = streamer.start_streaming()
        assert result is True
        assert streamer.is_streaming is True

    def test_stop_streaming(self):
        """Остановить передачу аудио."""
        streamer = AudioStreamer()
        streamer.start_streaming()
        result = streamer.stop_streaming()
        assert result is True
        assert streamer.is_streaming is False

    def test_stop_streaming_when_not_active(self):
        """Попытка остановить неактивный поток."""
        streamer = AudioStreamer()
        result = streamer.stop_streaming()
        assert result is False

    def test_double_start(self):
        """Попытка запустить уже запущенный поток."""
        streamer = AudioStreamer()
        streamer.start_streaming()
        result = streamer.start_streaming()
        assert result is False  # Уже запущен


class TestAudioPacket:
    """Тесты создания аудиопакетов."""

    def test_packet_creation(self):
        """Создать аудиопакет."""
        streamer = AudioStreamer()
        pcm_data = b'\x00' * 160  # 160 байт = 20ms @ 16kHz 16-бит
        packet = streamer.create_audio_packet(pcm_data, AudioCodec.OPUS)

        assert isinstance(packet, AudioPacket)
        assert packet.sequence_number == 0
        assert packet.codec == AudioCodec.OPUS
        assert packet.frame_duration_ms == 20

    def test_sequence_number_increment(self):
        """Проверка инкрементирования номера последовательности."""
        streamer = AudioStreamer()
        pcm_data = b'\x00' * 160

        packet1 = streamer.create_audio_packet(pcm_data, AudioCodec.OPUS)
        packet2 = streamer.create_audio_packet(pcm_data, AudioCodec.OPUS)

        assert packet1.sequence_number == 0
        assert packet2.sequence_number == 1

    def test_packet_payload_size_opus(self):
        """Проверка сжатия Opus (примерно 4:1)."""
        streamer = AudioStreamer()
        pcm_data = b'\x00' * 160
        packet = streamer.create_audio_packet(pcm_data, AudioCodec.OPUS)
        # Opus должен сжать примерно в 4 раза
        assert len(packet.payload) < len(pcm_data)

    def test_packet_payload_size_gsm_amr(self):
        """Проверка сжатия GSM AMR (примерно 8:1)."""
        streamer = AudioStreamer()
        pcm_data = b'\x00' * 160
        packet = streamer.create_audio_packet(pcm_data, AudioCodec.GSM_AMR)
        # GSM AMR должен сжать примерно в 8 раз
        assert len(packet.payload) <= len(pcm_data) // 4


class TestQualityMetrics:
    """Тесты расчета метрик качества."""

    def test_get_quality_metrics(self):
        """Получить метрики качества."""
        streamer = AudioStreamer()
        metrics = streamer.get_quality_metrics()

        assert isinstance(metrics, AudioQualityMetrics)
        assert 1.0 <= metrics.mos_score <= 5.0
        assert metrics.packet_loss_percent >= 0
        assert metrics.latency_ms >= 0
        assert metrics.jitter_ms >= 0

    def test_mos_score_range(self):
        """MOS score должен быть в диапазоне 1-5."""
        streamer = AudioStreamer()
        for _ in range(10):
            metrics = streamer.get_quality_metrics()
            assert 1.0 <= metrics.mos_score <= 5.0

    def test_metrics_depend_on_rssi_history(self):
        """Добавить RSSI в историю и проверить метрики."""
        streamer = AudioStreamer()
        # Добавить несколько значений RSSI
        for rssi in [-65.0, -70.0, -75.0]:
            streamer.rssi_history.append(rssi)

        metrics = streamer.get_quality_metrics()
        # Средний RSSI = (-65 + -70 + -75) / 3 = -70
        assert -71 < metrics.rssi_dbm < -69


class TestNetworkAdaptation:
    """Тесты адаптации к условиям сети."""

    def test_adapt_to_strong_signal(self):
        """Адаптация к сильному сигналу: выбор кодека при RSSI >= -70."""
        streamer = AudioStreamer()

        # Симуляция: напрямую добавить сильный RSSI в историю
        streamer.rssi_history = [-65.0, -65.0, -65.0]

        # Расчет среднего RSSI: (-65 + -65 + -65) / 3 = -65
        metrics = streamer.get_quality_metrics()
        assert metrics.rssi_dbm <= -65.0  # Среднее RSSI около -65

        # Выбрать кодек для среднего RSSI
        codec = streamer.select_codec_by_signal_quality(metrics.rssi_dbm)
        assert codec == AudioCodec.OPUS

    def test_adapt_to_weak_signal(self):
        """Адаптация к слабому сигналу."""
        rf = RFModule()
        rf.initialize()
        streamer = AudioStreamer(rf_module=rf)

        # Симуляция: добавить слабый RSSI в историю
        for _ in range(5):
            streamer.rssi_history.append(-85.0)

        codec = streamer.adapt_to_network_conditions()
        # При слабом сигнале (RSSI < -80) должен выбрать GSM AMR
        assert codec == AudioCodec.GSM_AMR


class TestAudioRepr:
    """Тест строкового представления."""

    def test_repr(self):
        """Проверка __repr__."""
        streamer = AudioStreamer()
        repr_str = repr(streamer)
        assert 'AudioStreamer' in repr_str
        assert 'voip_standard' in repr_str
        assert 'opus' in repr_str
