# Claude Skills for VKTEST

This directory contains reusable Claude Code skills for the VKTEST autonomous underwater vehicle project.

## Available Skills

### 1. Karpathy Guidelines (`karpathy-guidelines/SKILL.md`)

**When to use:** Before any code change, refactoring, or architectural decision.

**Four core principles:**
1. **Think Before Coding** — Surface assumptions, ask clarifying questions, don't pick silently
2. **Simplicity First** — Minimum code that solves the problem, no speculative features
3. **Surgical Changes** — Touch only what you must, clean up only your own mess
4. **Goal-Driven Execution** — Define verifiable success criteria, loop until verified

**Scope:** Meta-level guidance applicable to all VKTEST tasks.

**Best for:** Avoiding overcomplication, catching scope creep, preventing unwanted refactoring.

---

### 2. VKTEST Autonomy Patterns (`vktest-autonomy-patterns/SKILL.md`)

**When to use:** When implementing FSM logic, PID tuning, telemetry buffering, sensor integration, or operator control.

**Eight patterns covered:**
1. FSM State Transitions — Guard conditions, logging, testing
2. PID Depth Stabilization — Default gains, Ziegler-Nichols tuning, integral windup
3. Telemetry Buffering & Sync — SQLite during silence, MQTT fallback, sequence validation
4. Sensor Integration — Mock classes, SystemState extension, preflight tests
5. Watchdog Heartbeat — 10-sec interval, 30-sec timeout, UART reliability
6. Firebase vs MQTT Decision — When to use each, avoid blind mixing
7. Protocol Robustness — Protobuf, CRC32, sequence IDs, corruption detection
8. Operator Timeout & Autonomy — 5-min fallback, homing route validation
9. Cold Start & Battery Sag — Voltage checks, brownout prevention, discharge curve understanding

**Scope:** Core subsystems (AutonomousAgent, PIDDepthController, TelemetryEngine, AutonomyEngine, ProtobufSerializer).

**Best for:** Preventing architectural regressions, catching anti-patterns before they ship.

---

## How to Use Skills in Claude Code

### Option 1: Reference in your prompt
```
"Use the vktest-autonomy-patterns skill to guide FSM implementation..."
```

### Option 2: Invoke directly from CLI (if skill is registered)
```
/vktest-autonomy-patterns
/karpathy-guidelines
```

### Option 3: Merge into CLAUDE.md (already done)
The Karpathy principles are already integrated into `../CLAUDE.md` with VKTEST-specific context.

---

## Skill Design Philosophy

Each skill follows the **Karpathy principles** (Don't Assume, Simplicity First, Surgical Changes, Goal-Driven):

- **No bloat:** Only document the most common anti-patterns and gotchas
- **VKTEST-specific:** Every pattern includes "Don't" rules tied to real failures we've encountered
- **Testable:** Each pattern includes references to test suites where behavior is verified
- **Actionable:** Patterns show concrete "Do" and "Don't" examples, not abstract theory

---

## Contributing New Skills

To add a new skill (e.g., for Pixel 10 neural networks, WebRTC streaming, hardware testing):

1. Create directory: `.claude-skills/my-skill-name/`
2. Add `SKILL.md` with frontmatter:
   ```yaml
   ---
   name: my-skill-name
   description: What problem this skill solves
   license: MIT
   ---
   ```
3. Document 5-8 key patterns (Do/Don't/Anti-pattern format)
4. Reference existing code paths in VKTEST where pattern is used
5. Add link to this README

---

## Source Attribution

- **Karpathy Guidelines:** Derived from Andrej Karpathy's LLM coding pitfalls analysis (https://x.com/karpathy/status/2015883857489522876), implemented by [andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) (MIT license)
- **VKTEST Patterns:** Original, based on architecture decisions in `docs/ADVANCED_ARCHITECTURE_SYNTHESIS.md` and operational procedures in `docs/OPERATIONAL_STANDARDS_99.md`

---

## Integration with Main CLAUDE.md

The main `CLAUDE.md` file in the project root includes:
- Behavioral Guidelines section (Karpathy principles with VKTEST context)
- Architecture Overview (4-layer system design, FSM, 48-parameter SystemState)
- Module Map (all core subsystems with line counts and responsibilities)
- Development Guidelines (code style, testing, branching)
- Common Workflows (add sensor, debug PID, deploy to Pi)

This skills directory serves as a **deep reference** for experienced developers; the main CLAUDE.md is the **primary onboarding guide**.

