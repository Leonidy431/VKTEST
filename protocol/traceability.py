"""
Криптографическая прослеживаемость сварочных протоколов (99 факт #91-92).

Каждая сварка подписывается HMAC-SHA256 от канонического JSON с секретным
ключом устройства, чтобы предотвратить подделку протоколов недобросовестными
подрядчиками.

Важно: подпись без секретного ключа (простой sha256(payload)) НЕ является
защитой от подделки — злоумышленник, имеющий доступ на изменение записи,
может вычислить тот же детерминированный хэш и переподписать
сфальсифицированные данные. HMAC с ключом, известным только доверенной
стороне (устройству/серверу верификации, но не оператору/подрядчику),
делает переподпись невозможной без знания ключа. Ключ должен храниться вне
кода — в защищенном хранилище устройства (например, eFuse ESP32-S3) или
секрет-менеджере сервера верификации, а не в репозитории.
"""

import hashlib
import hmac
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


def sign_record(record: WeldSessionRecord, key: bytes) -> str:
    """
    HMAC-SHA256 подпись канонического JSON записи под секретным ключом
    устройства. key должен передаваться из защищенного хранилища вызывающей
    стороны — никогда не хардкодиться и не логироваться.
    """
    if not key:
        raise ValueError("Signing key must not be empty — a keyless signature is forgeable")
    payload = canonical_json(record).encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def verify_record(record: WeldSessionRecord, key: bytes) -> bool:
    if not record.signature:
        return False
    expected = sign_record(record, key)
    return hmac.compare_digest(expected, record.signature)


def finalize_record(record: WeldSessionRecord, key: bytes) -> WeldSessionRecord:
    """Вычисляет и проставляет подпись на записи (мутирует и возвращает record)."""
    record.signature = sign_record(record, key)
    return record
