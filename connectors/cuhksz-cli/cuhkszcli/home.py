"""State resolution for cuhksz-cli against the OWFA machine substrate (`~/.owfa`).

The connector owns **two** state directories — the bb backend's credentials/session
and the sis backend's — so both live as components under its single home:

    $OWFA_HOME/connectors/cuhksz-cli/homes/<id>/bb/
    $OWFA_HOME/connectors/cuhksz-cli/homes/<id>/sis/

Resolution (the ABI in `.owfa/docs/home.md`, kernel 0.5.2+):

    BB_CLI_HOME / SIS_CLI_HOME explicit override   (compatibility escape hatch, unchanged)
    > the substrate helper's component_dir()      (the default)
    > the pre-0.4 scattered home (~/.bb-cli, ~/.sis-cli) with a one-line loud notice

The canonical bootstrap below is kept byte-identical with `.owfa/docs/home.md`;
everything outside it is this connector's layer. `home status` / `home migrate`
are the only commands that touch the substrate beyond ordinary reads — migration
is never a side effect of a normal command.

No state ever enters a repository: homes are machine-global, the repo only ships
the connector code.
"""

from __future__ import annotations

import sys

CONNECTOR = "cuhksz-cli"
COMPONENTS = ("bb", "sis")
LEGACY_HOMES = {"bb": "~/.bb-cli", "sis": "~/.sis-cli"}
ENV_OVERRIDES = {"bb": "BB_CLI_HOME", "sis": "SIS_CLI_HOME"}

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


def legacy_home(component: str) -> Path:
    """The pre-0.4 scattered home of one component (~/.bb-cli / ~/.sis-cli)."""
    return Path(LEGACY_HOMES[component]).expanduser()


def _notify_legacy(component: str) -> None:
    """One loud stderr line per component per process: fallback is never silent."""
    if component in _notified:
        return
    _notified.add(component)
    print(
        f"[cuhksz-cli] {component}: no OWFA home helper found — using the legacy "
        f"{LEGACY_HOMES[component]} directory; run `cuhksz-cli home migrate --dry-run` "
        "then `cuhksz-cli home migrate` inside a workspace to move it into the substrate",
        file=sys.stderr,
    )


def _mkdir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def resolve_component(component: str, *, root: str = "", create: bool = True) -> dict:
    """Resolve one state component: explicit override > substrate > legacy fallback.

    Returns {"component", "path", "source", "env"} where source is one of
    "env-override" | "substrate" | "legacy". `create` makes the directory 0700 on
    demand; `home status` passes create=False and therefore writes nothing.
    """
    env_name = ENV_OVERRIDES[component]
    raw = os.environ.get(env_name)
    if raw:
        path = Path(raw).expanduser()
        return {"component": component, "path": _mkdir(path) if create else path,
                "source": "env-override", "env": env_name}
    helper = load_owfa_home()
    if helper is not None:
        path = helper.component_dir(CONNECTOR, component, explicit_root=root, create=create)
        return {"component": component, "path": path, "source": "substrate", "env": env_name}
    _notify_legacy(component)
    path = legacy_home(component)
    return {"component": component, "path": _mkdir(path) if create else path,
            "source": "legacy", "env": env_name}


def status(*, root: str = "") -> dict:
    """Read-only substrate view for `cuhksz-cli home status` (writes nothing)."""
    helper = load_owfa_home()
    out = {
        "connector": CONNECTOR,
        "helper": str(Path(getattr(helper, "__file__", "")).resolve()) if helper else None,
        "substrate": helper.connector_status(CONNECTOR, root) if helper else None,
        "components": {},
    }
    for component in COMPONENTS:
        row = resolve_component(component, root=root, create=False)
        legacy = legacy_home(component)
        out["components"][component] = {
            "path": str(row["path"]),
            "source": row["source"],
            "env_override": row["env"],
            "exists": row["path"].is_dir(),
            "legacy_path": str(legacy),
            "legacy_present": os.path.lexists(legacy),
            "legacy_is_symlink": legacy.is_symlink(),
        }
    return out


def _nonempty(path: Path) -> bool:
    try:
        return path.is_dir() and any(path.iterdir())
    except OSError:
        return True


def migrate(*, dry_run: bool = False, root: str = "") -> dict:
    """Move each legacy component home into the substrate (explicit command only).

    `dry_run` inspects and reports — no binding is registered and nothing moves.
    A real run delegates to `migrate_legacy_home(..., component=...)`, which moves
    (never copies) and leaves a symlink at the legacy path. Requires the helper.
    """
    helper = load_owfa_home()
    if helper is None:
        raise SystemExit(
            "[cuhksz-cli] home migrate needs the OWFA machine-substrate helper: run it "
            "from inside a workspace (the loader walks up to .owfa/scripts/owfa_home.py) "
            "or set OWFA_HOME_HELPER to that file's path"
        )
    out = {"connector": CONNECTOR, "dry_run": dry_run, "root": root or os.getcwd(),
           "components": {}}
    for component in COMPONENTS:
        source = legacy_home(component)
        target = helper.component_dir(CONNECTOR, component, explicit_root=root, create=False)
        row = {"legacy": str(source), "target": str(target)}
        if source.is_symlink():
            row["action"] = "already-migrated"
        elif not source.exists():
            row["action"] = "nothing-to-migrate"
        elif dry_run:
            row["action"] = "would-refuse-target-not-empty" if _nonempty(target) else "would-migrate"
        else:
            entry = helper.migrate_legacy_home(CONNECTOR, str(source), "", root, component)
            row["action"] = "migrated"
            row["binding_id"] = entry.get("id")
            row["home"] = entry.get("home")
        out["components"][component] = row
    return out
