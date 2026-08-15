# scripts/dev/

Developer-only diagnostic and inspection tools. **Not part of the build
or release pipeline.**

Anything in this directory is:

- Opt-in (run by hand, not by GHA or `build.py`).
- Lives outside `build_system/` on purpose — `build_system/` is a sealed
  contract, and ad-hoc measurement scripts would muddy that boundary.
- May hit real cloud buckets / networks when their env vars are set,
  but the *default* invocation is safe (dry-run or local-only).

## What's here

| Script | Purpose |
|---|---|
| `measure_cos_throughput.py` | One-shot probe that uploads a small synthetic payload to COS using the same `PartSize`/`MAXThread` policy as `build_system/scripts/upload_to_cos.py`. Useful when investigating why a specific GHA runner's link to COS ap-shanghai is slow (e.g. is the network cap ~0.35 MB/s, or is the SDK misconfigured?). Requires `ECAN_TENCENT_SECRET_ID` / `ECAN_TENCENT_SECRET_KEY` env vars. |

## Adding to this directory

Three rules:

1. The script must be **human-invoked**, not CI-invoked. If GHA should
   run it, it belongs in `build_system/scripts/` instead.
2. The script must work even when no cloud credentials are present —
   either by no-op'ing or by failing fast with a clear error message.
   Do not silently read from `.env`.
3. Update the table above.

## Scripts that were here but moved

`build_windows.sh` / `build_macos.sh` / `build_linux.sh` used to live
in `build_system/scripts/`. They are **not invoked by the GHA
release workflow** (which calls `python build.py prod --version X
--app cn` directly) and they were never wired into the GitHub
workflow. They are kept as a developer convenience for local
multi-platform builds, but they belong to `build_system/scripts/` —
not here. We do not copy them.