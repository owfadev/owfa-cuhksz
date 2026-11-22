"""State resolution for cuhksz-cli against the OWFA machine substrate (`~/.owfa`).

The connector owns **two** state directories — the bb backend's credentials/session
and the sis backend's — so both live as components under its single home:

    $OWFA_HOME/connectors/cuhksz-cli/homes/<id>/bb/
    $OWFA_HOME/connectors/cuhksz-cli/homes/<id>/sis/

Resolution precedence (the ABI in `.owfa/docs/home.md`, kernel 0.5.2+):

1. ``BB_CLI_HOME`` / ``SIS_CLI_HOME``  explicit override — use exactly this directory
2. the substrate helper               ``component_dir("cuhksz-cli", <component>)``
3. the pre-0.4 scattered home         ``~/.bb-cli`` / ``~/.sis-cli`` — only when no
                                      workspace/helper is found, **or** when the
                                      substrate component does not hold state yet and
                                      the legacy directory still does. This fallback
                                      is loud: one stderr line names the migration
                                      command, because a silent second home is the bug
                                      being fixed (an unmigrated legacy home must
                                      never be stranded behind an empty new one).

Migration is never a side effect. ``cuhksz-cli home status`` inspects; ``cuhksz-cli
home migrate [--dry-run]`` is the only thing that moves state — it pre-flights every
component first, moves (never copies), and leaves a symlink at the legacy path so old
absolute references keep resolving. A component pinned by its explicit override env
refuses the whole migration: an override is honoured exactly, so there is nothing to
migrate into the substrate.

The canonical bootstrap below is kept byte-identical with `.owfa/docs/home.md`;
everything outside it is this connector's layer.

No state ever enters a repository: homes are machine-global, the repo only ships the
connector code.
"""

from __future__ import annotations

import sys

CONNECTOR = "cuhksz-cli"
PROG = "cuhksz-cli"
COMPONENTS = ("bb", "sis")
LEGACY_HOMES = {"bb": "~/.bb-cli", "sis": "~/.sis-cli"}
ENV_OVERRIDES = {"bb": "BB_CLI_HOME", "sis": "SIS_CLI_HOME"}
# ABI this connector relies on: component_dir/connector_status/migrate_legacy_home
# landed in owfa_home 0.5.2; an older helper must fail with a friendly message, not
# an AttributeError traceback.
_REQUIRED_HELPER = (
    "component_dir",
    "connector_status",
    "home_dir",
    "homes_root",
    "load_bindings",
    "migrate_legacy_home",
    "resolve_home",
    "resolve_root",
)

# ---- canonical bootstrap (byte-identical with .owfa/docs/home.md) ----
import importlib.util
import os
from pathlib import Path

HELPER_ENV = "OWFA_HOME_HELPER"   # explicit path to owfa_home.py


def _candidates():
    out = []
    env = os.environ.get(HELPER_ENV)
    if env:
        out.append(Path(env).expanduser())
    for start in (Path(__file__).resolve(), Path.cwd().resolve()):
        for parent in (start, *start.parents):
            out.append(parent / ".owfa" / "scripts" / "owfa_home.py")
    return out


def load_owfa_home():
    """Import the machine substrate helper, or None when this connector runs outside a workspace."""
    seen = set()
    for helper in _candidates():
        if helper in seen or not helper.is_file():
            continue
        seen.add(helper)
        spec = importlib.util.spec_from_file_location("owfa_home", helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    return None
# ---- end canonical bootstrap ----

_notified = set()


class MigrationError(RuntimeError):
    """The explicit migrate command cannot run (helper ABI, override, non-empty target, no legacy).

    ``detail`` is the structured JSON payload the CLI emits on stdout before exiting 1.
    """

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message)
        self.detail = detail or {"ok": False, "error": message, "connector": CONNECTOR}


def legacy_home(component: str) -> Path:
    """The pre-0.4 scattered home of one component (~/.bb-cli / ~/.sis-cli)."""
    return Path(LEGACY_HOMES[component]).expanduser()


def helper_path() -> Path | None:
    """Path of the substrate helper this process would import, or None."""
    for path in _candidates():
        if path.is_file():
            return path
    return None


def _helper():
    """The helper module when it implements the 0.5.2+ ABI this connector relies on."""
    module = load_owfa_home()
    if module is None or not all(hasattr(module, name) for name in _REQUIRED_HELPER):
        return None
    return module


def _helper_problem() -> str:
    """A friendly explanation for "no usable helper" — names the actual gap."""
    path = helper_path()
    if path is None:
        return (
            "machine substrate helper (owfa_home.py) not found — install/upgrade the "
            "workspace kernel to plant .owfa/scripts/owfa_home.py, or point "
            "OWFA_HOME_HELPER at it"
        )
    return (
        f"machine substrate helper {path} predates the 0.5.2 ABI this connector needs "
        f"({', '.join(_REQUIRED_HELPER)}) — upgrade the workspace kernel or re-plant the helper"
    )


def _notice(key: str, line: str) -> None:
    """One loud stderr line per situation per process: the fallback is never silent."""
    if key in _notified:
        return
    _notified.add(key)
    print(f"[{PROG} home] {line}", file=sys.stderr)


def _has_state(path: Path) -> bool:
    try:
        return path.is_dir() and any(path.iterdir())
    except OSError:
        return path.exists()


def _mkdir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def resolve_component(component: str, *, root: str = "", create: bool = True) -> dict:
    """Resolve one state component at run time; never invents a second home.

    Returns {"component", "path", "source", "env", "substrate_home"} where source is
    one of "env-override" | "substrate" | "legacy". `create` makes the chosen
    directory 0700 on demand; when the legacy directory still holds the state it is
    chosen and the substrate component is NOT created (so the migration can move the
    state into an empty target later). `home status` passes create=False.
    """
    env_name = ENV_OVERRIDES[component]
    raw = os.environ.get(env_name)
    legacy = legacy_home(component)
    if raw:
        path = Path(raw).expanduser()
        return {"component": component, "path": _mkdir(path) if create else path,
                "source": "env-override", "env": env_name, "substrate_home": None}
    module = _helper()
    if module is None:
        _notice(
            f"{component}-no-helper",
            f"{component}: {_helper_problem()} — keeping the pre-0.4 home {legacy}; "
            f"once the helper is available inspect `{PROG} home status`, then run "
            f"`{PROG} home migrate --dry-run` and `{PROG} home migrate`",
        )
        if create:
            _mkdir(legacy)
        return {"component": component, "path": legacy, "source": "legacy",
                "env": env_name, "substrate_home": None}

    substrate = Path(module.component_dir(CONNECTOR, component, explicit_root=root, create=False))
    legacy_is_real = legacy.is_dir() and not legacy.is_symlink()
    if legacy_is_real and not _has_state(substrate):
        # The old state is the only state; using an empty new home would strand it.
        _notice(
            f"{component}-legacy-state",
            f"legacy {component} home {legacy} still holds the state and the substrate "
            f"component {substrate} holds none yet — never migrate silently; inspect "
            f"`{PROG} home status`, then run `{PROG} home migrate --dry-run` and "
            f"`{PROG} home migrate`",
        )
        if create and not legacy.exists():
            _mkdir(legacy)
        return {"component": component, "path": legacy, "source": "legacy",
                "env": env_name, "substrate_home": substrate}
    if legacy_is_real and _has_state(substrate):
        _notice(
            f"{component}-leftover",
            f"both {legacy} and the substrate component {substrate} exist — using the "
            f"substrate; the legacy directory is a leftover to clean up by hand "
            f"(never auto-deleted)",
        )
    if create:
        module.component_dir(CONNECTOR, component, explicit_root=root, create=True)
    return {"component": component, "path": substrate, "source": "substrate",
            "env": env_name, "substrate_home": substrate}


def _migration_commands() -> dict:
    return {
        "dry_run": f"{PROG} home migrate --dry-run",
        "command": f"{PROG} home migrate",
    }


def status(*, root: str = "") -> dict:
    """Read-only substrate view for `cuhksz-cli home status` (creates nothing)."""
    module = _helper()
    helper_file = helper_path()
    out = {
        "ok": True,
        "connector": CONNECTOR,
        "helper": str(helper_file) if helper_file else None,
        "helper_abi": "0.5.2" if module is not None else None,
        "helper_problem": None if module is not None else _helper_problem(),
        "migration": {**_migration_commands(), "helper_available": module is not None},
        "substrate": None,
        "components": {},
    }
    if module is not None:
        try:
            out["substrate"] = module.connector_status(CONNECTOR, root)
        except Exception as exc:  # a broken helper must not turn read-only status into a crash
            out["substrate"] = {"error": str(exc)}
    for component in COMPONENTS:
        row = resolve_component(component, root=root, create=False)
        legacy = legacy_home(component)
        substrate_home = row.get("substrate_home")
        out["components"][component] = {
            "component": component,
            "state_dir": str(row["path"]),
            "source": row["source"],
            "override_env": row["env"],
            "override_value": os.environ.get(row["env"]) or None,
            "legacy_home": str(legacy),
            "legacy_present": legacy.is_dir(),
            "legacy_is_symlink": legacy.is_symlink(),
            "legacy_has_state": _has_state(legacy),
            "substrate_home": str(substrate_home) if substrate_home else None,
            "substrate_exists": bool(substrate_home and Path(substrate_home).is_dir()),
        }
    return out


def _predict_home(module, root: str) -> tuple[Path, bool]:
    """What `migrate_legacy_home` would bind for this root (without mutating anything).

    Returns (home, dynamic): a root without a binding on a machine that already has
    bindings gets a fresh slug directory allocated at migrate time, so its exact path
    is only a pattern — such a home cannot collide with pre-existing state.
    """
    bindings = module.load_bindings(CONNECTOR)
    norm = os.path.normpath(root)
    for binding in bindings:
        if os.path.normpath(binding.get("root", "")) == norm:
            return Path(binding["home"]), False
    if not bindings:
        return Path(module.home_dir(CONNECTOR, "default")), False
    return Path(module.homes_root(CONNECTOR)) / "<new-binding-id>", True


def _preflight(module, root: str) -> dict:
    """Classify every component and collect refusals — no binding, no move, no mkdir."""
    home, dynamic = _predict_home(module, root)
    rows = []
    refusals = []
    for component in COMPONENTS:
        legacy = legacy_home(component)
        env_name = ENV_OVERRIDES[component]
        target = home / component
        row = {
            "component": component,
            "legacy": str(legacy),
            "target": str(target),
            "override_env": env_name,
            "override_value": os.environ.get(env_name) or None,
            "entries": [],
        }
        if row["override_value"]:
            row["action"] = "refused"
            refusals.append({
                "component": component,
                "reason": "env-override",
                "env": env_name,
                "value": row["override_value"],
                "message": (
                    f"{env_name} is set — an explicit override is honoured exactly, so "
                    f"there is nothing to migrate for the {component} component; unset "
                    f"{env_name} and retry"),
            })
        elif legacy.is_symlink():
            row["action"] = "already-migrated"
        elif not legacy.exists():
            row["action"] = "nothing-to-migrate"
        else:
            try:
                row["entries"] = sorted(p.name for p in legacy.iterdir())
            except OSError as exc:
                refusals.append({
                    "component": component, "reason": "unreadable-legacy",
                    "message": f"cannot read the legacy {component} home {legacy}: {exc}"})
                row["action"] = "refused"
            else:
                if not dynamic and target.is_dir() and any(target.iterdir()):
                    row["action"] = "refused"
                    refusals.append({
                        "component": component,
                        "reason": "target-not-empty",
                        "target": str(target),
                        "message": (
                            f"refusing to migrate: the {component} target {target} already "
                            f"exists and is not empty — move its contents away or pick "
                            f"another workspace root first"),
                    })
                else:
                    row["action"] = "would-migrate"
        rows.append(row)
    return {"home": home, "dynamic": dynamic, "components": rows, "refusals": refusals}


def migrate(*, dry_run: bool = False, root: str = "") -> dict:
    """Explicit legacy -> substrate move. The ONLY code path that moves cuhksz-cli state.

    Pre-flights all components first (explicit override / nothing to migrate / target
    already non-empty); one refusal aborts the whole command before anything moves, with
    a structured JSON error. A real run moves both components; if a move fails midway the
    command reports exactly which components moved and which did not.
    """
    module = _helper()
    if module is None:
        problem = _helper_problem()
        raise MigrationError(
            f"{problem}; this connector cannot perform the move without the 0.5.2 helper",
            {"ok": False, "connector": CONNECTOR, "dry_run": dry_run,
             "error": f"{problem}; cannot migrate without it",
             "migration": {**_migration_commands(), "helper_available": False}},
        )

    # bind the workspace root, not whatever subdirectory the shell happens to be in
    root = str(Path(root or module.resolve_root(CONNECTOR) or os.getcwd()).expanduser().resolve())
    plan = _preflight(module, root)
    rows = plan["components"]

    if plan["refusals"]:
        detail = {
            "ok": False,
            "connector": CONNECTOR,
            "dry_run": dry_run,
            "root": root,
            "error": "; ".join(r["message"] for r in plan["refusals"]),
            "refusals": plan["refusals"],
            "components": rows,
        }
        if any(r["reason"] == "env-override" for r in plan["refusals"]):
            detail["error"] = (
                "refusing to migrate: an explicit component override is set ("
                + ", ".join(f"{r['env']}={r['value']} for {r['component']}"
                            for r in plan["refusals"] if r["reason"] == "env-override")
                + ") — unset it first")
        raise MigrationError(detail["error"], detail)

    moves = [row for row in rows if row["action"] == "would-migrate"]
    if not moves:
        migrated = [row["component"] for row in rows if row["action"] == "already-migrated"]
        if migrated:
            return {
                "ok": True,
                "dry_run": dry_run,
                "already_migrated": True,
                "connector": CONNECTOR,
                "root": root,
                "components": rows,
                "note": ("the legacy path(s) are already symlinks into the substrate; "
                         "nothing to move"),
                "migration": _migration_commands(),
            }
        raise MigrationError(
            "no legacy home to migrate (checked ~/.bb-cli and ~/.sis-cli) — nothing to do",
            {"ok": False, "connector": CONNECTOR, "dry_run": dry_run, "root": root,
             "error": "no legacy home to migrate (checked ~/.bb-cli and ~/.sis-cli) — nothing to do",
             "reason": "nothing-to-migrate", "components": rows,
             "migration": _migration_commands()},
        )

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "connector": CONNECTOR,
            "root": root,
            "components": rows,
            "changes": "would move (never copy) each legacy directory into its substrate "
                       "component and leave a symlink at the legacy path; nothing was changed",
            "migration": _migration_commands(),
        }

    moved = []
    for index, row in enumerate(moves):
        component = row["component"]
        pending = [other["component"] for other in moves[index:]]
        try:
            entry = module.migrate_legacy_home(
                CONNECTOR, row["legacy"], "", root, component)
        except (Exception, SystemExit) as exc:
            detail = {
                "ok": False,
                "connector": CONNECTOR,
                "dry_run": False,
                "root": root,
                "error": f"the {component} move failed ({exc}); migrated: "
                         f"{', '.join(moved) or '(none)'}; not moved: {', '.join(pending)}",
                "moved": moved,
                "not_moved": pending,
                "failed": {"component": component, "error": str(exc)},
                "components": rows,
                "migration": _migration_commands(),
            }
            raise MigrationError(detail["error"], detail)
        row["action"] = "migrated"
        row["binding_id"] = entry.get("id")
        row["home"] = entry.get("home")
        row["target"] = str(Path(entry["home"]) / component) if entry.get("home") else row["target"]
        moved.append(component)
        if plan["dynamic"] and entry.get("home"):
            # the binding id is only known after the first move; complete the plan's targets
            for rest in moves[index + 1:]:
                rest["target"] = str(Path(entry["home"]) / rest["component"])

    return {
        "ok": True,
        "dry_run": False,
        "migrated": moved,
        "connector": CONNECTOR,
        "root": root,
        "home": moves[0].get("home") if moves else None,
        "components": rows,
        "note": "state was moved into the substrate and each legacy path left as a symlink "
                "(the symlinks are human cleanup items, never removed by the connector)",
        "migration": _migration_commands(),
    }
