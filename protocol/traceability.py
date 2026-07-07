"""
Криптографическая прослеживаемость сварочных протоколов (99 факт #91-92).

Каждая сварка подписывается SHA-256 хэшем от канонического JSON, чтобы
предотвратить подделку протоколов недобросовестными подрядчиками.
"""

import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class WeldSessionRecord:
    timestamp: str
    barcode: str
    welder_id: str
    location: Dict[str, float]
    target_voltage: float
    measured_voltage_avg: float
    measured_resistance: float
    heating_time_s: float
    energy_delivered_j: float
    outcome: str
    ambient_temperature_c: float
    battery_soc_before: Optional[float] = None
    battery_soc_after: Optional[float] = None
    signature: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def canonical_json(record: WeldSessionRecord) -> str:
    """Каноническая (детерминированная) сериализация без поля signature."""
    data = record.to_dict()
    data.pop("signature", None)
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sign_record(record: WeldSessionRecord) -> str:
    payload = canonical_json(record).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def verify_record(record: WeldSessionRecord) -> bool:
    if not record.signature:
        return False
    expected = sign_record(record)
    return expected == record.signature


def finalize_record(record: WeldSessionRecord) -> WeldSessionRecord:
    """Вычисляет и проставляет подпись на записи (мутирует и возвращает record)."""
    record.signature = sign_record(record)
    return record
