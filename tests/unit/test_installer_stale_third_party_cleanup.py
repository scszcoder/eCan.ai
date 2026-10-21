"""The installer must remove the stale ``third_party`` tree before copying files.

Field bug (otaerr0.png / installerr2.png, 2026-10-14): a customer on a
pre-0.9.99yab build had ms-playwright / browser_extensions packed with the
name-over-name nesting bug (commit 97a11e7c8), so chrome.exe, chrome.dll and
each ``<id>.crx`` sat on disk as DIRECTORIES. yab ships them as FILES, and Inno
cannot overwrite a directory with a file — the OTA install aborted with
``MoveFile failed; error code 183`` on ``edibdbjcniadpccecjdfdjjppcpchdlm.crx``.

``PrepareToInstall`` now DelTree's the installer-owned ``third_party`` subtrees
first. These assertions pin that the cleanup exists and — critically — uses the
single ``{{app}}`` f-string escaping that renders to the real Inno ``{app}``
constant, NOT the ``{{{{app}}}}`` form (which renders to a literal ``{{app}}``
that ExpandConstant does not expand — the latent bug still present in
InitializeUninstall).
"""

import re
import unittest
from pathlib import Path

SRC = (Path(__file__).resolve().parents[2] / "build_system" / "ecan_build.py").read_text(
    encoding="utf-8"
)


class StaleThirdPartyCleanupTests(unittest.TestCase):
    def test_both_third_party_locations_are_deltreed(self):
        # _internal\third_party (onedir PyInstaller layout) and a bare
        # third_party fallback must both be removed.
        self.assertIn(r"DelTree(ExpandConstant('{{app}}\\_internal\\third_party')", SRC)
        self.assertIn(r"DelTree(ExpandConstant('{{app}}\\third_party')", SRC)

    def test_cleanup_is_guarded_by_direxists(self):
        # A clean first install has no third_party yet; the DelTree must be
        # guarded so it is a no-op there, not an error.
        self.assertIn(r"if DirExists(ExpandConstant('{{app}}\\_internal\\third_party')) then", SRC)

    def test_uses_real_app_constant_not_literal(self):
        # {{app}} (f-string) -> {app} (Inno constant, expands to the install
        # dir). {{{{app}}}} -> {{app}} (literal, does NOT expand). The cleanup
        # must never use the literal form or it would scan a bogus path.
        self.assertNotIn(r"ExpandConstant('{{{{app}}}}\\_internal\\third_party')", SRC)

    def test_cleanup_lives_in_prepare_to_install(self):
        # It must run in PrepareToInstall (before [Files] copy, after the
        # process kills), not some never-reached spot.
        body = re.search(
            r"function PrepareToInstall\(.*?(?=\n// Skip wizard pages)", SRC, re.DOTALL
        )
        self.assertTrue(body, "PrepareToInstall body must be locatable")
        self.assertIn("third_party", body.group(0))


if __name__ == "__main__":
    unittest.main()
