import pytest

from simulation.pid_simulator import PIDVoltageRegulator


def test_pid_converges_to_target_under_stable_supply():
    """
    Симулируем замкнутый контур: ПИД корректирует угол симистора, который
    определяет фактическое RMS-напряжение через phase-control формулу.
    Проверяем, что после нескольких итераций напряжение сходится к target.

    peak_voltage=56V дает максимум RMS=39.6В (56/sqrt(2)) — жесткий предел,
    близкий к target=39.5В, как в реальной конструкции (вторичная обмотка
    выпрямлена до ~56В, регулировка вниз фазовым управлением).
    """
    pid = PIDVoltageRegulator()  # kp=1.5, ki=2.5, kd=0.02 — подобранные значения
    peak_voltage = 56.0  # напряжение после выпрямителя (холостой ход)
    measured_voltage = 30.0  # старт с сильной просадки
    dt = 0.02  # 50 итераций/сек (частота сети)

    for _ in range(500):
        angle = pid.update(measured_voltage, dt)
        measured_voltage = PIDVoltageRegulator.angle_to_rms_voltage(angle, peak_voltage)

    assert measured_voltage == pytest.approx(39.5, abs=1.0)


def test_pid_compensates_supply_sag_mid_weld():
    """
    peak_voltage=65V дает ~16% запас над target (max RMS=45.96В) — реалистичный
    запас конструкции для компенсации просадок батареи/генератора.
    """
    pid = PIDVoltageRegulator()
    peak_voltage = 65.0
    measured_voltage = 39.5
    dt = 0.02

    # Стабилизация
    for _ in range(300):
        angle = pid.update(measured_voltage, dt)
        measured_voltage = PIDVoltageRegulator.angle_to_rms_voltage(angle, peak_voltage)
    assert measured_voltage == pytest.approx(39.5, abs=1.0)

    # Просадка источника на 10% (запас все еще позволяет достичь target)
    peak_voltage *= 0.90
    for _ in range(300):
        angle = pid.update(measured_voltage, dt)
        measured_voltage = PIDVoltageRegulator.angle_to_rms_voltage(angle, peak_voltage)

    assert measured_voltage == pytest.approx(39.5, abs=1.0)


def test_angle_to_delay_us_zero_angle_is_zero_delay():
    assert PIDVoltageRegulator.angle_to_delay_us(0.0, mains_freq_hz=50.0) == 0.0


def test_angle_to_delay_us_full_angle_is_half_period():
    delay = PIDVoltageRegulator.angle_to_delay_us(180.0, mains_freq_hz=50.0)
    assert delay == pytest.approx(10000.0)  # 10ms half-period at 50Hz


def test_angle_to_rms_voltage_zero_angle_is_full_rms():
    # При угле 0 (полностью открыт) V_rms ~= V_peak / sqrt(2)
    v_rms = PIDVoltageRegulator.angle_to_rms_voltage(0.0, peak_voltage=100.0)
    assert v_rms == pytest.approx(100.0 / (2 ** 0.5), rel=1e-3)


def test_angle_to_rms_voltage_full_angle_is_zero():
    v_rms = PIDVoltageRegulator.angle_to_rms_voltage(180.0, peak_voltage=100.0)
    assert v_rms == pytest.approx(0.0, abs=1e-6)


def test_integral_does_not_wind_up_beyond_saturation():
    """
    Регрессионный тест: при длительной насыщенной ошибке (напряжение
    физически недостижимо, т.к. peak/sqrt(2) < target) интеграл не должен
    накручиваться далеко за пределы, нужные для угла=0 — иначе после
    восстановления запаса по напряжению система долго не отпускает максимум.
    """
    pid = PIDVoltageRegulator()
    peak_voltage = 40.0  # max RMS ~28.3V, недостижимо для target=39.5V
    measured_voltage = 20.0
    dt = 0.02

    for _ in range(500):
        angle = pid.update(measured_voltage, dt)
        measured_voltage = PIDVoltageRegulator.angle_to_rms_voltage(angle, peak_voltage)

    # Система должна выйти на физический максимум, а не превысить его
    assert measured_voltage == pytest.approx(peak_voltage / (2 ** 0.5), abs=0.1)

    # Теперь возвращаем запас по напряжению — благодаря conditional anti-windup
    # интеграл не залипал на все 500 итераций насыщения (см. проверку ниже),
    # поэтому система приходит к target за разумное число итераций, а не
    # держится на максимуме сотнями циклов из-за раскрученного интеграла.
    peak_voltage = 65.0
    for _ in range(400):
        angle = pid.update(measured_voltage, dt)
        measured_voltage = PIDVoltageRegulator.angle_to_rms_voltage(angle, peak_voltage)

    assert measured_voltage == pytest.approx(39.5, abs=1.0)


def test_reset_clears_integral_state():
    pid = PIDVoltageRegulator()
    for _ in range(50):
        pid.update(30.0, 0.02)
    assert pid._integral != 0.0
    pid.reset()
    assert pid._integral == 0.0
    assert pid._initialized is False
