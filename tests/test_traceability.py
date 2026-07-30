import pytest

from protocol.traceability import WeldSessionRecord, sign_record, verify_record, finalize_record

KEY = b"test-device-secret-key-not-for-production"
OTHER_KEY = b"a-different-secret-key"


@pytest.fixture
def record():
    return WeldSessionRecord(
        timestamp="2026-07-07T14:47:00Z",
        barcode="238003950012800115020004237",
        welder_id="W001",
        location={"latitude": 55.7558, "longitude": 37.6173},
        target_voltage=39.5,
        measured_voltage_avg=39.48,
        measured_resistance=1.13,
        heating_time_s=115,
        energy_delivered_j=4521.0,
        outcome="SUCCESS",
        ambient_temperature_c=8,
    )


def test_finalize_record_sets_signature(record):
    finalize_record(record, KEY)
    assert record.signature is not None
    assert len(record.signature) == 64  # HMAC-SHA256 hex digest length


def test_verify_record_accepts_valid_signature(record):
    finalize_record(record, KEY)
    assert verify_record(record, KEY) is True


def test_verify_record_rejects_tampered_data(record):
    finalize_record(record, KEY)
    record.energy_delivered_j = 9999.0  # подделка протокола
    assert verify_record(record, KEY) is False


def test_verify_record_rejects_tampered_data_even_if_resigned(record):
    # Атака: подрядчик меняет поле и пересчитывает подпись тем же публичным
    # алгоритмом. Без секретного ключа новая "подпись" не совпадет с
    # ожидаемой при верификации доверенной стороной, знающей настоящий ключ.
    finalize_record(record, KEY)
    record.energy_delivered_j = 9999.0
    record.signature = sign_record(record, OTHER_KEY)  # злоумышленник не знает KEY
    assert verify_record(record, KEY) is False


def test_verify_record_rejects_missing_signature(record):
    assert verify_record(record, KEY) is False


def test_sign_record_deterministic(record):
    sig1 = sign_record(record, KEY)
    sig2 = sign_record(record, KEY)
    assert sig1 == sig2


def test_sign_record_differs_by_key(record):
    sig1 = sign_record(record, KEY)
    sig2 = sign_record(record, OTHER_KEY)
    assert sig1 != sig2


def test_sign_record_rejects_empty_key(record):
    with pytest.raises(ValueError):
        sign_record(record, b"")
