# The `[Code]` section is compiled by ISCC, not by Python

## Symptom

CI packages the whole app, renders `setup.iss`, starts ISCC, and only then dies:

```
[INSTALLER] Running Inno Setup: C:\Program Files (x86)\Inno Setup 6\ISCC.exe
[INSTALLER] Script file: C:\actions-runner\_work\eCan.ai\eCan.ai\build\setup.iss
  Reading [Code] section
  Parsing [Tasks] section, line 65
  ...
  Compiling [Code] section
Error on line 131 in ...\build\setup.iss: Column 46:
Invalid number of parameters.
Compile aborted.
```

Everything before the installer stage is green (`[MINIBUILD] PROD build
completed successfully`, `[CHROMIUM] OK`, `[INFO] ICO file contains 7 icon(s)`).
The failure names a line in a *generated* file, so the number cannot be looked
up in the repository — it has to be produced by rendering the template.

## Why the tests did not catch it

All installer tests up to that point either grepped the template for expected
text or rendered it and checked the text. Both are blind to this class of bug:

* rendering only proves the f-string interpolated; the Pascal is compiled later,
  by Inno's own script engine;
* a wrong call still *looks* right in the source. `LoadStringFromFile(LeaseFile)`
  reads perfectly plausible.

The lease code made this worse than usual: `ClearUninstallLease` and
`WriteShutdownLease` were added by the shutdown-lease work, and **no tagged
build had ever compiled them** (`git tag --contains c57b3b67b` is empty) — every
build after that commit died earlier, in the Python render step, on the brace
bug in `docs/fixes/INNO_EXPANDCONSTANT_FIX.md`. The braces were fixed, the build
got further, and ISCC finally reached code that had never been compiled.

## What was wrong

Found at these addresses in the rendered `setup.iss` (CN config):

| Line | Code | Why ISCC rejects it |
|---|---|---|
| 131 | `Contents := LoadStringFromFile(LeaseFile);` | Real signature is `LoadStringFromFile(const FileName: String; var S: String): Boolean` — 2 parameters. This is the reported error. |
| 358 | `Epoch := (DateTimeToStr(Now) - DateTimeToStr(EncodeDate(1970, 1, 1))) div 10000000;` | `DateTimeToStr`, `Now` and `EncodeDate` are not Inno Pascal Script functions, and `DateTimeToStr` returns a *string*, which cannot be subtracted. Inno has `GetDateTimeString`/`FormatDateTime` and no date-to-number conversion. |
| 360 | `F := CreateFile(LeaseFile, fmCreate, fsNormal, 0);` | Not an Inno function. |
| 365 | `WriteString(F, '...');` | Not an Inno function. |
| 372 | `CloseFile(F);` | Not an Inno function. |

ISCC stops at the first error, so lines 358-372 would each have been a separate
CI round-trip.

## The fix

`ClearUninstallLease` reads with the documented two-argument form:

```pascal
if not LoadStringFromFile(LeaseFile, Contents) then
  Exit;
```

`WriteShutdownLease` writes with one documented call, and needs no timestamp
arithmetic at all:

```pascal
LeaseJson := '{' +
  '"reason":"uninstall",' +
  '"at":0,' +
  '"grace_s":"inf",' +
  '"pid":0' +
  '}';
SaveStringToFile(LeaseFile, LeaseJson, False);
```

`"at":0` is not a placeholder for a timestamp that should have been computed.
`utils/exit_intent.py::read_exit_lease` requires `at` to be a number and nothing
else, and `lease_is_active` computes `(now - at) < grace_s` — with
`grace_s = "inf"` that is true for **any** `at`, forever. The uninstall marker
is the one lease whose timestamp is never consulted.

`SaveStringToFile`'s encoding is Inno's business, not ours, so
`read_exit_lease` now decodes with `utf-8-sig`: the same bytes for plain UTF-8,
and a BOM cannot silently turn the permanent marker into "no lease" (which would
let the watchdog relaunch an app the user has just uninstalled).

## How this is now guarded

`tests/unit/test_installer_lease_contract.py` renders the script for all three
build configs and parses the rendered `[Code]` section, stripping comments and
string literals first:

* `test_the_code_section_only_calls_documented_inno_functions` — every global
  call must be a name in `_INNO_SUPPORT_ARITY`. An unknown name fails.
* `test_the_code_section_matches_the_documented_arities` — and it must be called
  with the documented parameter count.
* `test_clear_lease_reads_the_file_with_the_inno_signature`,
  `test_the_lease_is_written_with_one_documented_call` — the two shapes above,
  pinned literally.
* `test_shutdown_lease_timestamp_is_a_number_that_never_expires` — `"at":0`, and
  no date arithmetic anywhere in the routine.
* `tests/unit/test_uninstall_ota_lease.py` pins the file the uninstaller
  actually emits, including the BOM case.

Verified load-bearing by mutation: restoring any of the five bad lines above
turns those tests red (4 failures per mutation), and each restore was checked
with `cmp`.

## The rule

**`[Code]` is Pascal, and only ISCC knows whether it compiles.** A test that
greps the template, or even renders it, says nothing about the Pascal. Any call
added to `[Code]` whose name is not already in `_INNO_SUPPORT_ARITY` must be
looked up in the Inno help first — the "Support Functions Reference" chapter —
and the table extended deliberately. Never add a name because it looks like the
Delphi/Win32 function it resembles: `CreateFile`, `WriteString`, `CloseFile`,
`Now`, `EncodeDate` and `IntToStr` all exist in Delphi and none of them exist
here.
