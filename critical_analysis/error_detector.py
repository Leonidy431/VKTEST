"""
"Скептичный критик" — обнаружение когнитивных искажений в архитектуре
сварочного контроллера до того, как они станут браком на объекте.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class CriticalError:
    code: str
    message: str
    recommendation: str
    severity: str = "CRITICAL"  # CRITICAL | WARNING


@dataclass
class ArchitectureDescriptor:
    """Плоское описание архитектуры для прогона через проверки критика."""

    has_pid_controller: bool = False
    has_voltage_feedback: bool = False
    has_zero_cross_detection: bool = False
    reads_fitting_barcode: bool = False
    uses_universal_time_table: bool = False
    validates_resistance_against_barcode: bool = False
    has_open_circuit_protection: bool = False
    has_short_circuit_protection: bool = False
    has_low_voltage_lockout: bool = False
    has_ambient_temp_compensation: bool = False


class ErrorDetector:
    """Прогоняет архитектуру через набор проверок когнитивных ошибок."""

    def analyze(self, arch: ArchitectureDescriptor) -> List[CriticalError]:
        errors: List[CriticalError] = []

        if not arch.has_pid_controller and not arch.has_voltage_feedback:
            errors.append(
                CriticalError(
                    code="OPEN_LOOP_CONTROL",
                    message=(
                        "Разомкнутый контур управления: система полагается на "
                        "фиксированный таймер без обратной связи по напряжению."
                    ),
                    recommendation=(
                        "Внедрить ПИД-регулятор с измерением V_RMS в реальном "
                        "времени (см. control/welder_controller.py)."
                    ),
                )
            )

        if arch.uses_universal_time_table:
            errors.append(
                CriticalError(
                    code="UNIVERSAL_TABLE_FALLACY",
                    message=(
                        "Использование универсальной таблицы время/ток для всех "
                        "муфт игнорирует уникальное сопротивление R каждой спирали."
                    ),
                    recommendation=(
                        "Параметры сварки должны браться из штрих-кода/наклейки "
                        "конкретной муфты, а не из усредненной таблицы."
                    ),
                )
            )

        if arch.reads_fitting_barcode and not arch.validates_resistance_against_barcode:
            errors.append(
                CriticalError(
                    code="MISSING_RESISTANCE_CROSS_CHECK",
                    message=(
                        "Штрих-код читается, но измеренное сопротивление спирали "
                        "не сверяется с закодированным значением."
                    ),
                    recommendation=(
                        "Добавить тестовый импульс перед сваркой: R измеренное "
                        "должно совпадать с R из кода в пределах ±10%."
                    ),
                    severity="WARNING",
                )
            )

        if not arch.has_zero_cross_detection:
            errors.append(
                CriticalError(
                    code="NO_ZERO_CROSS_SYNC",
                    message=(
                        "Отсутствует детектор перехода через ноль — управление "
                        "симистором не синхронизировано с фазой сети."
                    ),
                    recommendation="Добавить компаратор Zero-Cross на GPIO прерывание.",
                )
            )

        if not (arch.has_open_circuit_protection and arch.has_short_circuit_protection):
            errors.append(
                CriticalError(
                    code="MISSING_FAULT_PROTECTION",
                    message=(
                        "Не реализованы защиты от обрыва цепи и короткого "
                        "замыкания во время сварки."
                    ),
                    recommendation="См. 99 факт #86-87: аварийное отключение при I=0 или I>110A.",
                )
            )

        if not arch.has_low_voltage_lockout:
            errors.append(
                CriticalError(
                    code="MISSING_LOW_VOLTAGE_LOCKOUT",
                    message="Нет блокировки старта при низком входном напряжении.",
                    recommendation="Блокировать старт при U_in < 185В (99 факт #89).",
                    severity="WARNING",
                )
            )

        if not arch.has_ambient_temp_compensation:
            errors.append(
                CriticalError(
                    code="MISSING_AMBIENT_COMPENSATION",
                    message=(
                        "Отсутствует компенсация времени сварки на температуру "
                        "окружающей среды — при отрицательных температурах "
                        "возможен недогрев."
                    ),
                    recommendation="См. control/temperature_compensator.py.",
                    severity="WARNING",
                )
            )

        return errors
