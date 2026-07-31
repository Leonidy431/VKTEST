"""Журнал решений сессии разработки портативного сварочного контроллера.

Формализует переписку и ключевые технические решения, принятые в ходе
сессии, в виде PEP 8 / PEP 257-совместимого Python-модуля, а не
неструктурированного текста. Каждая запись :class:`DecisionEntry`
фиксирует контекст, принятое решение и обоснование, чтобы будущие
читатели кода понимали "почему", а не только "что".

Запустить как отчет: ``python3 docs/session_log.py``
"""

from dataclasses import dataclass
from enum import Enum


class Phase(Enum):
    """Этапы сессии, соответствующие крупным блокам работы."""

    METHODOLOGY = "Методология критика (ТЗ в README)"
    ARCHITECTURE_PLAN = "Архитектурное планирование"
    REQUIREMENTS_CLARIFICATION = "Уточнение требований (портатив)"
    RESEARCH = "Исследование компонентов"
    IMPLEMENTATION = "Реализация"
    BUG_FIXING = "Обнаружение и исправление дефектов"
    DELIVERY = "Публикация (PR)"
    FOLLOW_UP = "Доработка по замечаниям"
    SELF_AUDIT = "Аудит собственной кодовой базы"
    HARDWARE = "Аппаратная фаза (корпус, KiCad)"


@dataclass(frozen=True)
class DecisionEntry:
    """Одна запись журнала решений.

    Attributes:
        phase: Этап сессии, к которому относится решение.
        topic: Краткое название вопроса, который решался.
        decision: Принятое решение.
        rationale: Обоснование решения.
        artifact: Путь к файлу(ам), где решение реализовано (если есть).
    """

    phase: Phase
    topic: str
    decision: str
    rationale: str
    artifact: str = ""


SESSION_LOG: tuple[DecisionEntry, ...] = (
    DecisionEntry(
        phase=Phase.METHODOLOGY,
        topic="Универсальные таблицы время/ток для электромуфтовой сварки",
        decision=(
            "Отвергнуть универсальные таблицы; параметры сварки должны "
            "браться из штрих-кода/наклейки конкретной муфты."
        ),
        rationale=(
            "Каждая муфта имеет уникальное сопротивление спирали R. "
            "По закону Джоуля-Ленца Q=(U^2/R)*t применение усредненного "
            "времени к муфте с другим R дает недогрев либо термическую "
            "деструкцию полимера."
        ),
        artifact="README.md, critical_analysis/error_detector.py",
    ),
    DecisionEntry(
        phase=Phase.ARCHITECTURE_PLAN,
        topic="Разомкнутый vs замкнутый контур управления",
        decision=(
            "Использовать ПИД-регулятор с обратной связью по напряжению "
            "вместо простого таймера с реле."
        ),
        rationale=(
            "Просадки сети/батареи квадратично снижают мощность "
            "(P=U^2/R); фиксированный таймер не компенсирует это, что "
            "приводит к недогреву в полевых условиях."
        ),
        artifact="simulation/pid_simulator.py, firmware/main/pid_controller.c",
    ),
    DecisionEntry(
        phase=Phase.REQUIREMENTS_CLARIFICATION,
        topic="Форм-фактор аппарата",
        decision="Портативный, носимый аппарат с гибридным питанием.",
        rationale=(
            "Уточнено пользователем: ремонт производится в полевых "
            "условиях, доступ к сети 220В не гарантирован."
        ),
        artifact="docs/architecture.md",
    ),
    DecisionEntry(
        phase=Phase.REQUIREMENTS_CLARIFICATION,
        topic="Источник питания",
        decision="Батарея 48V LiFePO4 + опциональная сеть 220В (гибрид).",
        rationale="Прямой ответ пользователя на уточняющий вопрос.",
        artifact="simulation/power_network.py::LiFePO4Battery",
    ),
    DecisionEntry(
        phase=Phase.REQUIREMENTS_CLARIFICATION,
        topic="Автономность батареи",
        decision=(
            "20-30 сварок на одной зарядке (уточнено и скорректировано "
            "пользователем с первоначальных 5-10)."
        ),
        rationale=(
            "Пользователь явно исправил первоначальную оценку "
            "в процессе диалога."
        ),
        artifact="docs/battery_energy_budget.md",
    ),
    DecisionEntry(
        phase=Phase.RESEARCH,
        topic="Выбор платы ESP32",
        decision=(
            "Отобрано 5 плат из 10+ реально исследованных кандидатов "
            "по 12 параметрам (ядро, ОЗУ, GPIO, АЦП, связь, ток, "
            "температура, габариты, open-hardware, цена)."
        ),
        rationale=(
            "Требование пользователя — не гадать по памяти, а найти "
            "реальные, покупаемые платы; выполнено через агент "
            "с веб-поиском."
        ),
        artifact="hardware/platforms.md",
    ),
    DecisionEntry(
        phase=Phase.BUG_FIXING,
        topic="Формула RMS-напряжения при фазовом управлении симистором",
        decision=(
            "Исправлена нормировка с 1/pi на 1/(2*pi) в "
            "angle_to_rms_voltage."
        ),
        rationale=(
            "Тест на угол=0 (полностью открыт) показал V_rms=V_peak "
            "вместо физически верного V_peak/sqrt(2); ошибка "
            "обнаружена автотестом, не проверкой вручную."
        ),
        artifact="simulation/pid_simulator.py",
    ),
    DecisionEntry(
        phase=Phase.BUG_FIXING,
        topic="Интегральный виндап ПИД-регулятора",
        decision=(
            "Заменен статический clamp интеграла (+-500) на conditional "
            "anti-windup, привязанный к реальному диапазону control_signal "
            "(+-90)."
        ),
        rationale=(
            "При старом clamp интеграл накручивался далеко за пределы, "
            "нужные для угла 0/180 градусов, и после восстановления "
            "запаса напряжения система долго не отпускала насыщение."
        ),
        artifact="simulation/pid_simulator.py, firmware/main/pid_controller.c",
    ),
    DecisionEntry(
        phase=Phase.BUG_FIXING,
        topic="Физически некорректный пример сопротивления муфты",
        decision="Заменено 0.128 Ом на 1.13 Ом во всех тестах и примерах.",
        rationale=(
            "При U=39.5В и R=0.128 Ом ток по закону Ома составил бы "
            "308А, что противоречит заявленным в архитектуре 30-40А. "
            "R=1.13 Ом дает физически согласованные ~35А."
        ),
        artifact="tests/, protocol/barcode_format.md",
    ),
    DecisionEntry(
        phase=Phase.IMPLEMENTATION,
        topic="Покрытие тестами",
        decision="70 тестов на всю Python-логику (pytest).",
        rationale=(
            "Тесты выявили оба физических/математических дефекта выше; "
            "без них дефекты остались бы незамеченными в тексте кода."
        ),
        artifact="tests/",
    ),
    DecisionEntry(
        phase=Phase.DELIVERY,
        topic="Pull Request",
        decision=(
            "PR #1 обновлен с полным описанием изменений, включая явный "
            "список найденных и исправленных дефектов."
        ),
        rationale=(
            "Прозрачность: ревьюер должен видеть не только 'что "
            "добавлено', но и 'что было неправильно и почему исправлено'."
        ),
        artifact="README.md",
    ),
    DecisionEntry(
        phase=Phase.FOLLOW_UP,
        topic="Незавершенные пункты плана",
        decision=(
            "Дописаны docs/safety_analysis.md (FMEA) и "
            "docs/commissioning.md, отсутствовавшие в первой поставке."
        ),
        rationale=(
            "Исходный план (Фаза 1, docs/) включал эти файлы; они не "
            "были созданы в первом проходе и остались техническим "
            "долгом до явного запроса на завершение по ТЗ."
        ),
        artifact="docs/safety_analysis.md, docs/commissioning.md",
    ),
    DecisionEntry(
        phase=Phase.SELF_AUDIT,
        topic="Методология критика применена к самому проекту",
        decision=(
            "Два независимых аудита кода; найдено и исправлено 13 "
            "дефектов (PR #3): критичное расхождение ambient-"
            "компенсации энергии и времени, мертвые защиты "
            "(should_derate, cooling), застревание автомата в ERROR, "
            "бесключевая подпись протоколов, ложный вердикт "
            "is_ready_for_production, незаполняемые RMS-буферы в "
            "прошивке, датчик тока 50А при отсечке 120А и др."
        ),
        rationale=(
            "По запросу пользователя: 'делай оценку и поиск слепых "
            "зон и исправления, затем тесты'. Критик, не примененный "
            "к самому себе, — тоже когнитивное искажение."
        ),
        artifact="PR #3, docs/backlog.md (раздел D)",
    ),
    DecisionEntry(
        phase=Phase.SELF_AUDIT,
        topic="Покрытие тестами и правила clauderc",
        decision=(
            "Покрытие поднято 91% -> 100% (70 -> 115 тестов) по "
            "simulation/control/critical_analysis/protocol; принят "
            "файл clauderc пользователя (цель покрытия >=95%, TDD, "
            "скептичное ревью) как правила проекта."
        ),
        rationale=(
            "Последовательные запросы пользователя: покрытие 85%+, "
            "затем 99%+; clauderc добавлен пользователем в репозиторий "
            "коммитом ada4f4d."
        ),
        artifact="tests/, clauderc, CLAUDE.md (команда coverage)",
    ),
    DecisionEntry(
        phase=Phase.HARDWARE,
        topic="Старт проектирования корпуса и разъемов в KiCad",
        decision=(
            "Составлено 12-фазное ТЗ (габариты -> библиотека -> "
            "контур -> схема -> зазоры -> трассировка -> FMEA-ревью "
            "-> корпус 3D -> панели/IP54 -> термо -> прототип -> "
            "верификация); создан скелет KiCad несущей платы "
            "160x110мм под выбранные стандартные модули: розетка "
            "DevKitC-1, 11 слаботочных разъемов, XT90PW, клеммы M4, "
            "предохранитель 5x20, крепеж M3."
        ),
        rationale=(
            "Запрос пользователя: 'в KiCad начни корпус и разъемы "
            "делать под стандартные выбранные нами платы, в 12 фаз "
            "ТЗ пропиши'. Сам пластиковый корпус - CAD (фазы 8-9); "
            "KiCad отвечает за несущую плату и экспорт STEP."
        ),
        artifact="docs/enclosure_tz.md, hardware/electronics/carrier/",
    ),
    DecisionEntry(
        phase=Phase.HARDWARE,
        topic="Бэклог проекта",
        decision=(
            "Открытые работы из переписки сведены в docs/backlog.md: "
            "12 фаз ТЗ корпуса (A), долги прошивки (B), протокола "
            "(C) и журнал выполненного (D)."
        ),
        rationale=(
            "Запрос пользователя: 'переписку в пеп8 и в беклог' - "
            "переписка фиксируется здесь (PEP 8), работы - в бэклоге."
        ),
        artifact="docs/backlog.md, docs/session_log.py",
    ),
)


def render_report() -> str:
    """Формирует читаемый текстовый отчет по журналу решений."""
    lines: list[str] = []
    current_phase: Phase | None = None
    for entry in SESSION_LOG:
        if entry.phase is not current_phase:
            current_phase = entry.phase
            lines.append(f"\n## {current_phase.value}\n")
        lines.append(f"- {entry.topic}")
        lines.append(f"  Решение: {entry.decision}")
        lines.append(f"  Обоснование: {entry.rationale}")
        if entry.artifact:
            lines.append(f"  Артефакт: {entry.artifact}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(render_report())
