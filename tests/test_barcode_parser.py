import pytest

from protocol.barcode_parser import (
    FittingBarcodeData,
    encode_barcode,
    parse_barcode,
    validate_checksum,
    BarcodeFormatError,
)


@pytest.fixture
def sample_data():
    return FittingBarcodeData(
        operation_type=2,
        diameter_mm=32,
        nominal_voltage=39.5,
        resistance_ohm=1.13,
        base_heating_time_s=115,
        cooling_time_min=20.0,
        manufacturer_code="042",
    )


def test_encode_produces_24_digit_string(sample_data):
    code = encode_barcode(sample_data)
    assert len(code) == 24
    assert code.isdigit()


def test_encode_then_parse_round_trip(sample_data):
    code = encode_barcode(sample_data)
    parsed = parse_barcode(code)
    assert parsed.operation_type == sample_data.operation_type
    assert parsed.diameter_mm == sample_data.diameter_mm
    assert parsed.nominal_voltage == pytest.approx(sample_data.nominal_voltage)
    assert parsed.resistance_ohm == pytest.approx(sample_data.resistance_ohm)
    assert parsed.base_heating_time_s == sample_data.base_heating_time_s
    assert parsed.cooling_time_min == pytest.approx(sample_data.cooling_time_min)
    assert parsed.manufacturer_code == sample_data.manufacturer_code


def test_validate_checksum_accepts_valid_code(sample_data):
    code = encode_barcode(sample_data)
    assert validate_checksum(code) is True


def test_validate_checksum_rejects_corrupted_code(sample_data):
    code = encode_barcode(sample_data)
    corrupted = code[:-1] + str((int(code[-1]) + 1) % 10)
    assert validate_checksum(corrupted) is False


def test_parse_rejects_wrong_length():
    with pytest.raises(BarcodeFormatError):
        parse_barcode("12345")


def test_parse_rejects_non_digit():
    with pytest.raises(BarcodeFormatError):
        parse_barcode("2" * 23 + "X")


def test_parse_rejects_bad_checksum(sample_data):
    code = encode_barcode(sample_data)
    corrupted = code[:-1] + str((int(code[-1]) + 1) % 10)
    with pytest.raises(BarcodeFormatError):
        parse_barcode(corrupted)
