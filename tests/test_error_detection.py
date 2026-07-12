from critical_analysis.error_detector import ArchitectureDescriptor, ErrorDetector
from critical_analysis.physics_validator import PhysicsValidator
from critical_analysis.standards_checker import StandardsChecker, PreparationChecklist
from critical_analysis.solution_synthesizer import SolutionSynthesizer


def test_open_loop_architecture_flagged():
    arch = ArchitectureDescriptor(uses_universal_time_table=True)
    errors = ErrorDetector().analyze(arch)
    codes = {e.code for e in errors}
    assert "OPEN_LOOP_CONTROL" in codes
    assert "UNIVERSAL_TABLE_FALLACY" in codes


def test_closed_loop_architecture_not_flagged_for_open_loop():
    arch = ArchitectureDescriptor(
        has_pid_controller=True,
        has_voltage_feedback=True,
        has_zero_cross_detection=True,
        reads_fitting_barcode=True,
        validates_resistance_against_barcode=True,
        has_open_circuit_protection=True,
        has_short_circuit_protection=True,
        has_low_voltage_lockout=True,
        has_ambient_temp_compensation=True,
    )
    errors = ErrorDetector().analyze(arch)
    assert errors == []


def test_physics_validator_rejects_energy_mismatch():
    validator = PhysicsValidator()
    result = validator.validate_energy_balance(
        voltage=39.5, resistance=1.13, time_s=115, expected_energy_j=1.0
    )
    assert result.valid is False


def test_physics_validator_accepts_correct_energy():
    validator = PhysicsValidator()
    expected = (39.5 ** 2 / 1.13) * 115
    result = validator.validate_energy_balance(
        voltage=39.5, resistance=1.13, time_s=115, expected_energy_j=expected
    )
    assert result.valid is True


def test_physics_validator_rejects_resistance_mismatch():
    validator = PhysicsValidator()
    result = validator.validate_resistance_match(measured_resistance=1.30, barcode_resistance=1.13)
    assert result.valid is False


def test_physics_validator_rejects_universal_table():
    validator = PhysicsValidator()
    result = validator.validate_universal_table_usage(uses_universal_table=True)
    assert result.valid is False


def test_standards_checker_flags_incomplete_preparation():
    checker = StandardsChecker()
    checklist = PreparationChecklist(scraped_oxide_layer=True)
    issues = checker.check_preparation(checklist)
    assert any(issue.status == "FAIL" for issue in issues)
    assert not checker.is_fully_compliant(issues)


def test_standards_checker_passes_full_preparation():
    checker = StandardsChecker()
    checklist = PreparationChecklist(
        scraped_oxide_layer=True, fixed_in_positioner=True, degreased_with_isopropyl=True
    )
    issues = checker.check_preparation(checklist)
    assert checker.is_fully_compliant(issues)


def test_solution_synthesizer_flags_not_ready():
    synthesizer = SolutionSynthesizer()
    arch = ArchitectureDescriptor(uses_universal_time_table=True)
    prep = PreparationChecklist()
    report = synthesizer.synthesize(arch, prep)
    assert report.is_ready_for_production is False
    assert len(report.recommendations) > 0


def test_solution_synthesizer_confirms_ready_architecture():
    synthesizer = SolutionSynthesizer()
    arch = ArchitectureDescriptor(
        has_pid_controller=True,
        has_voltage_feedback=True,
        has_zero_cross_detection=True,
        reads_fitting_barcode=True,
        validates_resistance_against_barcode=True,
        has_open_circuit_protection=True,
        has_short_circuit_protection=True,
        has_low_voltage_lockout=True,
        has_ambient_temp_compensation=True,
    )
    prep = PreparationChecklist(
        scraped_oxide_layer=True, fixed_in_positioner=True, degreased_with_isopropyl=True
    )
    report = synthesizer.synthesize(arch, prep, has_manufacturer_barcode=True, has_gost_marking=True)
    assert report.is_ready_for_production is True
