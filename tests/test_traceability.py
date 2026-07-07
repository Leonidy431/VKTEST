import pytest

from protocol.traceability import WeldSessionRecord, sign_record, verify_record, finalize_record


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
    finalize_record(record)
    assert record.signature is not None
    assert len(record.signature) == 64  # SHA-256 hex digest length


def test_verify_record_accepts_valid_signature(record):
    finalize_record(record)
    assert verify_record(record) is True


def test_verify_record_rejects_tampered_data(record):
    finalize_record(record)
    record.energy_delivered_j = 9999.0  # подделка протокола
    assert verify_record(record) is False


def test_verify_record_rejects_missing_signature(record):
    assert verify_record(record) is False


def test_sign_record_deterministic(record):
    sig1 = sign_record(record)
    sig2 = sign_record(record)
    assert sig1 == sig2
