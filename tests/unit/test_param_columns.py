"""Parametric search parameters per Microchip MCU table, and per family within a table."""
from agent.ec_skills.chip_docs import param_columns as pc

TREE = [
    {"name": "Amplifiers And Linear", "branchId": "", "subCategories": [
        {"name": "Comparators", "branchId": "chartno_365", "subCategories": []}]},
    {"name": "Microcontrollers And Processors", "branchId": "", "subCategories": [
        {"name": "16-Bit Microcontrollers", "branchId": "", "subCategories": [
            {"name": "New/Popular PIC24E ", "branchId": "chartno_368", "subCategories": []}]},
        {"name": "32-Bit Microprocessors", "branchId": "", "subCategories": [
            {"name": "32-bit MPUs", "branchId": "chartno_1156", "subCategories": []}]},
        {"name": "Digital Signal Controllers", "branchId": "", "subCategories": [
            {"name": "dsPIC33C", "branchId": "chartno_361", "subCategories": []}]}]},
]


def test_only_mcu_and_dsc_charts_are_in_scope():
    assert [(c["id"], c["path"][1:]) for c in pc.charts_in_scope(TREE)] == [
        (368, ["16-Bit Microcontrollers", "New/Popular PIC24E"]),
        (361, ["Digital Signal Controllers", "dsPIC33C"])]


def test_parameters_and_what_each_family_leaves_empty():
    view = {"allColumns": ["Product", "Part Family", "Pincount", "CAN"],
            "columnFilters": [{"column": ["Pincount", 1], "minVal": 28, "maxVal": 64},
                              {"column": ["CAN", 0], "values": ["Yes", "No"]}],
            "chartData": [{"demographics": {"Product": "A1", "Part Family": "A", "Pincount": 28, "CAN": None}},
                          {"demographics": {"Product": "A2", "Part Family": "A", "Pincount": 64, "CAN": ""}},
                          {"demographics": {"Product": "B1", "Part Family": "B", "Pincount": 44, "CAN": "Yes"}}]}
    d = pc.describe_chart({"id": 368, "name": "PIC24E", "path": ["x", "y"]}, view)
    assert d["products"] == 3 and d["family_key"] == "Part Family"
    assert d["parameters"][2] == {"name": "Pincount", "filled": 3, "filter": {"kind": "range", "min": 28, "max": 64}}
    assert d["parameters"][3]["filled"] == 1 and d["parameters"][3]["filter"]["kind"] == "values"
    assert d["families"] == {"A": {"products": 2, "empty": ["CAN"]}, "B": {"products": 1, "empty": []}}
    assert "| Pincount | 28 – 64 | 3/3 |" in pc.render_md([d], "now")


def test_family_from_part_number_when_the_chart_has_no_family_column():
    assert [pc.family_of(p) for p in ("PIC18F47Q43", "AVR128DA48", "dsPIC33CK256MP508", "PIC16F18446",
                                      "ATTINY1614", "PIC24FJ128GA010")] == [
        "PIC18F…Q", "AVR…DA", "DSPIC33CK…MP", "PIC16F", "ATTINY", "PIC24FJ…GA"]
    # a one-value Family column doesn't count as a family
    view = {"allColumns": ["Product", "Family", "CAN"], "columnFilters": [],
            "chartData": [{"demographics": {"Product": "PIC18F47Q43", "Family": "8-bit MCU", "CAN": None}},
                          {"demographics": {"Product": "PIC18F26Q83", "Family": "8-bit MCU", "CAN": "Yes"}}]}
    d = pc.describe_chart({"id": 717, "name": "8-bit PIC MCU", "path": ["x", "y"]}, view)
    assert d["family_key"] == pc.DERIVED and d["families"] == {"PIC18F…Q": {"products": 2, "empty": []}}


def test_rows_without_a_family_value_fall_back_to_the_part_number():
    view = {"allColumns": ["Product", "Part Prefix"], "columnFilters": [],
            "chartData": [{"demographics": {"Product": "PIC32CZ2051CA70144", "Part Prefix": "PIC32CZ "}},
                          {"demographics": {"Product": "PIC32CZ1025CA70100", "Part Prefix": "PIC32CZ"}},
                          {"demographics": {"Product": "ATSAMD21G18A", "Part Prefix": None}},
                          {"demographics": {"Product": "SAME54P20A", "Part Prefix": "SAME"}}]}
    d = pc.describe_chart({"id": 4067, "name": "SAM", "path": ["x", "y"]}, view)
    assert d["family_key"] == "Part Prefix"
    assert {k: v["products"] for k, v in d["families"].items()} == {"ATSAMD21G…A": 1, "PIC32CZ": 2, "SAME": 1}
