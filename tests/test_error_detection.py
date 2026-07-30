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


def test_physics_validator_accepts_non_universal_table():
    validator = PhysicsValidator()
    result = validator.validate_universal_table_usage(uses_universal_table=False)
    assert result.valid is True


def test_physics_validator_rejects_zero_resistance_energy_balance():
    validator = PhysicsValidator()
    result = validator.validate_energy_balance(
        voltage=39.5, resistance=0.0, time_s=115, expected_energy_j=1000.0
    )
    assert result.valid is False


def test_physics_validator_accepts_resistance_within_tolerance():
    validator = PhysicsValidator()
    result = validator.validate_resistance_match(measured_resistance=1.15, barcode_resistance=1.13)
    assert result.valid is True


def test_physics_validator_rejects_zero_barcode_resistance():
    validator = PhysicsValidator()
    result = validator.validate_resistance_match(measured_resistance=1.13, barcode_resistance=0.0)
    assert result.valid is False


def test_physics_validator_rejects_low_input_voltage():
    validator = PhysicsValidator()
    result = validator.validate_input_voltage(input_voltage=150.0)
    assert result.valid is False


def test_physics_validator_accepts_nominal_input_voltage():
    validator = PhysicsValidator()
    result = validator.validate_input_voltage(input_voltage=220.0)
    assert result.valid is True


def test_physics_validator_rejects_frequency_out_of_range():
    validator = PhysicsValidator()
    result = validator.validate_mains_frequency(freq_hz=70.0)
    assert result.valid is False


def test_physics_validator_accepts_nominal_frequency():
    validator = PhysicsValidator()
    result = validator.validate_mains_frequency(freq_hz=50.0)
    assert result.valid is True


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


def test_solution_synthesizer_flags_warnings_only_architecture_as_not_ready():
    """
    Регрессия для найденной аудитом ложноотрицательной реакции: архитектура
    без сверки сопротивления с штрих-кодом (WARNING, не CRITICAL) ранее все
    равно получала is_ready_for_production=True.
    """
    synthesizer = SolutionSynthesizer()
    arch = ArchitectureDescriptor(
        has_pid_controller=True,
        has_voltage_feedback=True,
        has_zero_cross_detection=True,
        reads_fitting_barcode=True,
        validates_resistance_against_barcode=False,  # только WARNING
        has_open_circuit_protection=True,
        has_short_circuit_protection=True,
        has_low_voltage_lockout=True,
        has_ambient_temp_compensation=True,
    )
    prep = PreparationChecklist(
        scraped_oxide_layer=True, fixed_in_positioner=True, degreased_with_isopropyl=True
    )
    report = synthesizer.synthesize(arch, prep, has_manufacturer_barcode=True, has_gost_marking=True)
    assert report.has_warnings is True
    assert report.is_ready_for_production is False


def test_standards_checker_barcode_requirement_not_mislabeled_as_real_iso():
    """
    Регрессия: check_fitting_marking ранее маркировал требование как
    "ISO 12176-4", выдавая PASS за соответствие реальному стандарту, хотя
    protocol/barcode_format.md прямо говорит, что формат — упрощенная схема
    проекта, а не точная репликация ISO 12176-4.
    """
    checker = StandardsChecker()
    issues = checker.check_fitting_marking(has_manufacturer_barcode=True, has_gost_marking=True)
    barcode_issue = next(i for i in issues if "штрих-код" in i.requirement.lower())
    assert barcode_issue.standard != "ISO 12176-4"


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
