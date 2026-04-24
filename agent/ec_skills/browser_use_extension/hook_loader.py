"""
HookLoader — load external hook bundles into the HookedAgent.

A *hook bundle* is a directory (or Python package) that ships one or more
hooks together with a declarative manifest.  Bundles live outside the app
source tree for customers who want site-specific behavior, and the
in-tree ``hooks/external/feige_chat`` bundle (PR 7) serves as the
reference implementation.

Bundle layout
=============

    my_bundle/
      hook.yaml          # bundle manifest (required)
      hooks.py           # hook classes (entrypoints resolved against here)
      README.md          # optional, for humans
      config.schema.json # optional JSON schema for inline config

Manifest shape (``hook.yaml``)
==============================

    api_version: 1
    bundle: feige_chat
    version: 1.0.0
    description: "..."
    hooks:
      - name: feige_bypass_actions
        entrypoint: "hooks:FeigeBypassActionsHook"   # module:Class OR file.py:Class
        stage: on_event_normalized
        tier: 1                    # external bundles MUST be >= 1
        priority: 20
        permissions:
          tools: ["feige_send_message"]
          network: none
        budget:
          timeout_ms: 500
        state: memory
        state_namespace: ""        # optional; paired hooks share via namespace
        matches: {}
        config: {}                 # bundle-level defaults; merged with user cfg

Spec resolution
===============

``HookBundleSpec.path`` can be:

    * Absolute filesystem path to a bundle directory.
    * Relative path — resolved against
      ``agent/ec_skills/browser_use_extension/hooks/external/``.
    * ``pkg:my_installed_package`` — imported as a Python package;
      its ``__path__[0]`` is used as the bundle root.

Security
========

* External bundles can NEVER declare ``tier: 0``.  The loader rejects
  them with ``TierViolation``.
* Permissions declared in the per-hook manifest are authoritative.
  They become the ``ScopedToolProxy`` whitelist at dispatch time; hooks
  cannot broaden their own permissions at runtime.
* The loader NEVER executes user code to discover hooks — it reads the
  manifest first, decides whether to proceed, and only then imports the
  entrypoint.  Tampered manifests fail pydantic validation.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .hook_api import (
    HOOK_API_VERSION,
    Hook,
    HookApiError,
    HookManifest,
    IncompatibleHookApiVersion,
    Stage,
    TierViolation,
)
from .hook_signing import (
    BundleSignatureError,
    enforce_trust,
)

try:
    import yaml  # type: ignore
    _HAS_YAML = True
except Exception:  # pragma: no cover
    yaml = None  # type: ignore
    _HAS_YAML = False

# Route INFO/WARN/ERROR into the shared eCan log stream so bundle
# load/unload activity is visible alongside BrowserAutomation lines.
logger = logging.getLogger("eCan")

# Default root where in-tree bundles live.  Relative spec paths are resolved
# against this directory.
_IN_TREE_BUNDLE_ROOT = Path(__file__).parent / "hooks" / "external"


# ---------------------------------------------------------------------------
# Errors specific to loading.
# ---------------------------------------------------------------------------
class HookBundleError(HookApiError):
    """Base class for bundle-load failures."""


class BundleManifestError(HookBundleError):
    """Raised when hook.yaml is missing, unparseable, or fails validation."""


class BundleEntrypointError(HookBundleError):
    """Raised when an entrypoint string can't be resolved to a Hook class."""


class BundlePathError(HookBundleError):
    """Raised when a bundle path can't be located on disk."""


# ---------------------------------------------------------------------------
# Public spec type — what callers (build_node.py, tests) hand to the loader.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HookBundleSpec:
    """Declarative request to load a hook bundle.

    Attributes
    ----------
    path
        Where the bundle lives.  See module docstring for the three forms.
    config
        User-supplied inline config.  Merged *over* bundle defaults.  Each
        instantiated hook receives the merged dict as its ``config`` kwarg
        (constructor sig: ``__init__(self, config: dict | None = None)``).
    enabled
        When False the spec is silently skipped by the loader.
    only_hooks
        Optional allow-list of hook names within the bundle.  When empty
        every hook in the manifest is loaded.
    """

    path: str
    config: dict | None = None
    enabled: bool = True
    only_hooks: tuple[str, ...] = ()

    @classmethod
    def from_any(cls, item: Any) -> "HookBundleSpec":
        """Coerce a string / dict / existing spec into a HookBundleSpec."""
        if isinstance(item, HookBundleSpec):
            return item
        if isinstance(item, str):
            return cls(path=item)
        if isinstance(item, dict):
            path = item.get("path")
            if not path:
                raise BundleManifestError(
                    f"hook bundle spec missing 'path': {item!r}"
                )
            only = item.get("only_hooks") or ()
            if isinstance(only, list):
                only = tuple(only)
            return cls(
                path=str(path),
                config=item.get("config") or None,
                enabled=bool(item.get("enabled", True)),
                only_hooks=only,
            )
        raise BundleManifestError(
            f"hook bundle spec must be str, dict, or HookBundleSpec "
            f"(got {type(item).__name__})"
        )


# ---------------------------------------------------------------------------
# Path resolution.
# ---------------------------------------------------------------------------
def _resolve_bundle_dir(path_str: str) -> Path:
    """Translate a spec path into an on-disk bundle directory."""
    if path_str.startswith("pkg:"):
        pkg_name = path_str[len("pkg:"):].strip()
        if not pkg_name:
            raise BundlePathError(f"empty package name in spec: {path_str!r}")
        try:
            mod = importlib.import_module(pkg_name)
        except Exception as e:
            raise BundlePathError(
                f"could not import bundle package {pkg_name!r}: {e}"
            ) from e
        paths = getattr(mod, "__path__", None)
        if not paths:
            raise BundlePathError(
                f"bundle package {pkg_name!r} has no __path__; "
                f"is it a namespace package or regular package?"
            )
        return Path(list(paths)[0]).resolve()

    p = Path(path_str)
    if not p.is_absolute():
        p = (_IN_TREE_BUNDLE_ROOT / p).resolve()
    else:
        p = p.resolve()
    if not p.exists():
        raise BundlePathError(f"bundle directory not found: {p}")
    if not p.is_dir():
        raise BundlePathError(f"bundle path is not a directory: {p}")
    return p


# ---------------------------------------------------------------------------
# Manifest parsing.
# ---------------------------------------------------------------------------
def _read_manifest_file(bundle_dir: Path) -> dict:
    """Read hook.yaml (or hook.json as a fallback) from the bundle dir."""
    yaml_path = bundle_dir / "hook.yaml"
    json_path = bundle_dir / "hook.json"
    if yaml_path.exists():
        if not _HAS_YAML:
            raise BundleManifestError(
                "PyYAML is required to load hook.yaml manifests; "
                "install pyyaml or ship a hook.json instead"
            )
        try:
            with yaml_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            raise BundleManifestError(
                f"failed to parse {yaml_path}: {e}"
            ) from e
    elif json_path.exists():
        import json
        try:
            with json_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise BundleManifestError(
                f"failed to parse {json_path}: {e}"
            ) from e
    else:
        raise BundleManifestError(
            f"no hook.yaml or hook.json found in {bundle_dir}"
        )
    if not isinstance(data, dict):
        raise BundleManifestError(
            f"manifest root must be a mapping, got {type(data).__name__}"
        )
    return data


# ---------------------------------------------------------------------------
# Entrypoint resolution.
# ---------------------------------------------------------------------------
def _load_hook_class(entrypoint: str, bundle_dir: Path) -> type:
    """Resolve ``"module:ClassName"`` or ``"relative.py:ClassName"`` to a class.

    Resolution order:
      1. If the left half ends in ``.py`` OR points at a real file under the
         bundle, load it as a side-loaded module via ``importlib.util``.
      2. Otherwise, treat the left half as a dotted Python module path and
         resolve it via ``importlib.import_module``.
    """
    if ":" not in entrypoint:
        raise BundleEntrypointError(
            f"entrypoint must be 'module:ClassName' or 'file.py:ClassName', "
            f"got {entrypoint!r}"
        )
    left, class_name = entrypoint.rsplit(":", 1)
    left = left.strip()
    class_name = class_name.strip()
    if not left or not class_name:
        raise BundleEntrypointError(f"invalid entrypoint: {entrypoint!r}")

    # Form 1: file path inside the bundle.
    candidate_file = bundle_dir / left
    if left.endswith(".py") or candidate_file.is_file():
        if not candidate_file.is_file():
            raise BundleEntrypointError(
                f"entrypoint file not found: {candidate_file}"
            )
        # Side-load with a unique module name to avoid collisions.
        mod_name = f"_ecan_hookbundle_{bundle_dir.name}_{candidate_file.stem}"
        spec = importlib.util.spec_from_file_location(mod_name, candidate_file)
        if spec is None or spec.loader is None:
            raise BundleEntrypointError(
                f"could not create module spec for {candidate_file}"
            )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        try:
            spec.loader.exec_module(mod)  # type: ignore[attr-defined]
        except Exception as e:
            sys.modules.pop(mod_name, None)
            raise BundleEntrypointError(
                f"failed to import {candidate_file}: {e}"
            ) from e
    else:
        # Form 2: dotted module path.
        try:
            mod = importlib.import_module(left)
        except Exception as e:
            raise BundleEntrypointError(
                f"could not import module {left!r}: {e}"
            ) from e

    cls = getattr(mod, class_name, None)
    if cls is None:
        raise BundleEntrypointError(
            f"class {class_name!r} not found in {left}"
        )
    if not isinstance(cls, type):
        raise BundleEntrypointError(
            f"{entrypoint!r} resolved to {type(cls).__name__}, not a class"
        )
    return cls


# ---------------------------------------------------------------------------
# Manifest → HookManifest translation.
# ---------------------------------------------------------------------------
def _build_hook_manifest(
    bundle_name: str,
    entry: dict,
    api_version: int,
) -> HookManifest:
    """Promote a per-hook manifest entry into a validated HookManifest.

    The bundle-level ``api_version`` propagates to each hook unless the
    entry overrides it.  Mutations happen on a copy so we don't poison the
    caller's dict.
    """
    merged = dict(entry)
    merged.setdefault("hook_api_version", api_version)
    # A nice-to-have: if the bundle author omitted 'entrypoint' entirely,
    # fail loudly rather than letting pydantic issue a confusing error.
    if "entrypoint" not in merged:
        raise BundleManifestError(
            f"bundle {bundle_name!r} hook {merged.get('name')!r} "
            f"is missing 'entrypoint'"
        )
    try:
        mf = HookManifest.model_validate(merged)
    except Exception as e:
        raise BundleManifestError(
            f"bundle {bundle_name!r} hook {merged.get('name')!r} "
            f"failed manifest validation: {e}"
        ) from e
    if not _is_version_supported(mf.hook_api_version):
        raise IncompatibleHookApiVersion(
            f"bundle {bundle_name!r} hook {mf.name!r} declares "
            f"hook_api_version={mf.hook_api_version}, runtime supports "
            f"{HOOK_API_VERSION}"
        )
    if mf.tier == 0:
        raise TierViolation(
            f"external bundle {bundle_name!r} may not declare tier=0 "
            f"(hook {mf.name!r}); tier 0 is reserved for in-tree built-ins"
        )
    return mf


def _is_version_supported(declared: int) -> bool:
    """Mirror the dispatcher's version check so the loader fails early."""
    return declared == HOOK_API_VERSION


# ---------------------------------------------------------------------------
# Instantiation.
# ---------------------------------------------------------------------------
def _instantiate_hook(
    cls: type,
    manifest: HookManifest,
    merged_config: dict,
) -> Hook:
    """Construct a hook instance, handling the common constructor shapes.

    Supported shapes (best to worst):
        __init__(self, config: dict | None = None, manifest: HookManifest | None = None)
        __init__(self, config: dict | None = None)
        __init__(self)                       # config attached post-hoc
    """
    import inspect as _inspect
    try:
        sig = _inspect.signature(cls.__init__)
        params = [p for p in sig.parameters.values() if p.name != "self"]
        kwargs: dict[str, Any] = {}
        accepted = {p.name for p in params}
        if "config" in accepted:
            kwargs["config"] = merged_config
        if "manifest" in accepted:
            kwargs["manifest"] = manifest
        instance = cls(**kwargs)
    except TypeError:
        # Fall back to no-arg construction.
        instance = cls()

    # Attach/override the manifest so dispatcher sees the loader's version.
    setattr(instance, "manifest", manifest)
    # Make config discoverable for hooks that don't take it through __init__.
    if merged_config and not getattr(instance, "config", None):
        setattr(instance, "config", merged_config)

    if not hasattr(instance, "run"):
        raise BundleEntrypointError(
            f"hook class {cls.__name__!r} has no run() method"
        )
    return instance  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Public API.
# ---------------------------------------------------------------------------
def load_bundle(spec: HookBundleSpec | dict | str) -> list[Hook]:
    """Load one hook bundle and return the list of instantiated hooks.

    Raises
    ------
    HookBundleError  (and subclasses) when manifest, path, or entrypoint
    cannot be resolved.  Callers that want best-effort loading should
    catch per-spec in ``load_bundles``.
    """
    sp = HookBundleSpec.from_any(spec)
    if not sp.enabled:
        logger.info(f"[HookLoader] bundle {sp.path!r} disabled, skipping")
        return []

    bundle_dir = _resolve_bundle_dir(sp.path)

    # Signature gate.  Default trust mode is ``permissive`` — unsigned
    # bundles pass through unchanged (preserving backwards compat), and
    # a present-but-broken hook.sig still fails loudly.  ``strict`` /
    # ``lockdown`` modes require signatures; see hook_signing.py.
    enforce_trust(bundle_dir)

    manifest_dict = _read_manifest_file(bundle_dir)

    bundle_name = str(manifest_dict.get("bundle") or bundle_dir.name)
    api_version = int(manifest_dict.get("api_version") or HOOK_API_VERSION)
    raw_hooks = manifest_dict.get("hooks")
    if not isinstance(raw_hooks, list) or not raw_hooks:
        raise BundleManifestError(
            f"bundle {bundle_name!r} must declare a non-empty 'hooks' list"
        )

    bundle_default_cfg = dict(manifest_dict.get("config") or {})
    user_cfg = dict(sp.config or {})
    bundle_merged_cfg = {**bundle_default_cfg, **user_cfg}

    # Make bundle dir importable for "module:Class" style entrypoints that
    # the author may write as top-level package imports (e.g. "hooks:X").
    bundle_parent = str(bundle_dir.parent)
    _ensure_on_sys_path(bundle_parent)

    want_only: set[str] = set(sp.only_hooks or ())
    loaded: list[Hook] = []
    for entry in raw_hooks:
        if not isinstance(entry, dict):
            raise BundleManifestError(
                f"bundle {bundle_name!r} has a non-dict hook entry: {entry!r}"
            )
        if want_only and entry.get("name") not in want_only:
            continue
        # Per-hook config = bundle default ← user-level override ← per-hook manifest config.
        per_hook_cfg = dict(entry.get("config") or {})
        merged_cfg = {**bundle_merged_cfg, **per_hook_cfg}

        manifest = _build_hook_manifest(bundle_name, entry, api_version)

        # Runtime-lane dispatch.  Python hooks load their entrypoint
        # class directly; js_injected + subprocess hooks are wrapped by
        # a lane shim that conforms to the same Hook protocol.
        if manifest.runtime == "js_injected":
            instance = _instantiate_js_lane(manifest, bundle_dir, merged_cfg)
        elif manifest.runtime == "subprocess":
            instance = _instantiate_subprocess_lane(manifest, bundle_dir, merged_cfg)
        else:  # "python"
            cls = _load_hook_class(manifest.entrypoint, bundle_dir)
            instance = _instantiate_hook(cls, manifest, merged_cfg)

        loaded.append(instance)
        logger.info(
            f"[HookLoader] loaded {manifest.name!r} v{manifest.version} "
            f"from bundle {bundle_name!r} (stage={manifest.stage.value}, "
            f"tier={manifest.tier})"
        )
    return loaded


def _instantiate_js_lane(
    manifest: HookManifest,
    bundle_dir: Path,
    merged_config: dict,
) -> Hook:
    """Build a ``JsInjectedLaneHook`` from a manifest + bundle dir."""
    from .hooks.runtime_lanes.js_lane import JsInjectedLaneHook
    js_entry = manifest.entrypoint
    if not isinstance(js_entry, str):
        raise BundleEntrypointError(
            f"js_injected entrypoint must be a file path string, got "
            f"{type(js_entry).__name__}"
        )
    js_path = bundle_dir / js_entry
    if not js_path.is_file():
        raise BundleEntrypointError(
            f"js entrypoint file not found: {js_path}"
        )
    try:
        instance = JsInjectedLaneHook.from_file(
            js_path, manifest=manifest, config=merged_config,
        )
    except Exception as e:
        raise BundleEntrypointError(
            f"could not build JsInjectedLaneHook from {js_path}: {e}"
        ) from e
    return instance  # type: ignore[return-value]


def _instantiate_subprocess_lane(
    manifest: HookManifest,
    bundle_dir: Path,
    merged_config: dict,
) -> Hook:
    """Build a ``SubprocessLaneHook`` from a manifest + bundle dir.

    The subprocess is NOT spawned here — only when the first dispatch
    occurs.  That keeps load_bundle cheap and side-effect-free.
    """
    from .hooks.runtime_lanes.subprocess_lane import SubprocessLaneHook
    try:
        instance = SubprocessLaneHook.from_manifest(
            manifest, bundle_dir, config=merged_config,
        )
    except Exception as e:
        raise BundleEntrypointError(
            f"could not build SubprocessLaneHook for {manifest.name!r}: {e}"
        ) from e
    return instance  # type: ignore[return-value]


def load_bundles(
    specs: Iterable[HookBundleSpec | dict | str] | None,
    *,
    fail_fast: bool = False,
) -> list[Hook]:
    """Load every spec; on error either raise (fail_fast=True) or log+skip."""
    out: list[Hook] = []
    for raw in specs or []:
        try:
            out.extend(load_bundle(raw))
        except HookApiError as e:
            if fail_fast:
                raise
            logger.error(
                f"[HookLoader] failed to load bundle {raw!r}: {e}",
                exc_info=True,
            )
    return out


# ---------------------------------------------------------------------------
# sys.path helper — put the bundle parent on sys.path exactly once.
# ---------------------------------------------------------------------------
def _ensure_on_sys_path(d: str) -> None:
    if d and d not in sys.path:
        sys.path.insert(0, d)


def list_available_bundles(
    root: Path | str | None = None,
) -> list[dict]:
    """Scan a directory of hook bundles and return a catalogue.

    Each entry: ``{path, name, version, description, signed, hooks,
    config_schema, config_defaults}``.  ``path`` is the relative name
    when ``root`` lives under the standard in-tree location, otherwise
    the absolute dir.  Bundles whose ``hook.yaml`` fails to parse are
    skipped with a warning rather than aborting the scan.

    This is the data source the node-editor GUI can consume to render
    a browsable catalogue or dynamic per-bundle config form.
    """
    search_root = Path(root).resolve() if root else _IN_TREE_BUNDLE_ROOT
    if not search_root.is_dir():
        return []
    out: list[dict] = []
    for child in sorted(search_root.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        manifest_path = child / "hook.yaml"
        if not manifest_path.is_file():
            manifest_path = child / "hook.json"
        if not manifest_path.is_file():
            continue
        try:
            # Re-read via the shared parser so YAML/JSON fallback logic
            # stays in one place.
            data = _read_manifest_file(child)
        except Exception as e:
            logger.warning(
                f"[HookLoader] skipping bundle {child.name!r}: {e}"
            )
            continue
        entry = {
            "path": (
                child.name if search_root == _IN_TREE_BUNDLE_ROOT else str(child)
            ),
            "abs_path": str(child),
            "name": str(data.get("bundle") or child.name),
            "version": str(data.get("version") or "0.0.0"),
            "author": str(data.get("author") or ""),
            "description": str(data.get("description") or "").strip(),
            "signed": (child / "hook.sig").is_file(),
            "hooks": [
                {
                    "name": h.get("name"),
                    "stage": h.get("stage"),
                    "runtime": h.get("runtime") or "python",
                    "tier": h.get("tier"),
                    "priority": h.get("priority"),
                }
                for h in (data.get("hooks") or [])
                if isinstance(h, dict)
            ],
            "config_defaults": dict(data.get("config") or {}),
            "config_schema": data.get("config_schema") or None,
        }
        out.append(entry)
    return out


def write_bundle_index(
    output_path: Path | str,
    root: Path | str | None = None,
) -> Path:
    """Write the catalogue produced by ``list_available_bundles`` to
    *output_path* as JSON.  Returns the resolved path.

    Useful as a build step: the node editor can load this static file
    rather than shelling out to Python at runtime.
    """
    import json as _json
    entries = list_available_bundles(root=root)
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        _json.dumps({"bundles": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"[HookLoader] wrote bundle index to {out} ({len(entries)} entries)")
    return out


__all__ = [
    "HookBundleSpec",
    "HookBundleError",
    "BundleManifestError",
    "BundleEntrypointError",
    "BundlePathError",
    "load_bundle",
    "load_bundles",
    "list_available_bundles",
    "write_bundle_index",
]
