"""
Валидация процесса сварки на соответствие регламентирующим стандартам:
ГОСТ Р 52779-2007, ГОСТ 32415-2013, СП 42-103-2003.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class ComplianceIssue:
    standard: str
    requirement: str
    status: str  # "PASS" | "FAIL"
    detail: str = ""


@dataclass
class PreparationChecklist:
    """СП 42-103-2003: подготовка труб перед сваркой."""

    scraped_oxide_layer: bool = False  # снятие оксидного слоя 0.1-0.2мм
    fixed_in_positioner: bool = False  # жесткая фиксация для снятия напряжения
    degreased_with_isopropyl: bool = False  # обезжиривание изопропиловым спиртом


class StandardsChecker:
    def check_preparation(self, checklist: PreparationChecklist) -> List[ComplianceIssue]:
        issues = []
        checks = [
            ("scraped_oxide_layer", "Механическая очистка скребком (0.1-0.2мм)"),
            ("fixed_in_positioner", "Фиксация труб в позиционере"),
            ("degreased_with_isopropyl", "Обезжиривание изопропиловым спиртом"),
        ]
        for field_name, requirement in checks:
            passed = getattr(checklist, field_name)
            issues.append(
                ComplianceIssue(
                    standard="СП 42-103-2003",
                    requirement=requirement,
                    status="PASS" if passed else "FAIL",
                    detail="" if passed else "Обязательный этап подготовки не выполнен",
                )
            )
        return issues

    def check_fitting_marking(self, has_manufacturer_barcode: bool, has_gost_marking: bool) -> List[ComplianceIssue]:
        issues = []
        issues.append(
            ComplianceIssue(
                standard="ГОСТ Р 52779-2007 / ГОСТ 32415-2013",
                requirement="Маркировка соединительной детали присутствует",
                status="PASS" if has_gost_marking else "FAIL",
            )
        )
        issues.append(
            ComplianceIssue(
                # Формат проекта — упрощенная, самостоятельно определенная
                # 24-значная схема (protocol/barcode_format.md), а НЕ
                # реализация реального ISO 12176-4. Маркировка стандарта как
                # "ISO 12176-4" здесь ранее выдавала PASS за соответствие
                # стандарту, которому код фактически не следует — тот же
                # класс ложноположительного результата, который этот модуль
                # должен предотвращать, а не совершать сам.
                standard="Внутренняя схема проекта (ISO 12176-4-inspired, не точная репликация)",
                requirement="24-значный штрих-код читаем",
                status="PASS" if has_manufacturer_barcode else "FAIL",
                detail="" if has_manufacturer_barcode else "Параметры должны браться вручную с наклейки муфты",
            )
        )
        return issues

    def is_fully_compliant(self, issues: List[ComplianceIssue]) -> bool:
        return all(issue.status == "PASS" for issue in issues)
