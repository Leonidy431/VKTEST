#!/usr/bin/env python3
"""Генератор скелета KiCad-проекта несущей платы (фаза 3 ТЗ).

Создает carrier.kicad_pro / .kicad_sch / .kicad_pcb (формат KiCad 7):
контур 160x110мм, крепеж M3, черновые посадочные места всех разъемов
под выбранные стандартные платы (см. docs/enclosure_tz.md, таблица).

Файлы генерируются детерминированно (uuid5 от имени объекта), поэтому
повторный запуск дает идентичный результат — diff-friendly.

Запуск:  python3 hardware/electronics/carrier/generate_kicad.py

ВАЖНО: посадочные места — черновые (фаза 3). Размеры с пометкой
"verify" в комментариях ниже требуют сверки с даташитами (фазы 1-2 ТЗ)
до начала трассировки.
"""

import uuid
from pathlib import Path

OUT_DIR = Path(__file__).parent
NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

BOARD_W = 160.0
BOARD_H = 110.0
PITCH = 2.54


def uid(name: str) -> str:
    return str(uuid.uuid5(NS, "welder-carrier/" + name))


def fp_text(kind: str, text: str, y: float, layer: str, name: str) -> str:
    return (
        f'    (fp_text {kind} "{text}" (at 0 {y} 0) (layer "{layer}")'
        f' (tstamp "{uid(name)}")\n'
        f'      (effects (font (size 1 1) (thickness 0.15)))\n'
        f'    )\n'
    )


def pad(num: str, shape: str, x: float, y: float, size: float,
        drill: float, name: str) -> str:
    return (
        f'    (pad "{num}" thru_hole {shape} (at {x:.2f} {y:.2f})'
        f' (size {size} {size}) (drill {drill})'
        f' (layers "*.Cu" "*.Mask") (tstamp "{uid(name)}"))\n'
    )


def header_fp(ref: str, value: str, at_x: float, at_y: float, npins: int,
              vertical: bool) -> str:
    """Гребенка 1xN, шаг 2.54мм, пад 1.7/сверло 1.0."""
    body = f'  (footprint "Carrier:PinHeader_1x{npins:02d}" (layer "F.Cu")\n'
    body += f'    (tstamp "{uid(ref)}")\n'
    body += f'    (at {at_x:.2f} {at_y:.2f})\n'
    body += '    (attr through_hole)\n'
    body += fp_text("reference", ref, -2.5, "F.SilkS", ref + "/ref")
    body += fp_text("value", value, 2.5, "F.Fab", ref + "/val")
    for i in range(npins):
        dx, dy = (0.0, i * PITCH) if vertical else (i * PITCH, 0.0)
        shape = "rect" if i == 0 else "oval"
        body += pad(str(i + 1), shape, dx, dy, 1.7, 1.0,
                    f"{ref}/pad{i + 1}")
    body += '  )\n'
    return body


def devkit_socket_fp(ref: str, at_x: float, at_y: float) -> str:
    """Розетка ESP32-S3-DevKitC-1: 2 ряда 1x22.

    Межрядное расстояние 22.86мм (0.9") — verify по чертежу Espressif
    (фаза 1 ТЗ).
    """
    row_gap = 22.86
    body = f'  (footprint "Carrier:ESP32S3_DevKitC1_Socket" (layer "F.Cu")\n'
    body += f'    (tstamp "{uid(ref)}")\n'
    body += f'    (at {at_x:.2f} {at_y:.2f})\n'
    body += '    (attr through_hole)\n'
    body += fp_text("reference", ref, -2.5, "F.SilkS", ref + "/ref")
    body += fp_text("value", "ESP32-S3-DevKitC-1 (2x1x22, verify 22.86mm)",
                    2.5, "F.Fab", ref + "/val")
    for i in range(22):
        shape = "rect" if i == 0 else "oval"
        body += pad(str(i + 1), shape, 0.0, i * PITCH, 1.7, 1.0,
                    f"{ref}/A{i + 1}")
        body += pad(str(i + 23), "oval", row_gap, i * PITCH, 1.7, 1.0,
                    f"{ref}/B{i + 1}")
    body += '  )\n'
    return body


def big_pads_fp(ref: str, value: str, at_x: float, at_y: float,
                pads: list, pad_size: float, drill: float) -> str:
    """Крупные силовые площадки (XT90PW, M4 клеммы, предохранитель)."""
    body = f'  (footprint "Carrier:{ref}_power" (layer "F.Cu")\n'
    body += f'    (tstamp "{uid(ref)}")\n'
    body += f'    (at {at_x:.2f} {at_y:.2f})\n'
    body += '    (attr through_hole)\n'
    body += fp_text("reference", ref, -pad_size, "F.SilkS", ref + "/ref")
    body += fp_text("value", value, pad_size, "F.Fab", ref + "/val")
    for num, (dx, dy) in enumerate(pads, start=1):
        body += pad(str(num), "circle", dx, dy, pad_size, drill,
                    f"{ref}/pad{num}")
    body += '  )\n'
    return body


def mount_hole_fp(ref: str, at_x: float, at_y: float) -> str:
    body = f'  (footprint "Carrier:MountingHole_M3" (layer "F.Cu")\n'
    body += f'    (tstamp "{uid(ref)}")\n'
    body += f'    (at {at_x:.2f} {at_y:.2f})\n'
    body += '    (attr through_hole exclude_from_pos_files)\n'
    body += fp_text("reference", ref, -4.0, "F.SilkS", ref + "/ref")
    body += fp_text("value", "M3", 4.0, "F.Fab", ref + "/val")
    body += pad("1", "circle", 0.0, 0.0, 6.0, 3.2, ref + "/pad1")
    body += '  )\n'
    return body


def gr_line(x1, y1, x2, y2, name: str) -> str:
    return (
        f'  (gr_line (start {x1:.2f} {y1:.2f}) (end {x2:.2f} {y2:.2f})'
        f' (stroke (width 0.15) (type default)) (layer "Edge.Cuts")'
        f' (tstamp "{uid(name)}"))\n'
    )


def gr_text(text: str, x: float, y: float, size: float, name: str) -> str:
    return (
        f'  (gr_text "{text}" (at {x:.2f} {y:.2f} 0) (layer "F.SilkS")'
        f' (tstamp "{uid(name)}")\n'
        f'    (effects (font (size {size} {size})'
        f' (thickness {size / 6:.2f})))\n'
        f'  )\n'
    )


LAYERS = """  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (32 "B.Adhes" user "B.Adhesive")
    (33 "F.Adhes" user "F.Adhesive")
    (34 "B.Paste" user)
    (35 "F.Paste" user)
    (36 "B.SilkS" user "B.Silkscreen")
    (37 "F.SilkS" user "F.Silkscreen")
    (38 "B.Mask" user)
    (39 "F.Mask" user)
    (40 "Dwgs.User" user "User.Drawings")
    (41 "Cmts.User" user "User.Comments")
    (42 "Eco1.User" user "User.Eco1")
    (43 "Eco2.User" user "User.Eco2")
    (44 "Edge.Cuts" user)
    (45 "Margin" user)
    (46 "B.CrtYd" user "B.Courtyard")
    (47 "F.CrtYd" user "F.Courtyard")
    (48 "B.Fab" user)
    (49 "F.Fab" user)
  )
"""


def build_pcb() -> str:
    s = '(kicad_pcb (version 20221018) (generator pcbnew)\n'
    s += '  (general (thickness 1.6))\n'
    s += '  (paper "A3")\n'
    s += LAYERS
    s += '  (setup (pad_to_mask_clearance 0))\n'
    s += '  (net 0 "")\n'

    # Контур платы 160x110
    s += gr_line(0, 0, BOARD_W, 0, "edge/top")
    s += gr_line(BOARD_W, 0, BOARD_W, BOARD_H, "edge/right")
    s += gr_line(BOARD_W, BOARD_H, 0, BOARD_H, "edge/bottom")
    s += gr_line(0, BOARD_H, 0, 0, "edge/left")

    # Крепеж M3 под бобышки корпуса (фаза 8 ТЗ)
    for ref, (x, y) in {
        "H1": (5, 5), "H2": (BOARD_W - 5, 5),
        "H3": (5, BOARD_H - 5), "H4": (BOARD_W - 5, BOARD_H - 5),
    }.items():
        s += mount_hole_fp(ref, x, y)

    # Вычислитель
    s += devkit_socket_fp("U1", 30, 22)

    # Слаботочные разъемы (модули из hardware/bom.csv)
    s += header_fp("J4", "TFT 2.4 SPI 1x14", 66, 10, 14, False)
    s += header_fp("J5", "Buttons 4+GND 1x5", 112, 10, 5, False)
    s += header_fp("J12", "microSD SPI 1x6", 66, 100, 6, False)
    s += header_fp("J13", "RTC DS3231 I2C 1x4", 88, 100, 4, False)
    s += header_fp("J6", "DS18B20 1-Wire 1x3", 103, 100, 3, False)
    s += header_fp("J7", "ZeroCross in 1x3", 115, 100, 3, False)
    s += header_fp("J8", "ACS758-150B 1x3", 122, 22, 3, True)
    s += header_fp("J9", "Triac gate MOC3083 1x3", 122, 34, 3, True)
    s += header_fp("J10", "Fan 5V PWM 1x3", 122, 46, 3, True)
    s += header_fp("J11", "Buzzer 1x2", 122, 58, 2, True)
    s += header_fp("J14", "V-sense divider 1x2", 122, 66, 2, True)

    # Силовая зона: вход 48В, предохранитель, сварочный выход
    # XT90PW-M: шаг выводов 10.5мм, пад 8.0/сверло 4.5 — verify (фаза 1)
    s += big_pads_fp("J1", "XT90PW-M 48V in (verify 10.5mm)",
                     146, 78, [(0, 0), (0, 10.5)], 8.0, 4.5)
    # Клеммы M4 сварочного выхода: пад 10, сверло 4.3
    s += big_pads_fp("J2", "WELD+ M4", 150, 25, [(0, 0)], 10.0, 4.3)
    s += big_pads_fp("J3", "WELD- M4", 150, 45, [(0, 0)], 10.0, 4.3)
    # Держатель предохранителя 5x20, шаг 22мм — verify (фаза 1)
    s += big_pads_fp("F1", "Fuse 5x20 aR (verify 22mm)",
                     100, 80, [(0, 0), (22, 0)], 5.0, 2.6)

    # Зонирование (фаза 5 ТЗ)
    s += gr_text("SKEPTICAL WELDER CARRIER v0.1 (PHASE 3 DRAFT)",
                 55, 4, 2.0, "txt/title")
    s += gr_text("LV 3V3/5V", 30, 15, 1.5, "txt/lv")
    s += gr_text("48V DC", 123, 88, 1.5, "txt/48v")
    s += gr_text("WELD OUT 110A", 138, 35, 1.5, "txt/weld")
    s += ')\n'
    return s


def build_sch() -> str:
    pinmap = (
        "Несущая плата: карта подключения (фаза 4 ТЗ — черновик).\\n"
        "Синхронизировать с firmware/main/*.h перед трассировкой:\\n"
        "  J7 ZeroCross  -> GPIO4  (zero_crossing.c ZC_GPIO_PIN)\\n"
        "  J9 TriacGate  -> GPIO5  (TRIAC_GATE_GPIO_PIN)\\n"
        "  J14 V-sense   -> ADC1_CH0 (measurements.h, verify GPIO)\\n"
        "  J8 ACS758     -> ADC1_CH1 (measurements.h, verify GPIO)\\n"
        "  J4 TFT SPI, J12 microSD SPI, J13 I2C, J6 1-Wire,\\n"
        "  J5 кнопки, J10 PWM кулера, J11 зуммер — назначить в фазе 4.\\n"
        "Схемные символы и ERC — фаза 4; этот лист фиксирует состав\\n"
        "разъемов и является источником для docs/enclosure_tz.md."
    )
    s = '(kicad_sch (version 20230121) (generator eeschema)\n'
    s += f'  (uuid "{uid("sch/root")}")\n'
    s += '  (paper "A3")\n'
    s += '  (title_block\n'
    s += '    (title "Welder carrier board - connector map")\n'
    s += '    (date "2026-07-30")\n'
    s += '    (rev "0.1")\n'
    s += '    (company "Skeptical Critic Welder")\n'
    s += '  )\n'
    s += f'  (text "{pinmap}" (at 20 40 0)\n'
    s += '    (effects (font (size 2 2)) (justify left bottom))\n'
    s += f'    (uuid "{uid("sch/pinmap")}")\n'
    s += '  )\n'
    s += '  (sheet_instances (path "/" (page "1")))\n'
    s += ')\n'
    return s


def build_pro() -> str:
    return (
        '{\n'
        '  "board": { "design_settings": {} },\n'
        '  "meta": { "filename": "carrier.kicad_pro", "version": 1 },\n'
        '  "schematic": { "legacy_lib_dir": "", "legacy_lib_list": [] },\n'
        f'  "sheets": [ [ "{uid("sch/root")}", "" ] ],\n'
        '  "text_variables": {}\n'
        '}\n'
    )


def check_balanced(text: str, path: str) -> None:
    depth = 0
    in_str = False
    prev = ""
    for ch in text:
        if in_str:
            if ch == '"' and prev != "\\":
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                raise SystemExit(f"{path}: unbalanced ')'")
        prev = ch
    if depth != 0 or in_str:
        raise SystemExit(f"{path}: unbalanced (depth={depth}, str={in_str})")


def main() -> None:
    files = {
        "carrier.kicad_pcb": build_pcb(),
        "carrier.kicad_sch": build_sch(),
        "carrier.kicad_pro": build_pro(),
    }
    for name, content in files.items():
        if name.endswith((".kicad_pcb", ".kicad_sch")):
            check_balanced(content, name)
        (OUT_DIR / name).write_text(content, encoding="utf-8")
        print(f"wrote {name}: {len(content)} bytes")


if __name__ == "__main__":
    main()
