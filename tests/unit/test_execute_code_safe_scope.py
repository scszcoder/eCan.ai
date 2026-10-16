"""bu_run_code must run code like a module: top-level names visible everywhere.

2026-10-12: the crawl planner's `"\\n".join(f"| {next_num + i} |..." for i, p in ...)`
failed 4 times with NameError: name 'next_num' is not defined (in <genexpr>),
because exec() got separate globals and locals dicts.
"""
from agent.mcp.server.code_utils.code_tools import execute_code_safe


def test_top_level_names_visible_in_comprehensions_and_functions():
    code = (
        "next_num = 41\n"
        "rows = [f'| {next_num + i} | {p} |' for i, p in enumerate(args['parts'].split(','))]\n"
        "def total():\n"
        "    return len(rows)\n"
        "result = {'rows': rows, 'n': total()}\n"
    )
    res = execute_code_safe(code, input_args={"parts": "PIC16F13143,PIC16F17126"})
    assert res.success, res.error
    assert res.return_value == {"rows": ["| 41 | PIC16F13143 |", "| 42 | PIC16F17126 |"], "n": 2}


def test_args_are_visible_inside_a_genexpr():
    res = execute_code_safe("result = sum(args['k'] for _ in range(3))", input_args={"k": 2})
    assert res.success, res.error
    assert res.return_value == 6
