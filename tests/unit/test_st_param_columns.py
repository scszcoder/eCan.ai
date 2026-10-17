"""st_param_columns: the parameters of ST's MCU product selector tables."""
from agent.ec_skills.chip_docs import st_param_columns as st

COLS = [
    {"id": "1", "name": "Part Number", "type": "string"},
    {"id": "1453", "name": "Supply Voltage", "type": "float", "units": "volts", "qualifier": "min"},
    {"id": "1455", "name": "Supply Voltage", "type": "float", "units": "volts", "qualifier": "max"},
    {"id": "5045", "name": "Timers", "type": "integer", "qualifier": "typ", "conditional": "16-bit"},
    {"id": "5279", "name": "Number of Channels", "type": "integer", "aggregation": "A/D Converters 12-bit"},
    {"id": "977", "name": "Other timer functions", "type": "multi"},
]


def _row(part, cells):
    return {"productFolderUrl": f"/en/microcontrollers-microprocessors/{part.lower()}.html",
            "cells": [{"columnId": "1", "value": part}] + [{"columnId": k, "value": v} for k, v in cells.items()]}


GRID = {"levelTitle": "STM32 mainstream MCUs", "columns": COLS, "rows": [
    _row("STM32F103C8", {"1453": "2", "1455": "3.6", "5045": "4", "977": "IWDG||SysTick"}),
    _row("STM32F103RB", {"1453": "2", "1455": "3.6", "5045": "4", "977": "WWDG"}),
    _row("STM32G071RB", {"1453": "1.7", "1455": "3.6", "5279": "16"}),
]}


def test_duplicate_names_get_their_qualifiers():
    assert [st.column_label(c) for c in COLS] == [
        "Part Number", "Supply Voltage (min)", "Supply Voltage (max)", "Timers (16-bit)",
        "A/D Converters 12-bit: Number of Channels", "Other timer functions"]


def test_series_from_part_number():
    assert [st.series_of(p) for p in ("STM32F103C8", "STM32WBA62MI", "STM8S003K3", "SPC582B60E1", "SR6P7C8")] == [
        "STM32F1", "STM32WBA6", "STM8S", "SPC58", "SR6P"]


def test_describe_grid_counts_ranges_values_and_per_series_gaps():
    c = st.describe_grid("SC2155", GRID)
    assert c["name"] == "STM32 mainstream MCUs" and c["products"] == 3
    assert c["url"] == "https://www.st.com/en/microcontrollers-microprocessors/stm32-mainstream-mcus/products.html"
    p = {x["name"]: x for x in c["parameters"]}
    assert p["Supply Voltage (min)"]["filled"] == 3
    assert p["Supply Voltage (min)"]["filter"] == {"kind": "range", "min": 1.7, "max": 2.0}
    assert p["Other timer functions"]["filter"] == {"kind": "values", "values": ["IWDG", "SysTick", "WWDG"]}
    assert "filter" not in p["Part Number"]  # one value per part: not a filter
    assert c["families"]["STM32F1"] == {"products": 2, "empty": ["A/D Converters 12-bit: Number of Channels"]}
    assert c["families"]["STM32G0"]["empty"] == ["Timers (16-bit)", "Other timer functions"]
