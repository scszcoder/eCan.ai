# The `[Code]` section is compiled by ISCC, not by Python

Two build failures, one cause: the uninstall-lease code in the Inno template had
never been through the compiler, and both times the reported error named a line
in a *generated* file.

## Symptom, round 1

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

## Symptom, round 2

The arity fix shipped, and the next run died eleven lines later — in the same
procedure, at the call that had just been written correctly by count:

```
Compiling [Code] section
Error on line 135 in ...\build\setup.iss: Column 52:
Type mismatch.
Compile aborted.
```

Line 135 was `if not LoadStringsFromFile(…)`'s ancestor,
`if not LoadStringFromFile(LeaseFile, Contents) then`, with
`Contents: String` declared in that procedure's `var` block.

## Why the tests did not catch either

All installer tests up to that point either grepped the template for expected
text or rendered it and checked the text. Both are blind to this class of bug:

* rendering only proves the f-string interpolated; the Pascal is compiled later,
  by Inno's own script engine;
* a wrong call still *looks* right in the source. `LoadStringFromFile(LeaseFile)`
  reads perfectly plausible, and so does `LoadStringFromFile(LeaseFile, Contents)`.

Round 1's guard only modelled parameter **counts**. A prototype has two halves,
and the half that was missing is the one round 2 tripped over.

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
| 131 | `Contents := LoadStringFromFile(LeaseFile);` | Real signature is `LoadStringFromFile(const FileName: String; var S: AnsiString): Boolean` — 2 parameters, and the second is not the return value. This is round 1's error. |
| 135 | `if not LoadStringFromFile(LeaseFile, Contents) then` with `Contents: String;` | The arity is right, the type is not. Inno Setup 6 turned that parameter `AnsiString` when the compiler became Unicode, and Pascal Script does not convert `String` → `AnsiString` at a call site — which is exactly why `Pos` is declared with the pseudo-type `AnyString`. This is round 2's error. |
| 358 | `Epoch := (DateTimeToStr(Now) - DateTimeToStr(EncodeDate(1970, 1, 1))) div 10000000;` | `DateTimeToStr`, `Now` and `EncodeDate` are not Inno Pascal Script functions, and `DateTimeToStr` returns a *string*, which cannot be subtracted. Inno has `GetDateTimeString`/`FormatDateTime` and no date-to-number conversion. |
| 360 | `F := CreateFile(LeaseFile, fmCreate, fsNormal, 0);` | Not an Inno function. |
| 365 | `WriteString(F, '...');` | Not an Inno function. |
| 372 | `CloseFile(F);` | Not an Inno function. |

ISCC stops at the first error, so lines 358-372 would each have been a separate
CI round-trip. The same is true of line 135: it was only visible once line 131
compiled.

## The fix

Both lease procedures now use Inno's `TArrayOfString` API — an array of plain
`String`, so no conversion is involved at all:

```pascal
if not LoadStringsFromFile(LeaseFile, Lines) then   // Lines: TArrayOfString
  Exit;
...
SetArrayLength(Lines, 1);
Lines[0] := '{"reason":"uninstall","at":0,"grace_s":"inf","pid":0}';
SaveStringsToFile(LeaseFile, Lines, False);
```

`ClearUninstallLease` scans every line for both markers on the same lease
(`uninstall` and a permanent grace, either `"inf"` or `Infinity`), because the
lease file is a single line today but nothing guarantees that stays true.

`"at":0` is not a placeholder for a timestamp that should have been computed.
`utils/exit_intent.py::read_exit_lease` requires `at` to be a number and nothing
else, and `lease_is_active` computes `(now - at) < grace_s` — with
`grace_s = "inf"` that is true for **any** `at`, forever. The uninstall marker
is the one lease whose timestamp is never consulted.

Encoding: `SaveStringsToFile` writes ASCII and appends a line break, so the
payload arrives as plain ASCII bytes and the file ends in `\r\n`.
`read_exit_lease` decodes with `utf-8-sig`, so neither the trailing newline nor
a BOM from a future UTF-8 writer can turn the permanent marker into "no lease"
(which would let the watchdog relaunch an app the user has just uninstalled).

## How this is now guarded

`tests/unit/test_installer_lease_contract.py` renders the script for all three
build configs and parses the rendered `[Code]` section, stripping comments and
string literals first:

* `test_the_code_section_only_calls_documented_inno_functions` — every global
  call must be a name in `_INNO_SUPPORT_PROTOTYPES`. An unknown name fails.
* `test_the_code_section_matches_the_documented_arities` — and it must be called
  with the documented parameter count (round 1).
* `test_the_code_section_never_calls_an_ansi_string_api` — and it must not be
  one of the routines whose parameters are `AnsiString` (round 2). The whole
  family is rejected, because the script has no `AnsiString` variable to give
  them.
* `test_clear_lease_reads_the_file_with_the_array_api`,
  `test_the_lease_array_is_declared_with_the_inno_array_type`,
  `test_the_lease_is_written_with_one_documented_call` — the three shapes above,
  pinned literally.
* `test_shutdown_lease_timestamp_is_a_number_that_never_expires` — `"at":0`, and
  no date arithmetic anywhere in the routine.
* `tests/unit/test_uninstall_ota_lease.py` pins the bytes the uninstaller
  actually emits (payload plus line break, and the BOM case) and feeds them back
  through `read_exit_lease`.

Verified load-bearing by mutation. Round 1: restoring any of the five bad lines
above turned the tests red (4 failures per mutation). Round 2: five more
mutations, restored one at a time with `cmp` after each —

| Mutation | Failures |
|---|---|
| array reader → single-string reader | 5 |
| array writer → single-string writer | 5 |
| `Lines: TArrayOfString` → `Lines: String` | 1 |
| writer loses its `Append` argument | 4 |
| writer appends instead of overwriting | 1 |

## The rule

**`[Code]` is Pascal, and only ISCC knows whether it compiles.** A test that
greps the template, or even renders it, says nothing about the Pascal.

A prototype has two halves, and a call in `[Code]` has to match both: the
parameter count and the parameter types. Any call whose name is not already in
`_INNO_SUPPORT_PROTOTYPES` must be looked up in the Inno help first — the
"Support Functions Reference" chapter — and the table extended deliberately.
Never add a name because it looks like the Delphi/Win32 function it resembles,
and never assume a `String` argument fits: `CreateFile`, `WriteString`,
`CloseFile`, `Now`, `EncodeDate` and `IntToStr` all exist in Delphi and none of
them exist here, while `LoadStringFromFile` and `SaveStringToFile` exist here
but want `AnsiString`.
