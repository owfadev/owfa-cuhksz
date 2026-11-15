"""Offline regressions: synthetic cookies only; no user config or requests."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from curl_cffi import requests as creq
from siscli import cli, config
from siscli.transport import Transport
from bbcli import cli as bbcli


# Secrets that must never appear in status output. Account labels
# (default_account) are documented as possibly containing a student id —
# see docs/sis.md "Status contract": they are local-machine output only.
FORBIDDEN_SECRETS = ("test-secret", "test-token")


class StatusTests(unittest.TestCase):
    def run_status(self, jar=None, cfg=None, env=None):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.json"
            if jar is not None:
                path.write_text(json.dumps(jar), encoding="utf-8")
            with patch.dict(os.environ, env or {}, clear=True), \
                    patch.object(config, "session_path", return_value=path):
                transport = Transport()
                sis = SimpleNamespace(transport=transport, cfg=cfg or {})
                before = path.read_bytes() if path.exists() else None
                with patch.object(transport._sess, "request", side_effect=AssertionError("network forbidden")), \
                        patch.object(cli, "Sis", return_value=sis), \
                        contextlib.redirect_stdout(io.StringIO()) as output:
                    result = cli.main(["status"])
                self.assertEqual(result, 0)
                self.assertEqual(before, path.read_bytes() if path.exists() else None)
                text = output.getvalue()
                for secret in FORBIDDEN_SECRETS:
                    self.assertNotIn(secret, text)
                data = json.loads(text)
                self.assertIsNone(data["authenticated"])
                self.assertFalse(data["authentication_checked"])
                self.assertIsNone(data["reachable"])
                self.assertFalse(data["network_checked"])
                return data

    def test_missing_session_and_credentials_does_not_exit_or_login(self):
        data = self.run_status()
        self.assertEqual(data["session"], "absent_or_unusable")
        self.assertEqual(data["relogin"], "blocked_missing_credentials")

    def test_cached_token_never_implies_authenticated(self):
        data = self.run_status([{"name": "PS_TOKEN", "value": "test-token"}])
        self.assertEqual(data["session"], "cached_unverified")
        self.assertEqual(data["relogin"], "blocked_missing_credentials")

    def test_stored_credentials_are_not_used_to_login(self):
        data = self.run_status(cfg={"username": "test-user", "password": "test-secret"})
        self.assertEqual(data["relogin"], "credentials_available_unverified")

    def test_environment_credentials_follow_resolver(self):
        data = self.run_status(env={config.ENV_USERNAME: "test-user", config.ENV_PASSWORD: "test-secret"})
        self.assertEqual(data["relogin"], "credentials_available_unverified")

    def test_partial_credentials_block_relogin(self):
        data = self.run_status(cfg={"username": "test-user"})
        self.assertEqual(data["relogin"], "blocked_missing_credentials")

    def test_non_token_jar_is_not_authenticated(self):
        data = self.run_status([{"name": "PS_DEVICEFEATURES", "value": "test-token"}])
        self.assertEqual(data["session"], "absent_or_unusable")

    def test_malformed_cookie_entries_are_reported_without_details(self):
        data = self.run_status([{"value": "test-secret"}])
        self.assertEqual(data["session"], "unreadable")

    def test_unreadable_session_does_not_hide_credential_availability(self):
        with patch.object(Transport, "load_session", side_effect=OSError("test-secret")):
            data = self.run_status(cfg={"username": "test-user", "password": "test-secret"})
        self.assertEqual(data["session"], "unreadable")
        self.assertEqual(data["relogin"], "credentials_available_unverified")

    def test_legacy_config_discloses_default_account_label(self):
        # Documented contract: default_account is a local account label that may
        # equal the student id (legacy configs name the account after the
        # username); passwords/tokens remain the non-disclosure line.
        data = self.run_status(cfg={"username": "test-user", "password": "test-secret"})
        self.assertEqual(data["default_account"], "test-user")
        self.assertEqual(data["accounts"], 1)

    def test_multiple_accounts_without_default_block_with_specific_reason(self):
        cfg = {"accounts": {"a": {"username": "test-user-a", "password": "test-secret"},
                            "b": {"username": "test-user-b", "password": "test-secret"}}}
        data = self.run_status(cfg=cfg)
        self.assertEqual(data["relogin"], "blocked_no_default_account")
        self.assertIsNone(data["default_account"])
        self.assertEqual(data["accounts"], 2)

    def test_multiple_accounts_with_default_can_relogin(self):
        cfg = {"accounts": {"a": {"username": "test-user-a", "password": "test-secret"},
                            "b": {"username": "test-user-b", "password": "test-secret"}},
               "default_account": "b"}
        data = self.run_status(cfg=cfg)
        self.assertEqual(data["relogin"], "credentials_available_unverified")
        self.assertEqual(data["default_account"], "b")

    def test_default_account_without_password_still_blocks(self):
        cfg = {"accounts": {"a": {"username": "test-user"}}, "default_account": "a"}
        data = self.run_status(cfg=cfg)
        self.assertEqual(data["relogin"], "blocked_missing_credentials")


class StatusIntegrationTests(unittest.TestCase):
    """Exercise real Sis construction and config loading in a synthetic home."""

    def run_status(self, config_bytes=None, session_bytes=None, absent_home=False):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "synthetic-home"
            if not absent_home:
                home.mkdir()
            for name, content in (("config.json", config_bytes), ("session.json", session_bytes)):
                if content is not None:
                    (home / name).write_bytes(content)

            def snapshot():
                return {str(p.relative_to(home)): p.read_bytes() for p in home.rglob("*") if p.is_file()}

            before = snapshot()
            with patch.dict(os.environ, {"SIS_CLI_HOME": str(home)}, clear=True), \
                    patch.object(creq.Session, "request", side_effect=AssertionError("network forbidden")) as request, \
                    patch("socket.socket.connect", side_effect=AssertionError("network forbidden")) as connect, \
                    patch.object(cli.Sis, "_relogin", side_effect=AssertionError("login forbidden")) as login, \
                    contextlib.redirect_stdout(io.StringIO()) as output, \
                    contextlib.redirect_stderr(io.StringIO()) as errors:
                result = cli.main(["status"])
            self.assertEqual(result, 0)
            request.assert_not_called()
            connect.assert_not_called()
            login.assert_not_called()
            self.assertEqual(before, snapshot())
            text = output.getvalue() + errors.getvalue()
            for secret in FORBIDDEN_SECRETS:
                self.assertNotIn(secret, text)
            self.assertEqual(errors.getvalue(), "")
            data = json.loads(output.getvalue())
            self.assertIsNone(data["authenticated"])
            self.assertIsNone(data["reachable"])
            self.assertFalse(data["authentication_checked"])
            self.assertFalse(data["network_checked"])
            return data

    def test_non_object_configs_do_not_crash(self):
        for value in (None, [1], "test-secret", 1, True, []):
            with self.subTest(value=value):
                data = self.run_status(config_bytes=json.dumps(value).encode("utf-8"))
                self.assertEqual(data["relogin"], "blocked_missing_credentials")

    def test_invalid_config_json_is_unavailable_without_rewrite(self):
        data = self.run_status(config_bytes=b'{"password": "test-secret"')
        self.assertEqual(data["relogin"], "blocked_missing_credentials")

    def test_session_errors_handled_by_loader_are_absent_or_unusable(self):
        for content in (b"invalid-json", b"\xff", b"[]", b"{}"):
            with self.subTest(content=content):
                data = self.run_status(session_bytes=content)
                self.assertEqual(data["session"], "absent_or_unusable")

    def test_malformed_cookie_entry_is_unreadable(self):
        data = self.run_status(session_bytes=b'[{"value": "test-token"}]')
        self.assertEqual(data["session"], "unreadable")

    def test_cached_session_and_stored_credentials_remain_unchanged(self):
        data = self.run_status(
            config_bytes=b'{"username": "test-user", "password": "test-secret"}',
            session_bytes=b'[{"name": "PS_TOKEN", "value": "test-token"}]')
        self.assertEqual(data["session"], "cached_unverified")
        self.assertEqual(data["relogin"], "credentials_available_unverified")

    def test_missing_home_creates_no_authentication_files(self):
        data = self.run_status(absent_home=True)
        self.assertEqual(data["session"], "absent_or_unusable")
        self.assertEqual(data["relogin"], "blocked_missing_credentials")


class BBStatusTests(unittest.TestCase):
    """bb-cli status tri-state contract (issue #16): offline evidence only —
    session state (cookie jar on disk) vs. capability (stored credentials),
    never triggering network or login."""

    def run_bb_status(self, config_bytes=None, session_bytes=None, env=None, fmt="json"):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "synthetic-home"
            home.mkdir()
            for name, content in (("config.json", config_bytes), ("session.json", session_bytes)):
                if content is not None:
                    (home / name).write_bytes(content)

            def snapshot():
                return {str(p.relative_to(home)): p.read_bytes() for p in home.rglob("*") if p.is_file()}

            before = snapshot()
            environ = {"BB_CLI_HOME": str(home)}
            environ.update(env or {})
            with patch.dict(os.environ, environ, clear=True), \
                    patch.object(creq.Session, "request",
                                 side_effect=AssertionError("network forbidden")) as request, \
                    patch("socket.socket.connect", side_effect=AssertionError("network forbidden")) as connect, \
                    contextlib.redirect_stdout(io.StringIO()) as output, \
                    contextlib.redirect_stderr(io.StringIO()) as errors:
                bbcli.main(["status"] + (["--format", fmt] if fmt != "json" else []))
            request.assert_not_called()
            connect.assert_not_called()
            self.assertEqual(before, snapshot())
            self.assertEqual(errors.getvalue(), "")
            text = output.getvalue()
            for secret in FORBIDDEN_SECRETS:
                self.assertNotIn(secret, text)
            if fmt == "json":
                return json.loads(text)
            return text

    def test_empty_home_reports_blocked_and_absent_session(self):
        data = self.run_bb_status()
        self.assertFalse(data["session_file"])
        self.assertFalse(data["session_valid"])
        self.assertEqual(data["auto_relogin"], "blocked (no stored credentials)")
        self.assertIsNone(data["user"])
        self.assertIsNone(data["default_account"])
        self.assertEqual(data["accounts"], 0)

    def test_stored_session_and_default_account_credentials(self):
        data = self.run_bb_status(
            config_bytes=b'{"accounts": {"a": {"username": "test-user", "password": "test-secret"}},'
                         b' "default_account": "a"}',
            session_bytes=b'[{"name": "s_session_id", "value": "test-token", "domain": "bb.cuhk.edu.cn"}]')
        self.assertTrue(data["session_file"])
        self.assertTrue(data["session_valid"])
        self.assertEqual(data["auto_relogin"], "available")
        self.assertEqual(data["default_account"], "a")
        self.assertEqual(data["accounts"], 1)

    def test_expired_or_absent_session_with_credentials_is_not_a_login_condition(self):
        # The issue #16 false-red: no live session, but credentials on disk mean
        # any real command re-logs in silently — status must say "available".
        data = self.run_bb_status(
            config_bytes=b'{"accounts": {"a": {"username": "test-user", "password": "test-secret"}}}')
        self.assertFalse(data["session_file"])
        self.assertFalse(data["session_valid"])
        self.assertEqual(data["auto_relogin"], "available")

    def test_corrupt_session_file_is_not_valid(self):
        data = self.run_bb_status(session_bytes=b'{"not": "a jar"]')
        self.assertTrue(data["session_file"])
        self.assertFalse(data["session_valid"])

    def test_legacy_flat_config_supports_relogin(self):
        data = self.run_bb_status(config_bytes=b'{"username": "test-user", "password": "test-secret"}')
        self.assertEqual(data["auto_relogin"], "available")
        self.assertEqual(data["default_account"], "test-user")

    def test_env_credentials_count_as_capability(self):
        data = self.run_bb_status(env={"BB_CLI_USERNAME": "test-user", "BB_CLI_PASSWORD": "test-secret"})
        self.assertEqual(data["auto_relogin"], "available")

    def test_multiple_accounts_without_default_block_relogin(self):
        data = self.run_bb_status(
            config_bytes=b'{"accounts": {"a": {"username": "ua", "password": "test-secret"},'
                         b' "b": {"username": "ub", "password": "test-secret"}}}')
        self.assertEqual(data["auto_relogin"], "blocked (no stored credentials)")
        self.assertIsNone(data["default_account"])
        self.assertEqual(data["accounts"], 2)

    def test_text_format_uses_tri_state_and_hint(self):
        text = self.run_bb_status(fmt="text")
        self.assertIn("auto_relogin=blocked (no stored credentials)", text)
        self.assertIn("session_valid=no", text)
        self.assertIn("run `bb-cli login`", text)
        self.assertNotIn("authenticated=", text)

    def test_text_format_no_hint_when_relogin_available(self):
        text = self.run_bb_status(
            config_bytes=b'{"username": "test-user", "password": "test-secret"}', fmt="text")
        self.assertIn("auto_relogin=available", text)
        self.assertNotIn("!!", text)


if __name__ == "__main__":
    unittest.main()
