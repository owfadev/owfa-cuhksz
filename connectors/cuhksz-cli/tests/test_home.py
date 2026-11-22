"""Substrate resolution + migration regressions (offline, temp OWFA_HOME only).

Every test runs with HOME / OWFA_HOME pointed into a TemporaryDirectory, so the
real ~/.bb-cli / ~/.sis-cli are never read for content and never moved. Tests
that need the framework helper skip when no checkout provides one; set
OWFA_HOME_HELPER to point at `.owfa/scripts/owfa_home.py` explicitly.
"""
import contextlib
import io
import json
import os
import shutil
import stat
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bbcli import config as bb_config
from siscli import config as sis_config
from cuhkszcli import cli, home

DEFAULT_HELPER = "~/dev/owfa/.owfa/scripts/owfa_home.py"
HELPER = Path(os.environ.get("OWFA_HOME_HELPER") or DEFAULT_HELPER).expanduser()
HAVE_HELPER = HELPER.is_file()


def require_helper(test):
    if not HAVE_HELPER:
        test.skipTest(f"OWFA home helper not found at {HELPER}; set OWFA_HOME_HELPER")
    return HELPER


@contextlib.contextmanager
def substrate_env(**overrides):
    """Isolated machine: temp HOME + temp OWFA_HOME + the workspace helper."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "home").mkdir()
        workspace = base / "ws"
        workspace.mkdir()
        env = {
            "HOME": str(base / "home"),
            "OWFA_HOME": str(base / "owfa"),
            "OWFA_HOME_HELPER": str(HELPER),
        }
        env.update(overrides)
        with patch.dict(os.environ, env, clear=True):
            home._notified.clear()
            try:
                yield base, workspace
            finally:
                home._notified.clear()


def snapshot(root: Path):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


class ResolutionTests(unittest.TestCase):
    def test_explicit_override_wins_over_substrate(self):
        require_helper(self)
        with substrate_env() as (base, _):
            explicit = base / "explicit-bb"
            with patch.dict(os.environ, {"BB_CLI_HOME": str(explicit)}), \
                    contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(bb_config.bb_home(), explicit)
                self.assertTrue(explicit.is_dir())
                # no substrate component was created on bb's behalf
                self.assertFalse((base / "owfa" / "connectors" / "cuhksz-cli" / "homes").exists())
                self.assertEqual(bb_config.bb_home(), explicit)  # explicit override never notifies
            self.assertEqual(errors.getvalue(), "")

    def test_components_live_under_the_single_connector_home(self):
        require_helper(self)
        with substrate_env() as (base, _):
            expected = base / "owfa" / "connectors" / "cuhksz-cli" / "homes" / "default"
            self.assertEqual(bb_config.bb_home(), expected / "bb")
            self.assertEqual(sis_config.sis_home(), expected / "sis")
            self.assertTrue((expected / "bb").is_dir())
            self.assertEqual(stat.S_IMODE((expected / "bb").stat().st_mode), 0o700)

    def test_binding_id_selects_the_home(self):
        helper = require_helper(self)
        import importlib.util
        spec = importlib.util.spec_from_file_location("owfa_home_test_bind", helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with substrate_env() as (base, workspace):
            module.bind(home.CONNECTOR, str(workspace), "lab-9f3a")
            self.assertEqual(
                bb_config.bb_home(),
                base / "owfa" / "connectors" / "cuhksz-cli" / "homes" / "lab-9f3a" / "bb")

    def test_legacy_fallback_is_loud_and_one_line(self):
        with substrate_env() as (base, _):
            with patch.object(home, "load_owfa_home", return_value=None), \
                    contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(bb_config.bb_home(), base / "home" / ".bb-cli")
                self.assertTrue((base / "home" / ".bb-cli").is_dir())
                bb_config.bb_home()  # second call: no repeated notice
            lines = [ln for ln in errors.getvalue().splitlines() if ln.strip()]
            self.assertEqual(len(lines), 1)
            self.assertIn("no OWFA home helper", lines[0])
            self.assertIn("cuhksz-cli home migrate", lines[0])

    def test_missing_helper_never_silently_creates_a_second_home(self):
        with substrate_env() as (base, _):
            with patch.object(home, "load_owfa_home", return_value=None), \
                    contextlib.redirect_stderr(io.StringIO()):
                sis_config.sis_home()
            self.assertFalse((base / "owfa").exists())


class StatusTests(unittest.TestCase):
    def test_status_writes_nothing(self):
        require_helper(self)
        with substrate_env() as (base, _):
            before = snapshot(base)
            data = home.status()
            self.assertEqual(snapshot(base), before)
            self.assertFalse((base / "owfa").exists())
            self.assertEqual(data["connector"], "cuhksz-cli")
            self.assertEqual(data["components"]["bb"]["source"], "substrate")
            self.assertIsNotNone(data["substrate"])
            self.assertFalse(data["components"]["bb"]["exists"])

    def test_status_reports_legacy_source_without_helper(self):
        with substrate_env() as (base, _):
            (base / "home" / ".bb-cli").mkdir()
            with patch.object(home, "load_owfa_home", return_value=None), \
                    contextlib.redirect_stderr(io.StringIO()):
                data = home.status()
            self.assertEqual(data["components"]["bb"]["source"], "legacy")
            self.assertTrue(data["components"]["bb"]["legacy_present"])
            self.assertIsNone(data["helper"])

    def test_cli_status_json(self):
        require_helper(self)
        with substrate_env() as (base, _), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.main(["home", "status"]), 0)
        data = json.loads(output.getvalue())
        self.assertEqual(data["components"]["sis"]["source"], "substrate")


class MigrationTests(unittest.TestCase):
    def make_legacy(self, base: Path):
        bb = base / "home" / ".bb-cli"
        sis = base / "home" / ".sis-cli"
        bb.mkdir()
        sis.mkdir()
        (bb / "config.json").write_text('{"accounts": {}}', encoding="utf-8")
        (sis / "session.json").write_text("[]", encoding="utf-8")
        return bb, sis

    def test_dry_run_moves_and_binds_nothing(self):
        require_helper(self)
        with substrate_env() as (base, workspace):
            bb, sis = self.make_legacy(base)
            before = snapshot(base)
            data = home.migrate(dry_run=True, root=str(workspace))
            self.assertEqual(snapshot(base), before)
            self.assertEqual(data["components"]["bb"]["action"], "would-migrate")
            self.assertEqual(data["components"]["sis"]["action"], "would-migrate")
            self.assertEqual(
                Path(data["components"]["bb"]["target"]),
                base / "owfa" / "connectors" / "cuhksz-cli" / "homes" / "default" / "bb")
            self.assertFalse((base / "owfa" / "connectors" / "cuhksz-cli" / "bindings.json").exists())
            # dry run leaves the legacy directories exactly as they were
            self.assertTrue((bb / "config.json").is_file())
            self.assertFalse(bb.is_symlink())

    def test_real_migrate_moves_and_links(self):
        require_helper(self)
        with substrate_env() as (base, workspace):
            bb, sis = self.make_legacy(base)
            data = home.migrate(root=str(workspace))
            target_bb = base / "owfa" / "connectors" / "cuhksz-cli" / "homes" / "default" / "bb"
            target_sis = base / "owfa" / "connectors" / "cuhksz-cli" / "homes" / "default" / "sis"
            self.assertEqual(data["components"]["bb"]["action"], "migrated")
            self.assertEqual(data["components"]["sis"]["action"], "migrated")
            self.assertEqual((target_bb / "config.json").read_text(encoding="utf-8"), '{"accounts": {}}')
            self.assertEqual((target_sis / "session.json").read_text(encoding="utf-8"), "[]")
            self.assertTrue(bb.is_symlink())
            self.assertEqual(bb.resolve(), target_bb.resolve())
            self.assertTrue(sis.is_symlink())
            bindings = json.loads(
                (base / "owfa" / "connectors" / "cuhksz-cli" / "bindings.json").read_text(encoding="utf-8"))
            self.assertEqual(bindings["bindings"][0]["root"], str(workspace.resolve()))

    def test_migrate_reuses_an_existing_binding_id(self):
        helper = require_helper(self)
        import importlib.util
        spec = importlib.util.spec_from_file_location("owfa_home_test_migrate", helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with substrate_env() as (base, workspace):
            module.bind(home.CONNECTOR, str(workspace), "lab-9f3a")
            self.make_legacy(base)
            data = home.migrate(root=str(workspace))
            self.assertEqual(data["components"]["bb"]["binding_id"], "lab-9f3a")
            self.assertEqual(
                Path(data["components"]["bb"]["target"]),
                base / "owfa" / "connectors" / "cuhksz-cli" / "homes" / "lab-9f3a" / "bb")

    def test_existing_symlink_is_already_migrated(self):
        require_helper(self)
        with substrate_env() as (base, workspace):
            bb, _ = self.make_legacy(base)
            target = base / "owfa" / "connectors" / "cuhksz-cli" / "homes" / "default" / "bb"
            target.mkdir(parents=True)
            shutil.rmtree(bb)
            bb.symlink_to(target, target_is_directory=True)
            data = home.migrate(dry_run=True, root=str(workspace))
            self.assertEqual(data["components"]["bb"]["action"], "already-migrated")

    def test_missing_legacy_is_a_noop(self):
        require_helper(self)
        with substrate_env() as (base, workspace):
            data = home.migrate(root=str(workspace))
            self.assertEqual(data["components"]["bb"]["action"], "nothing-to-migrate")
            self.assertFalse((base / "home" / ".bb-cli").exists())

    def test_non_empty_target_is_refused(self):
        require_helper(self)
        with substrate_env() as (base, workspace):
            self.make_legacy(base)
            target = base / "owfa" / "connectors" / "cuhksz-cli" / "homes" / "default" / "bb"
            target.mkdir(parents=True)
            (target / "config.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(SystemExit) as raised, \
                    contextlib.redirect_stdout(io.StringIO()):
                home.migrate(root=str(workspace))
            self.assertIn("refusing to migrate", str(raised.exception))

    def test_migrate_requires_the_helper(self):
        with substrate_env() as (base, workspace):
            self.make_legacy(base)
            with patch.object(home, "load_owfa_home", return_value=None), \
                    self.assertRaises(SystemExit) as raised:
                home.migrate(root=str(workspace))
            self.assertIn("OWFA_HOME_HELPER", str(raised.exception))

    def test_cli_migrate_dry_run(self):
        require_helper(self)
        with substrate_env() as (base, workspace), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            bb, _ = self.make_legacy(base)
            self.assertEqual(cli.main(["home", "migrate", "--dry-run", "--root", str(workspace)]), 0)
            self.assertTrue((bb / "config.json").is_file())
            self.assertFalse(bb.is_symlink())
        data = json.loads(output.getvalue())
        self.assertTrue(data["dry_run"])
        self.assertEqual(data["components"]["bb"]["action"], "would-migrate")


if __name__ == "__main__":
    unittest.main()
