"""Логирование сессий сварки в JSONL файл (аппенд-онли, для SD карты)."""

import json
from pathlib import Path
from typing import Iterator

from .traceability import WeldSessionRecord, finalize_record, verify_record


class SessionLogger:
    """
    key — секретный ключ подписи устройства (HMAC-SHA256), передаваемый из
    защищенного хранилища вызывающей стороны (см. protocol/traceability.py).
    Один и тот же ключ должен использоваться при логировании и при
    последующей верификации записей.
    """

    def __init__(self, log_path: Path, key: bytes) -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.key = key

    def log(self, record: WeldSessionRecord) -> WeldSessionRecord:
        finalize_record(record, self.key)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return record

    def read_all(self) -> Iterator[WeldSessionRecord]:
        if not self.log_path.exists():
            return
        with self.log_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                yield WeldSessionRecord(**data)

    def verify_all(self) -> dict:
        total = 0
        valid = 0
        tampered = []
        for record in self.read_all():
            total += 1
            if verify_record(record, self.key):
                valid += 1
            else:
                tampered.append(record.timestamp)
        return {"total": total, "valid": valid, "tampered": tampered}
