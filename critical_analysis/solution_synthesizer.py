"""
Синтез корректного решения на основе выявленных критиком ошибок и
результатов физической/нормативной валидации.
"""

from dataclasses import dataclass, field
from typing import List

from .error_detector import CriticalError, ArchitectureDescriptor, ErrorDetector
from .physics_validator import PhysicsValidator, ValidationResult
from .standards_checker import ComplianceIssue, StandardsChecker, PreparationChecklist


@dataclass
class SynthesisReport:
    is_ready_for_production: bool
    critical_errors: List[CriticalError] = field(default_factory=list)
    physics_issues: List[str] = field(default_factory=list)
    compliance_issues: List[ComplianceIssue] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


class SolutionSynthesizer:
    """
    Объединяет все три модуля критического анализа в единый отчет о
    готовности архитектуры/процесса к промышленной эксплуатации.
    """

    def __init__(self) -> None:
        self.error_detector = ErrorDetector()
        self.physics_validator = PhysicsValidator()
        self.standards_checker = StandardsChecker()

    def synthesize(
        self,
        architecture: ArchitectureDescriptor,
        preparation: PreparationChecklist,
        has_manufacturer_barcode: bool = True,
        has_gost_marking: bool = True,
    ) -> SynthesisReport:
        critical_errors = self.error_detector.analyze(architecture)

        compliance_issues = self.standards_checker.check_preparation(preparation)
        compliance_issues += self.standards_checker.check_fitting_marking(
            has_manufacturer_barcode, has_gost_marking
        )

        recommendations = [err.recommendation for err in critical_errors]
        recommendations += [
            f"[{issue.standard}] {issue.requirement}: {issue.detail}"
            for issue in compliance_issues
            if issue.status == "FAIL"
        ]

        has_critical = any(e.severity == "CRITICAL" for e in critical_errors)
        is_compliant = self.standards_checker.is_fully_compliant(compliance_issues)

        return SynthesisReport(
            is_ready_for_production=not has_critical and is_compliant,
            critical_errors=critical_errors,
            compliance_issues=compliance_issues,
            recommendations=recommendations,
        )
