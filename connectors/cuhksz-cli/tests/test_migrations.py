"""Offline regressions for the package migration verify hook (migrations/init.py).

Runs with temp HOME / OWFA_HOME; the verify hook is read-only and must never
create or move a connector home.
"""
import contextlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

DEFAULT_HELPER = "~/dev/owfa/.owfa/scripts/owfa_home.py"
HELPER = Path(os.environ.get("OWFA_HOME_HELPER") or DEFAULT_HELPER).expanduser()


def find_migrations_init(start: Path | None = None) -> Path | None:
    """Locate `migrations/init.py` without assuming the package-source depth.

    Two supported layouts, searched upward from this test file (or `start`):
    the package source (`<repo>/migrations/init.py`) and an installed domain
    (`<instance>/.owfa/plugins/domains/<pkg>/migrations/init.py`). Returns
    None when neither exists so the suite skips instead of erroring.
    """
    probe = (start or Path(__file__)).resolve()
    base = probe if probe.is_dir() else probe.parent
    for parent in (base, *base.parents):
        direct = parent / "migrations" / "init.py"
        if direct.is_file():
            return direct
        domains = parent / ".owfa" / "plugins" / "domains"
        if not domains.is_dir():
            continue
        matches = sorted(domains.glob("*/migrations/init.py"))
        for candidate in matches:  # prefer this package when several are installed
            if candidate.parent.parent.name == "cuhksz":
                return candidate
        if matches:
            return matches[0]
    return None


INIT_PY = find_migrations_init()


def load_verify():
    spec = importlib.util.spec_from_file_location("cuhksz_init_verify", INIT_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify


@contextlib.contextmanager
def isolated(helper: str):
    """Temp HOME + OWFA_HOME; `helper` is the OWFA_HOME_HELPER value ('' = none)."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "home").mkdir()
        workspace = base / "ws"
        workspace.mkdir()
        env = {"HOME": str(base / "home"), "OWFA_HOME": str(base / "owfa"),
               "OWFA_HOME_HELPER": helper}
        with patch.dict(os.environ, env, clear=True):
            yield base, workspace


def write_identity(root: Path) -> None:
    page = root / "wiki" / "cuhksz" / "identity.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("---\ntype: cuhksz\n---\nstudent_id: 000000000\n", encoding="utf-8")


class LocatorTests(unittest.TestCase):
    def test_finds_the_package_source_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init = root / "migrations" / "init.py"
            init.parent.mkdir(parents=True)
            init.write_text("", encoding="utf-8")
            probe = root / "connectors" / "pkg" / "tests" / "test_x.py"
            probe.parent.mkdir(parents=True)
            probe.write_text("", encoding="utf-8")
            self.assertEqual(find_migrations_init(probe), init)

    def test_finds_the_installed_domain_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init = root / ".owfa" / "plugins" / "domains" / "cuhksz" / "migrations" / "init.py"
            init.parent.mkdir(parents=True)
            init.write_text("", encoding="utf-8")
            probe = root / "wiki" / "tmp" / "probe.py"
            probe.parent.mkdir(parents=True)
            probe.write_text("", encoding="utf-8")
            self.assertEqual(find_migrations_init(probe), init)

    def test_returns_none_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp) / "a" / "b" / "probe.py"
            probe.parent.mkdir(parents=True)
            probe.write_text("", encoding="utf-8")
            self.assertIsNone(find_migrations_init(probe))


@unittest.skipUnless(INIT_PY is not None,
                     "migrations/init.py not found (neither package source nor installed domain)")
class InitVerifyTests(unittest.TestCase):
    def test_missing_identity_is_an_error(self):
        with isolated("") as (_, workspace):
            issues = load_verify()(SimpleNamespace(root=str(workspace)))
            self.assertIn(
                ("error", "wiki/cuhksz/identity.md missing — create it per the identity constitution (sis block from transcript)"),
                issues)

    def test_identity_page_with_sis_block_passes(self):
        with isolated("") as (_, workspace):
            write_identity(workspace)
            errors = [i for i in load_verify()(SimpleNamespace(root=str(workspace))) if i[0] == "error"]
            self.assertEqual(errors, [])

    def test_no_helper_falls_back_and_writes_nothing(self):
        with isolated("") as (base, workspace):
            (base / "home" / ".bb-cli").mkdir()
            (base / "home" / ".bb-cli" / "config.json").write_text("{}", encoding="utf-8")
            before = {str(p.relative_to(base)): p.read_bytes() for p in base.rglob("*") if p.is_file()}
            issues = load_verify()(SimpleNamespace(root=str(workspace)))
            after = {str(p.relative_to(base)): p.read_bytes() for p in base.rglob("*") if p.is_file()}
            self.assertEqual(before, after)
            self.assertTrue(any("sis" in message for _, message in issues))

    def test_helper_present_checks_the_substrate_components(self):
        if not HELPER.is_file():
            self.skipTest(f"OWFA home helper not found at {HELPER}; set OWFA_HOME_HELPER")
        with isolated(str(HELPER)) as (base, workspace):
            write_identity(workspace)
            issues = load_verify()(SimpleNamespace(root=str(workspace)))
            messages = [m for _, m in issues]
            self.assertTrue(any("cuhksz-cli bb not logged in yet" in m for m in messages))
            self.assertFalse((base / "owfa").exists())


if __name__ == "__main__":
    unittest.main()
