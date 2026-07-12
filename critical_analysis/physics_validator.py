"""
Проверка предложенных параметров сварки на соответствие закону Джоуля-Ленца
и допустимым температурным диапазонам для полиэтилена.
"""

from dataclasses import dataclass


@dataclass
class ValidationResult:
    valid: bool
    reason: str = ""


class PhysicsValidator:
    MELT_TEMP_MIN_C = 210.0
    MELT_TEMP_MAX_C = 230.0

    def validate_energy_balance(
        self, voltage: float, resistance: float, time_s: float, expected_energy_j: float, tolerance: float = 0.05
    ) -> ValidationResult:
        """Проверяет, что Q = (U^2/R)*t совпадает с ожидаемой энергией в пределах tolerance."""
        if resistance <= 0:
            return ValidationResult(False, "Сопротивление должно быть положительным")

        actual_energy = (voltage ** 2 / resistance) * time_s
        delta = abs(actual_energy - expected_energy_j) / expected_energy_j if expected_energy_j else 1.0

        if delta > tolerance:
            return ValidationResult(
                False,
                f"Расчетная энергия {actual_energy:.0f}Дж отклоняется от ожидаемой "
                f"{expected_energy_j:.0f}Дж на {delta:.1%} (закон Джоуля-Ленца нарушен)",
            )
        return ValidationResult(True)

    def validate_resistance_match(
        self, measured_resistance: float, barcode_resistance: float, tolerance: float = 0.10
    ) -> ValidationResult:
        """99 факт #36: если разница R измеренного и R из штрих-кода > 10% — ошибка."""
        if barcode_resistance <= 0:
            return ValidationResult(False, "Некорректное сопротивление из штрих-кода")

        delta = abs(measured_resistance - barcode_resistance) / barcode_resistance
        if delta > tolerance:
            return ValidationResult(
                False,
                f"Измеренное сопротивление {measured_resistance:.3f}Ом отличается "
                f"от заявленного {barcode_resistance:.3f}Ом на {delta:.1%} (>10% — brak)",
            )
        return ValidationResult(True)

    def validate_universal_table_usage(self, uses_universal_table: bool) -> ValidationResult:
        """Отвергает 'усредненные таблицы времени/тока из интернета'."""
        if uses_universal_table:
            return ValidationResult(
                False,
                "Универсальная таблица игнорирует уникальное R каждой муфты — "
                "риск непровара или термической деструкции полимера",
            )
        return ValidationResult(True)

    def validate_input_voltage(self, input_voltage: float, min_voltage: float = 185.0) -> ValidationResult:
        """99 факт #89: блокировка старта при низком входном напряжении."""
        if input_voltage < min_voltage:
            return ValidationResult(
                False, f"Входное напряжение {input_voltage:.0f}В ниже допустимого {min_voltage:.0f}В"
            )
        return ValidationResult(True)

    def validate_mains_frequency(
        self, freq_hz: float, min_freq: float = 45.0, max_freq: float = 65.0
    ) -> ValidationResult:
        """99 факт #90: блокировка при частоте сети вне 45-65 Гц (ненадежный генератор)."""
        if not (min_freq <= freq_hz <= max_freq):
            return ValidationResult(
                False, f"Частота сети {freq_hz:.1f}Гц вне диапазона [{min_freq}, {max_freq}]Гц"
            )
        return ValidationResult(True)
