"""Substrate resolution + migration regressions (offline, temp OWFA_HOME only).

Every test runs with HOME / OWFA_HOME pointed into a TemporaryDirectory, so the
real ~/.bb-cli / ~/.sis-cli are never read for content and never moved. Tests
that need the framework helper skip when no checkout provides one; set
OWFA_HOME_HELPER to point at `.owfa/scripts/owfa_home.py` explicitly. The
integration test at the bottom exercises the primary discovery path (walk-up
from an installed-like tree, no OWFA_HOME_HELPER).
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bbcli import config as bb_config
from siscli import config as sis_config
from cuhkszcli import cli, home

PKG_DIR = Path(__file__).resolve().parents[1]
DEFAULT_HELPER = "~/dev/owfa/.owfa/scripts/owfa_home.py"
HELPER = Path(os.environ.get("OWFA_HOME_HELPER") or DEFAULT_HELPER).expanduser()
HAVE_HELPER = HELPER.is_file()


def require_helper(test):
    if not HAVE_HELPER:
        test.skipTest(f"OWFA home helper not found at {HELPER}; set OWFA_HOME_HELPER")
    return HELPER


def load_helper_module(path: Path = HELPER):
    spec = importlib.util.spec_from_file_location(f"owfa_home_test_{id(path)}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def substrate_home(base: Path, binding: str = "default") -> Path:
    return base / "owfa" / "connectors" / "cuhksz-cli" / "homes" / binding


def bindings_file(base: Path) -> Path:
    return base / "owfa" / "connectors" / "cuhksz-cli" / "bindings.json"


def write_legacy(base: Path, components=("bb", "sis")) -> dict:
    paths = {}
    for component, name in (("bb", ".bb-cli"), ("sis", ".sis-cli")):
        path = base / "home" / name
        if component in components:
            path.mkdir(parents=True)
            (path / "config.json").write_text('{"accounts": {"a": {"username": "u", "password": "p"}},'
                                              ' "default_account": "a"}', encoding="utf-8")
        paths[component] = path
    return paths


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
            expected = substrate_home(base)
            self.assertEqual(bb_config.bb_home(), expected / "bb")
            self.assertEqual(sis_config.sis_home(), expected / "sis")
            self.assertTrue((expected / "bb").is_dir())
            self.assertEqual(stat.S_IMODE((expected / "bb").stat().st_mode), 0o700)

    def test_binding_id_selects_the_home(self):
        helper = require_helper(self)
        module = load_helper_module(helper)
        with substrate_env() as (base, workspace):
            module.bind(home.CONNECTOR, str(workspace), "lab-9f3a")
            self.assertEqual(bb_config.bb_home(), substrate_home(base, "lab-9f3a") / "bb")

    def test_legacy_fallback_is_loud_and_one_line(self):
        with substrate_env() as (base, _):
            with patch.object(home, "load_owfa_home", return_value=None), \
                    patch.object(home, "helper_path", return_value=None), \
                    contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(bb_config.bb_home(), base / "home" / ".bb-cli")
                self.assertTrue((base / "home" / ".bb-cli").is_dir())
                bb_config.bb_home()  # second call: no repeated notice
            lines = [ln for ln in errors.getvalue().splitlines() if ln.strip()]
            self.assertEqual(len(lines), 1)
            self.assertIn("not found", lines[0])
            self.assertIn("cuhksz-cli home migrate", lines[0])

    def test_missing_helper_never_silently_creates_a_second_home(self):
        with substrate_env() as (base, _):
            with patch.object(home, "load_owfa_home", return_value=None), \
                    patch.object(home, "helper_path", return_value=None), \
                    contextlib.redirect_stderr(io.StringIO()):
                sis_config.sis_home()
            self.assertFalse((base / "owfa").exists())

    def test_unmigrated_legacy_state_wins_over_an_empty_substrate(self):
        """BLOCKING 3: a helper alone must not strand the old credentials behind a new empty home."""
        require_helper(self)
        with substrate_env() as (base, _):
            write_legacy(base, ("bb",))
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(bb_config.bb_home(), base / "home" / ".bb-cli")
                self.assertEqual(sis_config.sis_home(), substrate_home(base) / "sis")  # no legacy sis
            self.assertFalse((substrate_home(base) / "bb").exists())  # never create the empty target
            text = errors.getvalue()
            self.assertIn("never migrate silently", text)
            self.assertIn("home migrate --dry-run", text)
            self.assertIn("cuhksz-cli home migrate", text)

    def test_bb_status_reads_legacy_state_and_does_not_create_the_substrate(self):
        """The reviewer's repro: `bb status` on an unmigrated machine must not look empty."""
        require_helper(self)
        with substrate_env() as (base, _):
            write_legacy(base, ("bb",))
            with contextlib.redirect_stdout(io.StringIO()) as output, \
                    contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(cli.main(["bb", "status"]), 0)
            data = json.loads(output.getvalue())
            self.assertEqual(data["auto_relogin"], "available")  # read the legacy credentials
            self.assertFalse((substrate_home(base) / "bb").exists())
            self.assertFalse(bindings_file(base).exists())
            self.assertIn("home migrate", errors.getvalue())

    def test_both_homes_hold_state_uses_the_substrate_and_reports_the_leftover(self):
        require_helper(self)
        with substrate_env() as (base, _):
            write_legacy(base, ("bb",))
            (substrate_home(base) / "bb").mkdir(parents=True)
            (substrate_home(base) / "bb" / "config.json").write_text("{}", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(bb_config.bb_home(), substrate_home(base) / "bb")
            self.assertIn("leftover", errors.getvalue())


class HelperAbiTests(unittest.TestCase):
    def _old_helper(self, base: Path) -> Path:
        path = base / "old-owfa_home.py"
        path.write_text(
            "def resolve_home(connector, explicit_root='', explicit_home=''):\n"
            "    raise AssertionError('must not be called')\n",
            encoding="utf-8")
        return path

    def test_old_helper_falls_back_loudly_instead_of_crashing(self):
        with substrate_env() as (base, _):
            old = self._old_helper(base)
            (base / "home" / ".bb-cli").mkdir()
            with patch.dict(os.environ, {"OWFA_HOME_HELPER": str(old)}), \
                    contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(bb_config.bb_home(), base / "home" / ".bb-cli")
            self.assertIn("predates the 0.5.2 ABI", errors.getvalue())

    def test_old_helper_migrate_gives_a_friendly_error(self):
        with substrate_env() as (base, workspace):
            old = self._old_helper(base)
            with patch.dict(os.environ, {"OWFA_HOME_HELPER": str(old)}), \
                    contextlib.redirect_stdout(io.StringIO()) as output, \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["home", "migrate", "--root", str(workspace)]), 1)
            data = json.loads(output.getvalue())
            self.assertFalse(data["ok"])
            self.assertIn("0.5.2", data["error"])
            self.assertNotIn("AttributeError", data["error"])


class StatusTests(unittest.TestCase):
    def test_status_writes_nothing(self):
        require_helper(self)
        with substrate_env() as (base, _):
            before = {str(p.relative_to(base)): p.read_bytes() for p in base.rglob("*") if p.is_file()}
            data = home.status()
            after = {str(p.relative_to(base)): p.read_bytes() for p in base.rglob("*") if p.is_file()}
            self.assertEqual(after, before)
            self.assertFalse((base / "owfa").exists())
            self.assertTrue(data["ok"])
            self.assertEqual(data["connector"], "cuhksz-cli")
            self.assertEqual(data["components"]["bb"]["source"], "substrate")
            self.assertIsNotNone(data["substrate"])
            self.assertFalse(data["components"]["bb"]["substrate_exists"])

    def test_status_reports_legacy_source_without_helper(self):
        with substrate_env() as (base, _):
            write_legacy(base, ("bb",))
            with patch.object(home, "load_owfa_home", return_value=None), \
                    patch.object(home, "helper_path", return_value=None), \
                    contextlib.redirect_stderr(io.StringIO()):
                data = home.status()
            self.assertEqual(data["components"]["bb"]["source"], "legacy")
            self.assertTrue(data["components"]["bb"]["legacy_has_state"])
            self.assertFalse(data["migration"]["helper_available"])
            self.assertIsNone(data["helper"])

    def test_status_reports_unmigrated_legacy_state_as_legacy(self):
        require_helper(self)
        with substrate_env() as (base, _):
            write_legacy(base, ("sis",))
            with contextlib.redirect_stderr(io.StringIO()):
                data = home.status()
            self.assertEqual(data["components"]["sis"]["source"], "legacy")
            self.assertEqual(Path(data["components"]["sis"]["state_dir"]), base / "home" / ".sis-cli")
            self.assertTrue(data["components"]["sis"]["substrate_home"].endswith("/sis"))

    def test_cli_status_json(self):
        require_helper(self)
        with substrate_env() as (base, _), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.main(["home", "status"]), 0)
        data = json.loads(output.getvalue())
        self.assertEqual(data["components"]["sis"]["source"], "substrate")


class MigrationTests(unittest.TestCase):
    def test_dry_run_moves_and_binds_nothing(self):
        require_helper(self)
        with substrate_env() as (base, workspace):
            legacy = write_legacy(base)
            before = {str(p.relative_to(base)): p.read_bytes() for p in base.rglob("*") if p.is_file()}
            data = home.migrate(dry_run=True, root=str(workspace))
            after = {str(p.relative_to(base)): p.read_bytes() for p in base.rglob("*") if p.is_file()}
            self.assertEqual(after, before)
            self.assertTrue(data["ok"])
            self.assertTrue(data["dry_run"])
            actions = {row["component"]: row for row in data["components"]}
            self.assertEqual(actions["bb"]["action"], "would-migrate")
            self.assertEqual(actions["sis"]["action"], "would-migrate")
            self.assertEqual(Path(actions["bb"]["target"]), substrate_home(base) / "bb")
            self.assertFalse(bindings_file(base).exists())
            # dry run leaves the legacy directories exactly as they were
            self.assertTrue((legacy["bb"] / "config.json").is_file())
            self.assertFalse(legacy["bb"].is_symlink())

    def test_real_migrate_moves_and_links(self):
        require_helper(self)
        with substrate_env() as (base, workspace):
            legacy = write_legacy(base)
            data = home.migrate(root=str(workspace))
            self.assertTrue(data["ok"])
            self.assertEqual(sorted(data["migrated"]), ["bb", "sis"])
            self.assertTrue((substrate_home(base) / "bb" / "config.json").is_file())
            self.assertTrue((substrate_home(base) / "sis" / "config.json").is_file())
            self.assertTrue(legacy["bb"].is_symlink())
            self.assertEqual(legacy["bb"].resolve(), (substrate_home(base) / "bb").resolve())
            self.assertTrue(legacy["sis"].is_symlink())
            bindings = json.loads(bindings_file(base).read_text(encoding="utf-8"))["bindings"]
            self.assertEqual(bindings[0]["root"], str(workspace.resolve()))

    def test_migrate_reuses_an_existing_binding_id(self):
        helper = require_helper(self)
        module = load_helper_module(helper)
        with substrate_env() as (base, workspace):
            module.bind(home.CONNECTOR, str(workspace), "lab-9f3a")
            write_legacy(base)
            data = home.migrate(root=str(workspace))
            actions = {row["component"]: row for row in data["components"]}
            self.assertEqual(actions["bb"]["binding_id"], "lab-9f3a")
            self.assertEqual(Path(actions["bb"]["target"]), substrate_home(base, "lab-9f3a") / "bb")

    def test_existing_symlink_is_already_migrated(self):
        require_helper(self)
        with substrate_env() as (base, workspace):
            legacy = write_legacy(base, ("bb",))
            target = substrate_home(base) / "bb"
            target.mkdir(parents=True)
            shutil.rmtree(legacy["bb"])
            legacy["bb"].symlink_to(target, target_is_directory=True)
            data = home.migrate(dry_run=True, root=str(workspace))
            actions = {row["component"]: row for row in data["components"]}
            self.assertEqual(actions["bb"]["action"], "already-migrated")
            self.assertEqual(actions["sis"]["action"], "nothing-to-migrate")

    def test_missing_legacy_is_a_structured_noop_error(self):
        require_helper(self)
        with substrate_env() as (base, workspace), \
                contextlib.redirect_stdout(io.StringIO()) as output, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["home", "migrate", "--root", str(workspace)]), 1)
        data = json.loads(output.getvalue())
        self.assertFalse(data["ok"])
        self.assertEqual(data["reason"], "nothing-to-migrate")
        self.assertFalse((base / "home" / ".bb-cli").exists())

    def test_override_refuses_the_whole_migration(self):
        """BLOCKING 1: a pinned component means its legacy dir is not the live state."""
        require_helper(self)
        for env_name, component in (("BB_CLI_HOME", "bb"), ("SIS_CLI_HOME", "sis")):
            with self.subTest(env=env_name):
                with substrate_env() as (base, workspace):
                    legacy = write_legacy(base)
                    pinned = base / "pinned"
                    with patch.dict(os.environ, {env_name: str(pinned)}), \
                            contextlib.redirect_stdout(io.StringIO()) as output, \
                            contextlib.redirect_stderr(io.StringIO()):
                        self.assertEqual(cli.main(["home", "migrate", "--root", str(workspace)]), 1)
                    data = json.loads(output.getvalue())
                    self.assertFalse(data["ok"])
                    refusals = data["refusals"]
                    self.assertEqual(len(refusals), 1)
                    self.assertEqual(refusals[0]["reason"], "env-override")
                    self.assertEqual(refusals[0]["component"], component)
                    self.assertEqual(refusals[0]["env"], env_name)
                    # nothing moved and no binding was registered
                    self.assertFalse(legacy["bb"].is_symlink())
                    self.assertFalse(legacy["sis"].is_symlink())
                    self.assertFalse(bindings_file(base).exists())
                    self.assertFalse((substrate_home(base) / "bb").exists())
                    self.assertFalse((substrate_home(base) / "sis").exists())

    def test_non_empty_component_target_aborts_before_anything_moves(self):
        """BLOCKING 2: sis non-empty must not leave bb already moved."""
        require_helper(self)
        with substrate_env() as (base, workspace):
            legacy = write_legacy(base)
            (substrate_home(base) / "sis").mkdir(parents=True)
            (substrate_home(base) / "sis" / "keepme").write_text("x", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as output, \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["home", "migrate", "--root", str(workspace)]), 1)
            data = json.loads(output.getvalue())
            self.assertFalse(data["ok"])
            self.assertEqual([r["component"] for r in data["refusals"]], ["sis"])
            self.assertEqual(data["refusals"][0]["reason"], "target-not-empty")
            # bb was NOT moved, bound or created
            self.assertFalse(legacy["bb"].is_symlink())
            self.assertTrue((legacy["bb"] / "config.json").is_file())
            self.assertFalse((substrate_home(base) / "bb").exists())
            self.assertFalse(bindings_file(base).exists())

    def test_midway_move_failure_reports_what_moved(self):
        """A real move failing after bb must report precisely and stop."""
        helper = require_helper(self)
        module = load_helper_module(helper)
        with substrate_env() as (base, workspace):
            legacy = write_legacy(base)
            fake = SimpleNamespace(**{name: getattr(module, name) for name in home._REQUIRED_HELPER})

            def migrate_legacy_home(connector, legacy_dir, binding_id="", root="", component=""):
                if component == "sis":
                    raise OSError("disk full")
                return module.migrate_legacy_home(connector, legacy_dir, binding_id, root, component)

            fake.migrate_legacy_home = migrate_legacy_home
            with patch.object(home, "_helper", return_value=fake), \
                    contextlib.redirect_stdout(io.StringIO()) as output, \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["home", "migrate", "--root", str(workspace)]), 1)
            data = json.loads(output.getvalue())
            self.assertFalse(data["ok"])
            self.assertEqual(data["moved"], ["bb"])
            self.assertEqual(data["not_moved"], ["sis"])
            self.assertEqual(data["failed"]["component"], "sis")
            self.assertTrue(legacy["bb"].is_symlink())
            self.assertTrue((legacy["sis"] / "config.json").is_file())
            self.assertFalse(legacy["sis"].is_symlink())
            self.assertFalse((substrate_home(base) / "sis").exists())  # not registered, not moved

    def test_migrate_requires_the_helper(self):
        with substrate_env() as (base, workspace):
            write_legacy(base)
            with patch.object(home, "load_owfa_home", return_value=None), \
                    patch.object(home, "helper_path", return_value=None), \
                    contextlib.redirect_stdout(io.StringIO()) as output, \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["home", "migrate", "--root", str(workspace)]), 1)
            data = json.loads(output.getvalue())
            self.assertFalse(data["ok"])
            self.assertIn("OWFA_HOME_HELPER", data["error"])

    def test_cli_migrate_dry_run(self):
        require_helper(self)
        with substrate_env() as (base, workspace), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            legacy = write_legacy(base)
            self.assertEqual(cli.main(["home", "migrate", "--dry-run", "--root", str(workspace)]), 0)
            self.assertTrue((legacy["bb"] / "config.json").is_file())
            self.assertFalse(legacy["bb"].is_symlink())
        data = json.loads(output.getvalue())
        self.assertTrue(data["dry_run"])
        actions = {row["component"]: row["action"] for row in data["components"]}
        self.assertEqual(actions, {"bb": "would-migrate", "sis": "would-migrate"})


class InstalledLikeTreeTests(unittest.TestCase):
    """PRIMARY discovery path: walk-up from an installed-like tree, no OWFA_HOME_HELPER."""

    def test_walkup_discovery_and_dry_run_from_an_outside_cwd(self):
        require_helper(self)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            workspace = base / "ws"
            pkg = workspace / "connectors" / "cuhksz-cli"
            ignore = shutil.ignore_patterns(".venv", "__pycache__", "*.egg-info", "build", "dist")
            shutil.copytree(PKG_DIR, pkg, ignore=ignore)
            planted = workspace / ".owfa" / "scripts" / "owfa_home.py"
            planted.parent.mkdir(parents=True)
            shutil.copyfile(HELPER, planted)
            home_dir = base / "home"
            home_dir.mkdir()
            work = base / "work"
            work.mkdir()
            legacy = home_dir / ".bb-cli"
            legacy.mkdir()
            (legacy / "config.json").write_text("{}", encoding="utf-8")
            env = {k: v for k, v in os.environ.items()
                   if k not in ("OWFA_HOME", "OWFA_HOME_HELPER", "OWFA_ROOT",
                                "BB_CLI_HOME", "SIS_CLI_HOME", "PYTHONPATH")}
            env.update({"HOME": str(home_dir), "OWFA_HOME": str(base / "owfa"),
                        "PYTHONPATH": str(pkg)})

            def run(*args):
                return subprocess.run([sys.executable, "-m", "cuhkszcli", *args],
                                      cwd=str(work), env=env, capture_output=True,
                                      text=True, timeout=60)

            status = run("home", "status")
            self.assertEqual(status.returncode, 0, status.stderr)
            data = json.loads(status.stdout)
            self.assertEqual(Path(data["helper"]), planted)
            self.assertEqual(data["helper_abi"], "0.5.2")
            self.assertEqual(data["components"]["bb"]["source"], "legacy")  # legacy still holds state
            self.assertIn("never migrate silently", status.stderr)

            dry = run("home", "migrate", "--dry-run")
            self.assertEqual(dry.returncode, 0, dry.stderr)
            plan = json.loads(dry.stdout)
            self.assertTrue(plan["dry_run"])
            self.assertEqual(Path(plan["components"][0]["target"]),
                             base / "owfa" / "connectors" / "cuhksz-cli" / "homes" / "default" / "bb")
            self.assertFalse(legacy.is_symlink())
            self.assertFalse((base / "owfa").exists())

            real = run("home", "migrate")
            self.assertEqual(real.returncode, 0, real.stderr)
            out = json.loads(real.stdout)
            self.assertTrue(out["ok"])
            self.assertTrue(legacy.is_symlink())
            self.assertTrue((base / "owfa" / "connectors" / "cuhksz-cli" / "homes"
                             / "default" / "bb" / "config.json").is_file())


if __name__ == "__main__":
    unittest.main()
