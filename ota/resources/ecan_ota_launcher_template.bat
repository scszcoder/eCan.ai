@echo off
REM OTA launcher: wait __DELAY_SECONDS__ seconds (giving the parent Python
REM process time to fully exit so the installer can replace files), then
REM start the installer with its arguments forwarded verbatim, then
REM delete ourselves so we don't pollute <appdata>\ota_scripts\.
REM
REM Arguments (%*) are passed straight to ``start``. Because they go
REM through ``%*`` rather than being substituted into a single line,
REM paths with spaces, double-quotes, ampersands, carets, parens or
REM percent signs round-trip cleanly.
REM
REM IMPORTANT: do NOT wrap ``__ARGS_COUNT__`` with ``%`` in this template.
REM At parse time batch would expand ``%N%`` as positional arg N followed
REM by a literal ``%`` — so a file whose count happened to coincide with
REM an index past the argv range would render as nothing or as the wrong
REM file path. Python has already substituted the literal count by the
REM time this file is written, so we leave the placeholder percent-free.
setlocal DisableDelayedExpansion
timeout /t __DELAY_SECONDS__ /nobreak >nul
echo [OTA] Launching installer with __ARGS_COUNT__ argument(s)
start "" %*
(del "%~f0" >nul 2>&1)
