"""The Inno Setup generator must reference custom-message variables with SINGLE
braces so the f-string substitutes their `{cm:Name}` value.

Field bug (shipped v0.9.99yaa): the uninstaller used `{{cm_remove_user_data}}`
(double braces), so Python emitted the literal text `{cm_remove_user_data}` into
the .iss. Inno then raised `Runtime error: Unknown constant "cm_remove_user_data"`
and the uninstaller crashed before it could remove anything. The splash caption
had the same `{{cm_initialize_caption}}` mistake (silently swallowed by a
surrounding try/except, so it only lost its caption).

A `cm_*` Python variable (e.g. `cm_remove_user_data = "{cm:RemoveUserDataPrompt}"`)
exists precisely so the f-string can write `{cm_remove_user_data}` and get the
colon form out without confusing the f-string parser. Double-bracing it defeats
that and reintroduces the crash.
"""

import re
import unittest
from pathlib import Path

SRC = (Path(__file__).resolve().parents[2] / "build_system" / "ecan_build.py").read_text(
    encoding="utf-8"
)


class InstallerCustomMessageConstantTests(unittest.TestCase):
    def test_no_double_braced_cm_variable_references(self):
        # Any `{{cm_<name>}}` emits a literal `{cm_<name>}` constant that Inno
        # cannot resolve. There must be none.
        offenders = re.findall(r"\{\{cm_[a-z_]+\}\}", SRC)
        self.assertEqual(
            offenders,
            [],
            f"double-braced cm_* references emit unknown Inno constants: {offenders}",
        )

    def test_remove_user_data_uses_single_brace_substitution(self):
        self.assertIn("ExpandConstant('{cm_remove_user_data}')", SRC)
        self.assertNotIn("ExpandConstant('{{cm_remove_user_data}}')", SRC)

    def test_initialize_caption_uses_single_brace_substitution(self):
        self.assertIn("ExpandConstant('{cm_initialize_caption}')", SRC)
        self.assertNotIn("ExpandConstant('{{cm_initialize_caption}}')", SRC)

    def test_referenced_messages_are_defined_for_both_languages(self):
        # The resolved {cm:Name} must exist for english and chinesesimplified,
        # or Inno raises "Unknown custom message" instead.
        for name in ("RemoveUserDataPrompt", "InitializeCaption"):
            self.assertIn(f"english.{name}=", SRC)
            self.assertIn(f"chinesesimplified.{name}=", SRC)


if __name__ == "__main__":
    unittest.main()
