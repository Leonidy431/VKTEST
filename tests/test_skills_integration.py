"""
Integration tests for Claude Skills and CLAUDE.md documentation.

Verifies:
1. CLAUDE.md exists and contains all required sections
2. Karpathy guidelines are properly integrated
3. VKTEST autonomy patterns are accessible
4. Skills directory structure is valid
"""

import os
import json
from pathlib import Path


class TestCLAUDEMDStructure:
    """Tests for main CLAUDE.md file."""

    @staticmethod
    def read_claude_md():
        """Read CLAUDE.md from project root."""
        path = Path("/home/user/VKTEST/CLAUDE.md")
        assert path.exists(), "CLAUDE.md not found in project root"
        return path.read_text()

    def test_claude_md_exists(self):
        """CLAUDE.md must exist."""
        path = Path("/home/user/VKTEST/CLAUDE.md")
        assert path.exists(), "CLAUDE.md not found"

    def test_claude_md_contains_project_summary(self):
        """CLAUDE.md must have Project Summary section."""
        content = self.read_claude_md()
        assert "## Project Summary" in content
        assert "VKTEST" in content
        assert "autonomous underwater vehicle" in content

    def test_claude_md_contains_behavioral_guidelines(self):
        """CLAUDE.md must have Karpathy principles integrated."""
        content = self.read_claude_md()
        assert "## Behavioral Guidelines (Karpathy Principles)" in content
        assert "Think Before Coding" in content
        assert "Simplicity First" in content
        assert "Surgical Changes" in content
        assert "Goal-Driven Execution" in content

    def test_claude_md_contains_vktest_context(self):
        """Karpathy principles must have VKTEST-specific guidance."""
        content = self.read_claude_md()
        assert "In VKTEST context:" in content
        # Should appear at least 4 times (once per principle)
        assert content.count("In VKTEST context:") >= 4

    def test_claude_md_contains_quick_commands(self):
        """CLAUDE.md must have Quick Commands section."""
        content = self.read_claude_md()
        assert "## Quick Commands" in content
        assert "pytest" in content
        assert "docker-compose" in content
        assert "black" in content

    def test_claude_md_contains_architecture_overview(self):
        """CLAUDE.md must describe system architecture."""
        content = self.read_claude_md()
        assert "## Architecture Overview" in content
        assert "4-Layer System Design" in content
        assert "Dual-Stack Channel Strategy" in content
        assert "FSM:" in content
        assert "SystemState:" in content

    def test_claude_md_contains_module_map(self):
        """CLAUDE.md must map core modules."""
        content = self.read_claude_md()
        assert "## Module Map" in content
        assert "AutonomousAgent" in content
        assert "PIDDepthController" in content
        assert "Protocol & Serialization" in content

    def test_claude_md_contains_development_guidelines(self):
        """CLAUDE.md must have development standards."""
        content = self.read_claude_md()
        assert "## Development Guidelines" in content
        assert "Code Style" in content
        assert "Testing Strategy" in content
        assert "Branching & Commits" in content

    def test_claude_md_contains_attribution(self):
        """CLAUDE.md must credit Karpathy principles source."""
        content = self.read_claude_md()
        assert "## Inspiration & Attribution" in content
        assert "Andrej Karpathy" in content
        assert "andrej-karpathy-skills" in content


class TestSkillsDirectory:
    """Tests for .claude-skills/ directory structure."""

    @staticmethod
    def get_skills_dir():
        """Get .claude-skills directory path."""
        return Path("/home/user/VKTEST/.claude-skills")

    def test_skills_directory_exists(self):
        """Skills directory must exist."""
        skills_dir = self.get_skills_dir()
        assert skills_dir.exists(), ".claude-skills directory not found"
        assert skills_dir.is_dir(), ".claude-skills must be a directory"

    def test_skills_readme_exists(self):
        """Skills directory must have README."""
        readme = self.get_skills_dir() / "README.md"
        assert readme.exists(), "Skills README.md not found"
        assert readme.read_text().startswith("# Claude Skills for VKTEST")

    def test_karpathy_guidelines_skill_exists(self):
        """Karpathy guidelines skill must be present."""
        skill_path = self.get_skills_dir() / "karpathy-guidelines" / "SKILL.md"
        assert skill_path.exists(), "karpathy-guidelines SKILL.md not found"

    def test_karpathy_skill_has_frontmatter(self):
        """Karpathy skill must have YAML frontmatter."""
        skill_path = self.get_skills_dir() / "karpathy-guidelines" / "SKILL.md"
        content = skill_path.read_text()
        assert content.startswith("---"), "SKILL.md missing YAML frontmatter"
        lines = content.split("\n")
        assert lines[1].startswith("name:"), "SKILL.md missing 'name' field"
        assert "description:" in content, "SKILL.md missing 'description' field"
        assert "license:" in content, "SKILL.md missing 'license' field"

    def test_vktest_autonomy_patterns_skill_exists(self):
        """VKTEST autonomy patterns skill must be present."""
        skill_path = self.get_skills_dir() / "vktest-autonomy-patterns" / "SKILL.md"
        assert skill_path.exists(), "vktest-autonomy-patterns SKILL.md not found"

    def test_vktest_patterns_skill_has_frontmatter(self):
        """VKTEST patterns skill must have YAML frontmatter."""
        skill_path = self.get_skills_dir() / "vktest-autonomy-patterns" / "SKILL.md"
        content = skill_path.read_text()
        assert content.startswith("---"), "SKILL.md missing YAML frontmatter"
        assert "name: vktest-autonomy-patterns" in content
        assert "description:" in content

    def test_vktest_patterns_includes_all_required_patterns(self):
        """VKTEST patterns skill must document all 9 patterns."""
        skill_path = self.get_skills_dir() / "vktest-autonomy-patterns" / "SKILL.md"
        content = skill_path.read_text()

        required_patterns = [
            "Pattern 1: FSM State Transitions",
            "Pattern 2: PID Depth Stabilization",
            "Pattern 3: Telemetry Buffering & Sync",
            "Pattern 4: Sensor Integration",
            "Pattern 5: Watchdog Heartbeat",
            "Pattern 6: Firebase vs MQTT Decision",
            "Pattern 7: Protocol Robustness",
            "Pattern 8: Operator Timeout & Autonomy",
            "Pattern 9: Cold Start & Battery Sag",
        ]

        for pattern in required_patterns:
            assert pattern in content, f"Missing {pattern} in VKTEST patterns skill"

    def test_vktest_patterns_includes_do_dont_antipattern(self):
        """Each VKTEST pattern must have Do/Don't/Anti-pattern sections."""
        skill_path = self.get_skills_dir() / "vktest-autonomy-patterns" / "SKILL.md"
        content = skill_path.read_text()

        # Each pattern section should contain these subsections
        required_subsections = ["**Do:**", "**Don't:**", "**Anti-pattern:**"]
        for subsection in required_subsections:
            # Count occurrences - should have at least one per pattern section
            count = content.count(subsection)
            assert count >= 4, f"{subsection} not found enough times in patterns"


class TestDocumentationConsistency:
    """Tests for consistency between CLAUDE.md and skills."""

    def test_karpathy_principles_appear_in_both(self):
        """Karpathy principles should be in CLAUDE.md and SKILL.md."""
        claude_md = Path("/home/user/VKTEST/CLAUDE.md").read_text()
        karpathy_skill = (
            Path("/home/user/VKTEST/.claude-skills/karpathy-guidelines/SKILL.md")
            .read_text()
        )

        # Both should mention the 4 principles
        for principle in [
            "Think Before Coding",
            "Simplicity First",
            "Surgical Changes",
            "Goal-Driven Execution",
        ]:
            assert principle in claude_md, f"{principle} missing from CLAUDE.md"
            assert principle in karpathy_skill, f"{principle} missing from Karpathy skill"

    def test_architecture_sections_reference_modules(self):
        """Architecture sections should reference actual code files."""
        claude_md = Path("/home/user/VKTEST/CLAUDE.md").read_text()

        # These files should actually exist
        required_files = [
            "robotics/autonomous_agent_main.py",
            "robotics/motor_control/pid_depth_controller.py",
            "robotics/protocol/robot_data.proto",
            "robotics/protocol/protobuf_serializer.py",
        ]

        for file in required_files:
            assert file in claude_md, f"Module file {file} not mentioned in CLAUDE.md"
            assert Path(f"/home/user/VKTEST/{file}").exists(), f"Module file {file} not found"

    def test_documentation_mentions_key_numbers(self):
        """Documentation should cite key performance metrics."""
        claude_md = Path("/home/user/VKTEST/CLAUDE.md").read_text()

        # Key VKTEST metrics that should be documented
        metrics = {
            "10 Hz": "Control loop frequency",
            "±5 cm": "Depth accuracy",
            "48": "SystemState parameters",
            "99%": "Firebase write reduction",
            "20×": "Battery efficiency improvement",
        }

        for metric, description in metrics.items():
            assert metric in claude_md, f"Missing {description}: {metric}"


class TestProjectIntegrity:
    """Tests for overall project structure integrity."""

    def test_branch_is_correct(self):
        """Verify we're on the correct development branch."""
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd="/home/user/VKTEST",
            capture_output=True,
            text=True,
        )
        branch = result.stdout.strip()
        assert "claude/phased-array-robotics" in branch, f"Wrong branch: {branch}"

    def test_all_tests_pass(self):
        """All existing tests must pass."""
        import subprocess
        result = subprocess.run(
            ["pytest", "tests/", "-q"],
            cwd="/home/user/VKTEST",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Tests failed:\n{result.stdout}\n{result.stderr}"
        assert "passed" in result.stdout, "No tests passed"

    def test_no_uncommitted_critical_changes(self):
        """Critical project files should be committed."""
        import subprocess

        critical_files = [
            "CLAUDE.md",
            ".claude-skills/README.md",
            ".claude-skills/karpathy-guidelines/SKILL.md",
            ".claude-skills/vktest-autonomy-patterns/SKILL.md",
        ]

        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd="/home/user/VKTEST",
            capture_output=True,
            text=True,
        )

        for file in critical_files:
            # File should either be committed (not in status) or modified but staged
            if file in result.stdout:
                assert "M " not in result.stdout or f"M  {file}" not in result.stdout, (
                    f"Critical file {file} has uncommitted changes"
                )
