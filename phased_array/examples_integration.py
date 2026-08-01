"""
Примеры интеграции ФАР модуля с основным контроллером робота.

Демонстрирует:
- Инициализацию RF системы
- Адаптивное управление мощностью
- Поиск оптимального луча
- Логирование метрик
"""

import logging
from datetime import datetime

from phased_array import (
    RFModule, BeamForming, PowerManager, DataLogger, Config
)
from phased_array.data_logger import LogEntry
from phased_array.rf_module import RFState


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)


def example_basic_rf_initialization():
    """
    Пример 1: Базовая инициализация RF модуля.

    Это первое, что нужно сделать при старте робота.
    """
    print('\n=== Example 1: RF Module Initialization ===\n')

    # Создать RF модуль (Qorvo или Wi-Fi 7)
    rf = RFModule(chip='Qorvo_QPM5680', frequency_hz=5.8e9)

    # Инициализировать (SPI handshake, калибровка)
    if not rf.initialize():
        print('ERROR: RF Module initialization failed!')
        return

    print(f'✓ RF Module initialized: {rf.get_chip_info()}')

    # Включить режим приема
    rf.enable_rx()
    print(f'✓ RX mode enabled, state={rf.get_state()}')

    # Прочитать силу сигнала
    rssi = rf.get_rssi()
    print(f'✓ RSSI: {rssi} dBm')


def example_adaptive_tx_power():
    """
    Пример 2: Адаптивное управление мощностью TX.

    Использует P-регулятор для поддержания целевого RSSI.
    Повышает мощность если сигнал слабый, понижает для энергосбережения.
    """
    print('\n=== Example 2: Adaptive TX Power Management ===\n')

    rf = RFModule()
    rf.initialize()

    pm = PowerManager(rf_module=rf)

    # Симуляция разных значений RSSI
    rssi_values = [-95.0, -85.0, -75.0, -70.0, -65.0]
    target_rssi = -75.0

    for rssi in rssi_values:
        # Вычислить рекомендуемую мощность TX
        recommended_power = pm.optimize_tx_power(
            rssi_dbm=rssi,
            target_rssi_dbm=target_rssi
        )

        # Применить мощность
        if rf.set_tx_power(recommended_power):
            print(
                f'RSSI={rssi:6.1f} dBm → TX power adjusted to '
                f'{recommended_power:5.1f} dBm'
            )


def example_beam_steering():
    """
    Пример 3: Управление формированием луча.

    Направляет луч в разные направления (азимут).
    """
    print('\n=== Example 3: Beam Steering ===\n')

    bf = BeamForming(num_elements=4, element_spacing_lambda=0.5)

    # Направить луч в разные направления
    angles = [0.0, 30.0, 60.0, 90.0, 120.0, 180.0]

    print('Pointing beam to different azimuth angles:')
    for angle in angles:
        beam = bf.point_beam(azimuth_deg=angle, elevation_deg=0.0)
        gain = bf.calculate_gain_at_angle(angle, 0.0)
        print(f'  Azimuth={angle:6.1f}° → Gain={gain:6.2f} dBi, '
              f'Phase weights={[f"{w:.0f}" for w in bf.get_phase_weights()]}')


def example_beam_scanning():
    """
    Пример 4: Сканирование луча для поиска оптимального направления.

    Используется когда сигнал слабый (RSSI < -85 дБм).
    """
    print('\n=== Example 4: Beam Scanning for Optimal Direction ===\n')

    bf = BeamForming(num_elements=4)
    pm = PowerManager()
    rf = RFModule()
    rf.initialize()

    # Текущий RSSI слабый
    rssi = -90.0
    print(f'Current RSSI: {rssi} dBm (weak)')

    # Сканировать луч по азимуту
    print('Scanning beam pattern:')
    patterns = bf.scan_beam_pattern(step_deg=30.0)

    # Найти направление с максимальным усилением
    best_pattern = max(patterns, key=lambda p: p.gain_dbi)
    print(f'\n✓ Best direction found: Azimuth={best_pattern.azimuth_deg:.1f}°, '
          f'Gain={best_pattern.gain_dbi:.2f} dBi')

    # Применить оптимальный луч
    bf.point_beam(best_pattern.azimuth_deg, best_pattern.elevation_deg)
    print(f'✓ Beam pointed to optimal direction')


def example_thermal_monitoring():
    """
    Пример 5: Мониторинг теплового режима и дросселирование.

    Система контролирует температуру PA и автоматически снижает
    мощность TX если температура превышает пределы.
    """
    print('\n=== Example 5: Thermal Monitoring & Throttling ===\n')

    rf = RFModule()
    rf.initialize()
    pm = PowerManager(rf_module=rf)

    # Симуляция повышения температуры при длительной TX
    print('Simulating long TX session:')

    ambient_temp = 25.0
    time_elapsed_s = [0, 30, 60, 120, 180]  # Секунды TX

    for t in time_elapsed_s:
        # Оценка температуры PA (экспоненциальный нагрев)
        pa_temp = pm.estimate_pa_temperature(
            tx_power_dbm=20.0,
            ambient_temp_c=ambient_temp,
            time_elapsed_s=t
        )

        # Обновить тепловое состояние
        thermal_state = pm.update_thermal_state(pa_temp)

        print(f'Time={t:3d}s: PA Temp={pa_temp:5.1f}°C, '
              f'Thermal State={thermal_state.value:7s}')

        # Если горячо, снизить мощность
        if thermal_state.value == 'hot':
            rf.set_tx_power(rf.tx_power_dbm - 4)
            print(f'  → TX Power throttled to {rf.tx_power_dbm} dBm')


def example_metrics_logging():
    """
    Пример 6: Логирование метрик для анализа.

    Записывает RSSI, мощность, температуру в JSON лог.
    """
    print('\n=== Example 6: Metrics Logging ===\n')

    logger = DataLogger()
    rf = RFModule()
    rf.initialize()

    # Логировать события инициализации
    logger.log_event('INIT', 'RF Module initialized successfully', rssi_dbm=-90.0)

    # Симуляция логирования метрик
    print('Logging metrics (simulated):')
    for i in range(5):
        rssi = -85.0 + (i - 2) * 3  # Вариация RSSI
        entry = LogEntry(
            timestamp_s=datetime.now().timestamp() + i,
            rssi_dbm=rssi,
            phase_error_deg=0.0,
            tx_power_dbm=20.0,
            frequency_hz=Config.FREQUENCY_CENTER_HZ,
            pa_temperature_c=35.0 + i * 2,
            thermal_state='normal',
        )
        logger.log_metric(entry)
        print(f'  Record {i+1}: RSSI={rssi:.1f} dBm, Temp={entry.pa_temperature_c:.1f}°C')

    # Получить статистику
    stats = logger.get_statistics()
    print(f'\n✓ Statistics: {len(logger.memory_buffer)} records logged')
    print(f'  RSSI mean={stats.get("rssi_mean_dbm", 0):.1f} dBm')


def example_full_robot_loop():
    """
    Пример 7: Полный цикл управления роботом с ФАР.

    Интеграция всех компонентов в единый mainloop.
    """
    print('\n=== Example 7: Full Robot Control Loop with ФАР ===\n')

    # Инициализация
    rf = RFModule()
    rf.initialize()

    bf = BeamForming(num_elements=4)
    pm = PowerManager(rf_module=rf)
    logger = DataLogger()

    rf.enable_rx()

    # Симуляция цикла управления (5 итераций)
    print('Robot control loop (5 iterations):')
    print('-' * 70)

    for iteration in range(5):
        # Получить текущий RSSI
        rssi = rf.get_rssi()

        # Если сигнал слабый, сканировать луч
        if rssi < -80:
            print(f'[{iteration}] RSSI weak ({rssi:.1f} dBm), scanning beam...')
            patterns = bf.scan_beam_pattern(step_deg=45.0)
            best = max(patterns, key=lambda p: p.gain_dbi)
            bf.point_beam(best.azimuth_deg, best.elevation_deg)
        else:
            print(f'[{iteration}] RSSI good ({rssi:.1f} dBm), maintaining beam')

        # Адаптивное управление мощностью
        new_power = pm.optimize_tx_power(rssi_dbm=rssi)
        rf.set_tx_power(new_power)

        # Логировать метрику
        entry = LogEntry(
            timestamp_s=datetime.now().timestamp(),
            rssi_dbm=rssi,
            phase_error_deg=0.0,
            tx_power_dbm=rf.tx_power_dbm,
            frequency_hz=Config.FREQUENCY_CENTER_HZ,
            pa_temperature_c=35.0,
            thermal_state='normal',
        )
        logger.log_metric(entry)

        print(f'          TX Power={rf.tx_power_dbm:.0f} dBm, '
              f'Beam Az={bf.current_beam.azimuth_deg:.1f}°\n')

    print(f'✓ Logged {len(logger.memory_buffer)} metrics')


if __name__ == '__main__':
    # Запустить все примеры
    example_basic_rf_initialization()
    example_adaptive_tx_power()
    example_beam_steering()
    example_beam_scanning()
    example_thermal_monitoring()
    example_metrics_logging()
    example_full_robot_loop()

    print('\n=== All Examples Completed ===\n')
