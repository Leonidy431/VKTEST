"""
Парсер 24-значного штрих-кода муфты. См. protocol/barcode_format.md для
описания формата и оговорки о его происхождении (упрощенная схема проекта,
вдохновленная ISO 12176-4, а не точная его репликация).
"""

from dataclasses import dataclass


class BarcodeFormatError(ValueError):
    pass


@dataclass
class FittingBarcodeData:
    operation_type: int
    diameter_mm: int
    nominal_voltage: float
    resistance_ohm: float
    base_heating_time_s: int
    cooling_time_min: float
    manufacturer_code: str


_FIELD_SLICES = {
    "operation_type": slice(0, 1),
    "diameter_mm": slice(1, 3),
    "voltage_x10": slice(3, 7),
    "resistance_x1000": slice(7, 12),
    "heating_time_s": slice(12, 16),
    "cooling_time_x10": slice(16, 20),
    "manufacturer_code": slice(20, 23),
    "check_digit": slice(23, 24),
}

BARCODE_LENGTH = 24


def _luhn_checksum(digits: str) -> int:
    """Стандартный алгоритм Луна для контрольной цифры."""
    total = 0
    parity = len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10


def validate_checksum(barcode: str) -> bool:
    if len(barcode) != BARCODE_LENGTH or not barcode.isdigit():
        return False
    payload = barcode[:23]
    expected_check = int(barcode[23])
    # Контрольная цифра выбирается так, чтобы luhn_checksum(payload + check) == 0
    computed = _luhn_checksum(payload + "0")
    check_digit = (10 - computed) % 10
    return check_digit == expected_check


def compute_check_digit(payload_23_digits: str) -> int:
    if len(payload_23_digits) != 23 or not payload_23_digits.isdigit():
        raise BarcodeFormatError("Payload must be exactly 23 digits")
    computed = _luhn_checksum(payload_23_digits + "0")
    return (10 - computed) % 10


def parse_barcode(barcode: str) -> FittingBarcodeData:
    if len(barcode) != BARCODE_LENGTH:
        raise BarcodeFormatError(f"Expected {BARCODE_LENGTH} digits, got {len(barcode)}")
    if not barcode.isdigit():
        raise BarcodeFormatError("Barcode must contain only digits")
    if not validate_checksum(barcode):
        raise BarcodeFormatError("Checksum validation failed — possible scan error")

    return FittingBarcodeData(
        operation_type=int(barcode[_FIELD_SLICES["operation_type"]]),
        diameter_mm=int(barcode[_FIELD_SLICES["diameter_mm"]]),
        nominal_voltage=int(barcode[_FIELD_SLICES["voltage_x10"]]) / 10.0,
        resistance_ohm=int(barcode[_FIELD_SLICES["resistance_x1000"]]) / 1000.0,
        base_heating_time_s=int(barcode[_FIELD_SLICES["heating_time_s"]]),
        cooling_time_min=int(barcode[_FIELD_SLICES["cooling_time_x10"]]) / 10.0,
        manufacturer_code=barcode[_FIELD_SLICES["manufacturer_code"]],
    )


def encode_barcode(data: FittingBarcodeData) -> str:
    payload = (
        f"{data.operation_type:01d}"
        f"{data.diameter_mm:02d}"
        f"{int(round(data.nominal_voltage * 10)):04d}"
        f"{int(round(data.resistance_ohm * 1000)):05d}"
        f"{data.base_heating_time_s:04d}"
        f"{int(round(data.cooling_time_min * 10)):04d}"
        f"{data.manufacturer_code:>03s}"
    )
    if len(payload) != 23:
        raise BarcodeFormatError(f"Encoded payload has wrong length: {len(payload)}")
    check_digit = compute_check_digit(payload)
    return payload + str(check_digit)
