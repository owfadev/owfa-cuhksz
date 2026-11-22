import importlib.util
import os
import re


def _load_helper(ctx):
    """Find the workspace's machine-substrate helper (read-only import)."""
    root = getattr(ctx, "root", "") or ""
    candidates = []
    env = os.environ.get("OWFA_HOME_HELPER")
    if env:
        candidates.append(os.path.expanduser(env))
    if root:
        walk = os.path.abspath(str(root))
        while True:
            candidates.append(os.path.join(walk, ".owfa", "scripts", "owfa_home.py"))
            parent = os.path.dirname(walk)
            if parent == walk:
                break
            walk = parent
    for path in candidates:
        if os.path.isfile(path):
            spec = importlib.util.spec_from_file_location("owfa_home_verify", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    return None


def _component_path(helper, ctx, component):
    return helper.component_dir(
        "cuhksz-cli", component, explicit_root=str(getattr(ctx, "root", "") or ""), create=False)


def verify(ctx):
    issues = []
    idp = os.path.join(ctx.root, "wiki", "cuhksz", "identity.md")
    if not os.path.exists(idp):
        issues.append(("error", "wiki/cuhksz/identity.md missing — create it per the identity constitution (sis block from transcript)"))
    else:
        with open(idp, encoding="utf-8") as handle:
            text = handle.read()
        if not re.search(r"^type:\s*cuhksz\s*$", text, re.M):
            issues.append(("error", "identity.md missing `type: cuhksz`"))
        if "student_id" not in text:
            issues.append(("error", "identity.md missing the sis block mapping (student_id ...)"))

    helper = _load_helper(ctx)
    if helper is not None:
        for component in ("bb", "sis"):
            path = _component_path(helper, ctx, component)
            if not os.path.isdir(path):
                issues.append(("warning", f"cuhksz-cli {component} not logged in yet ({path} absent) — guide the user at first pull"))
        for component, legacy in (("bb", "~/.bb-cli"), ("sis", "~/.sis-cli")):
            legacy_path = os.path.expanduser(legacy)
            if os.path.lexists(legacy_path) and not os.path.islink(legacy_path):
                issues.append((
                    "warning",
                    f"legacy {legacy} is still a real directory — run `cuhksz-cli home migrate --dry-run` "
                    "then `cuhksz-cli home migrate` to move it into the substrate",
                ))
    else:
        for legacy, component in (("~/.bb-cli", "bb"), ("~/.sis-cli", "sis")):
            if not os.path.isdir(os.path.expanduser(legacy)):
                issues.append((
                    "warning",
                    f"cuhksz-cli {component} not logged in yet ({legacy} absent; no OWFA home helper found — "
                    "legacy fallback) — guide the user at first pull",
                ))
    return issues
