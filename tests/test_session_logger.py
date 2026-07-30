import pytest

from protocol.session_logger import SessionLogger
from protocol.traceability import WeldSessionRecord

KEY = b"test-device-secret-key-not-for-production"


def make_record(energy_j: float = 4521.0) -> WeldSessionRecord:
    return WeldSessionRecord(
        timestamp="2026-07-07T14:47:00Z",
        barcode="238003950012800115020004237",
        welder_id="W001",
        location={"latitude": 55.7558, "longitude": 37.6173},
        target_voltage=39.5,
        measured_voltage_avg=39.48,
        measured_resistance=1.13,
        heating_time_s=115,
        energy_delivered_j=energy_j,
        outcome="SUCCESS",
        ambient_temperature_c=8,
    )


@pytest.fixture
def logger(tmp_path):
    return SessionLogger(tmp_path / "sessions.jsonl", key=KEY)


def test_log_writes_and_signs_record(logger):
    record = logger.log(make_record())
    assert record.signature is not None
    assert logger.log_path.exists()


def test_read_all_returns_logged_records(logger):
    logger.log(make_record(energy_j=1000.0))
    logger.log(make_record(energy_j=2000.0))
    records = list(logger.read_all())
    assert len(records) == 2
    assert {r.energy_delivered_j for r in records} == {1000.0, 2000.0}


def test_read_all_returns_nothing_for_missing_file(tmp_path):
    logger = SessionLogger(tmp_path / "does_not_exist.jsonl", key=KEY)
    assert list(logger.read_all()) == []


def test_verify_all_reports_all_valid(logger):
    logger.log(make_record())
    logger.log(make_record(energy_j=999.0))
    report = logger.verify_all()
    assert report == {"total": 2, "valid": 2, "tampered": []}


def test_read_all_skips_blank_lines(logger):
    logger.log(make_record())
    with logger.log_path.open("a", encoding="utf-8") as f:
        f.write("\n")  # пустая строка (например, конец файла) должна пропускаться
    records = list(logger.read_all())
    assert len(records) == 1


def test_verify_all_detects_tampered_line(logger, tmp_path):
    record = logger.log(make_record())
    log_path = logger.log_path
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    import json

    data = json.loads(lines[0])
    data["energy_delivered_j"] = 99999.0  # подделка задним числом, в обход log()
    log_path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")

    report = logger.verify_all()
    assert report["total"] == 1
    assert report["valid"] == 0
    assert report["tampered"] == [record.timestamp]
