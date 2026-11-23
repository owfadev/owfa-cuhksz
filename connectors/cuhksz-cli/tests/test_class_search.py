"""Offline regressions for the read-only SIS Class Search (`cuhksz-cli sis search`).

No network, no user config: the fabricated term page / CDATA payload mirror the
live shapes verified on 2026-11-23, and a fake transport stands in for the
PeopleSoft session.
"""
import contextlib
import io
import json
import unittest
from unittest.mock import patch

from siscli import cli, config, parser
from siscli.api import Sis
from siscli.transport import TransportError, extract_win0_form

# A synthetic win0 form: a checked open-only box, an unchecked box, hidden
# state, a selected term option and a submit control (which must be skipped).
TERM_PAGE = """<!DOCTYPE html><html><body>
<form name="win0" action="/psc/csprd/EMPLOYEE/HRMS/c/SA_LEARNER_SERVICES.CLASS_SEARCH.GBL">
  <input type="hidden" name="ICStateNum" value="3">
  <input type="hidden" name="ICSID" value="synthetic-page-sid">
  <input type="checkbox" name="SSR_CLSRCH_WRK_SSR_OPEN_ONLY$chk$3" value="Y" checked>
  <input type="checkbox" name="UNCHECKED$chk$9" value="Y">
  <input type="hidden" name="ICSID" value="page-sid">
  <input type="hidden" name="ICStateNum" value="217">
  <input type="text" name="SSR_CLSRCH_WRK_SUBJECT$0" value="">
  <input type="submit" name="SSR_CLSRCH_WRK2_SSR_PB_CLASS_SRCH" value="Search">
  <select name="CLASS_SRCH_WRK2_STRM$35$">
    <option value="">Select Term</option>
    <option value="2610">2026-27 Term 1</option>
    <option value="2620" selected>2026-27 Term 2</option>
  </select>
</form></body></html>"""

# Step 1 answers with the state step 2 must copy back. A live response is an
# XML/JS page with no <input> tags: the state arrives as JS assignments and
# ICSID is normally not echoed (verified live 2026-11-23).
STEP1_RESPONSE = """<?xml version='1.0' encoding='utf-8' ?>
<PAGE id='SSR_CLSRCH_ENTRY'><GENSCRIPT id='script'><![CDATA[var oWin=window;
var oDoc = window.document;
oDoc.win0.ICStateNum.value=218;
oDoc.win0.ICResubmit.value='0';
]]></GENSCRIPT></PAGE>"""

# Full live-shaped dropdown: placeholders run far into the future.
FULL_TERM_PAGE = "<html><body><form name='win0'><select name='CLASS_SRCH_WRK2_STRM$35$'>" + "".join(
    f'<option value="{y % 100:02d}10">{y}-{str(y+1)[-2:]} Term 1</option>'
    f'<option value="{y % 100:02d}20">{y}-{str(y+1)[-2:]} Term 2</option>'
    for y in range(2014, 2036)) + "</select></form></body></html>"

# Two CDATA blocks: the parser must concatenate them before reading the HTML.
RESULT_PAYLOAD = (
    "<?xml version='1.0'?><PAGE id='SSR_CLSRCH_RSLT'><![CDATA["
    "<div id='win0divDERIVED_CLSRCH_DESCR200$0'>AIE 1904 - AI Exploration IV</div>"
    "<div id='DERIVED_CLSRCH_SSR_CLASSNAME_LONG$0'>L01-LEC(2278)</div>"
    "<div id='MTG_DAYTIME$0'>MoWe 10:00AM - 11:15AM</div>"
    "<div id='MTG_ROOM$0'>Room 101</div>"
    "<div id='MTG_INSTR$0'>Prof A</div>"
    "<div id='MTG_DAYTIME$1'>Fr 10:00AM - 10:50AM</div>"
    "<div id='MTG_ROOM$1'>Room 202</div>"
    "]]><![CDATA["
    "<div id='win0divDERIVED_CLSRCH_DESCR200$1'>CSC 3200 - Algorithms</div>"
    "<div id='DERIVED_CLSRCH_SSR_CLASSNAME_LONG$1'>L01-LEC(3001)</div>"
    "<div id='MTG_DAYTIME$2'>TuTh 2:00PM - 3:15PM</div>"
    "<div id='MTG_ROOM$2'>Room 303</div>"
    "<div id='MTG_INSTR$2'>Prof B</div>"
    "<div id='DERIVED_CLSRCH_SSR_CLASSNAME_LONG$2'>S01-SUP(2549)</div>"
    "]]></PAGE>"
)

WARNING_PAYLOAD = (
    "<?xml version='1.0'?><PAGE id='SSR_SS_WARNING'>"
    "Your search will return over 50 classes. Please narrow your search.</PAGE>"
)

FORBIDDEN_SECRETS = ("test-secret", "test-token")


class FakeTransport:
    """Stands in for the PeopleSoft session: one GET, then two AJAX POSTs."""

    def __init__(self, page=TERM_PAGE, step1=STEP1_RESPONSE, payload=RESULT_PAYLOAD):
        self.page = page
        self.step1 = step1
        self.payload = payload
        self.gets = []
        self.posts = []

    def get_content(self, comp, nav):
        self.gets.append((comp, nav))
        return self.page

    def post_ajax(self, action_url, fields, timeout=None):
        self.posts.append((action_url, dict(fields), timeout))
        return self.step1 if len(self.posts) == 1 else self.payload


def make_sis(transport, cfg=None):
    sis = Sis.__new__(Sis)
    sis.cfg = cfg or {}
    sis.transport = transport
    sis.ensure_session = lambda: True  # never touch credentials/network in tests
    return sis


class ParserTests(unittest.TestCase):
    def test_class_search_terms_parses_the_term_select(self):
        self.assertEqual(parser.class_search_terms(TERM_PAGE), [
            {"strm": "2610", "label": "2026-27 Term 1"},
            {"strm": "2620", "label": "2026-27 Term 2"},
        ])
        self.assertEqual(parser.class_search_terms("<html><body>no form</body></html>"), [])

    def test_parse_class_search_extracts_courses_sections_and_meeting_times(self):
        data = parser.parse_class_search(RESULT_PAYLOAD)
        self.assertNotIn("notice", data)
        self.assertEqual(len(data["courses"]), 2)

        first, second = data["courses"]
        self.assertEqual(first["course"], "AIE 1904 - AI Exploration IV")
        self.assertEqual(len(first["sections"]), 1)
        section = first["sections"][0]
        self.assertEqual(section["section"], "L01-LEC(2278)")
        self.assertEqual(section["times"], ["MoWe 10:00AM - 11:15AM", "Fr 10:00AM - 10:50AM"])
        self.assertEqual(section["room"], "Room 101")  # the first meeting row wins
        self.assertEqual(section["instructor"], "Prof A")

        self.assertEqual(second["course"], "CSC 3200 - Algorithms")
        self.assertEqual([s["section"] for s in second["sections"]],
                         ["L01-LEC(3001)", "S01-SUP(2549)"])
        self.assertEqual(second["sections"][0]["times"], ["TuTh 2:00PM - 3:15PM"])
        self.assertEqual(second["sections"][1]["times"], [])  # SUP has no fixed meeting

    def test_over_50_warning_becomes_a_notice_without_courses(self):
        data = parser.parse_class_search(WARNING_PAYLOAD)
        self.assertEqual(data["courses"], [])
        self.assertIn("more than", data["notice"])
        self.assertIn("--catalog", data["notice"])


    def test_ic_state_fields_reads_the_live_js_shape(self):
        self.assertEqual(parser.ic_state_fields(STEP1_RESPONSE),
                         {"ICStateNum": "218", "ICResubmit": "0"})
        # An HTML-shaped payload keeps working; a missing field stays absent.
        html_state = '<input type="hidden" name="ICStateNum" value="27">'
        self.assertEqual(parser.ic_state_fields(html_state), {"ICStateNum": "27"})
        self.assertEqual(parser.ic_state_fields("<PAGE/>"), {})

    def test_default_term_skips_future_placeholders(self):
        terms = parser.class_search_terms(FULL_TERM_PAGE)
        self.assertEqual(parser.default_term(terms, year=2026)["label"], "2026-27 Term 2")
        self.assertEqual(parser.default_term(terms, year=2020)["label"], "2020-21 Term 2")


class ApiTests(unittest.TestCase):
    def test_term_matching_by_label_substring_and_by_strm(self):
        for requested, expected in (("Term 2", "2026-27 Term 2"), ("2620", "2026-27 Term 2"),
                                    ("Term 1", "2026-27 Term 1")):
            with self.subTest(term=requested):
                sis = make_sis(FakeTransport())
                data = sis.class_search(term=requested, subject="AIE")
                self.assertEqual(data["term"], expected)
                self.assertEqual(data["strm"], "2610" if expected.endswith("Term 1") else "2620")

    def test_omitted_term_defaults_to_newest_option(self):
        sis = make_sis(FakeTransport())
        data = sis.class_search(subject="AIE")
        self.assertEqual(data["term"], "2026-27 Term 2")
        self.assertEqual(data["strm"], "2620")

    def test_ambiguous_term_substring_is_refused_instead_of_picking_the_oldest(self):
        sis = make_sis(FakeTransport(page=FULL_TERM_PAGE))
        with self.assertRaises(SystemExit) as raised:
            sis.class_search(term="Term 2", subject="AIE")
        message = str(raised.exception)
        self.assertIn("ambiguous", message)
        self.assertIn("2026-27 Term 2 (2620)", message)

    def test_unknown_term_exits_with_the_available_options(self):
        sis = make_sis(FakeTransport())
        with self.assertRaises(SystemExit) as raised:
            sis.class_search(term="2030-31 Term 9", subject="AIE")
        message = str(raised.exception)
        self.assertIn("Term not matched", message)
        self.assertIn("2026-27 Term 1 (2610)", message)
        self.assertIn("2026-27 Term 2 (2620)", message)

    def test_missing_subject_and_catalog_is_refused_before_any_request(self):
        transport = FakeTransport()
        sis = make_sis(transport)
        with self.assertRaises(SystemExit) as raised:
            sis.class_search(term="2620")
        self.assertIn("--subject", str(raised.exception))
        self.assertIn("--catalog", str(raised.exception))
        self.assertEqual(transport.gets, [])

    def test_two_step_ajax_fields_preserve_the_verified_protocol(self):
        transport = FakeTransport()
        sis = make_sis(transport)
        data = sis.class_search(subject="AIE", catalog="1904", open_only=False, contains=True)

        self.assertEqual(data["subject"], "AIE")
        self.assertEqual(data["catalog"], "1904")
        self.assertFalse(data["open_only"])
        self.assertTrue(data["contains"])
        self.assertEqual(len(transport.posts), 2)
        action, step1, _timeout = transport.posts[0]
        action2, step2, _timeout2 = transport.posts[1]
        self.assertEqual(action, action2)

        # Step 1 — change event primes the component state.
        self.assertEqual(step1["ICAJAX"], "1")
        self.assertEqual(step1["ICNAVTYPEDROPDOWN"], "0")
        self.assertEqual(step1["ICChanged"], "1")
        self.assertEqual(step1["ICAction"], "None")
        self.assertEqual(step1[config.CLASS_SEARCH_TERM_FIELD], "2620")
        self.assertEqual(step1[config.CLASS_SEARCH_SUBJECT_FIELD], "AIE")
        self.assertEqual(step1[config.CLASS_SEARCH_CATALOG_FIELD], "1904")
        self.assertEqual(step1[config.CLASS_SEARCH_EXACT_FIELD], "C")
        self.assertEqual(step1[config.CLASS_SEARCH_OPEN_FIELD], "N")
        # Career stays explicitly empty: UGCU would return 0 results.
        self.assertEqual(step1[config.CLASS_SEARCH_CAREER_FIELD], "")

        # Step 2 — the search button + state copied back from step 1.
        self.assertEqual(step2["ICChanged"], "-1")
        self.assertEqual(step2["ICAction"], config.CLASS_SEARCH_ACTION)
        # Live shape: ICStateNum/ICResubmit come from the step-1 JS payload;
        # ICSID is not echoed, so the page value is carried over.
        self.assertEqual(step2["ICStateNum"], "218")
        self.assertEqual(step2["ICResubmit"], "0")
        self.assertEqual(step2["ICSID"], "page-sid")
        self.assertEqual(step2[config.CLASS_SEARCH_SUBJECT_FIELD], "AIE")
        self.assertEqual(step2[config.CLASS_SEARCH_CATALOG_FIELD], "1904")

    def test_warning_payload_surfaces_as_a_notice(self):
        sis = make_sis(FakeTransport(payload=WARNING_PAYLOAD))
        data = sis.class_search(subject="CSC")
        self.assertEqual(data["courses"], [])
        self.assertIn("notice", data)
        self.assertIn("--catalog", data["notice"])

    def test_extract_win0_form_keeps_checked_boxes_and_selected_option(self):
        action, fields = extract_win0_form(TERM_PAGE)
        self.assertTrue(action.endswith("SA_LEARNER_SERVICES.CLASS_SEARCH.GBL"))
        self.assertEqual(fields[config.CLASS_SEARCH_OPEN_FIELD], "Y")
        self.assertNotIn("UNCHECKED$chk$9", fields)
        self.assertNotIn("SSR_CLSRCH_WRK2_SSR_PB_CLASS_SRCH", fields)
        self.assertEqual(fields[config.CLASS_SEARCH_TERM_FIELD], "2620")
        with self.assertRaises(TransportError):
            extract_win0_form("<html><body>no form</body></html>")


class CliTests(unittest.TestCase):
    def run_cli(self, argv, fake_sis):
        with patch.object(cli, "Sis", return_value=fake_sis), \
                contextlib.redirect_stdout(io.StringIO()) as out, \
                contextlib.redirect_stderr(io.StringIO()) as err:
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_cli_without_subject_or_catalog_exits_with_actionable_message(self):
        sis = make_sis(FakeTransport())
        with self.assertRaises(SystemExit) as raised:
            self.run_cli(["search"], sis)
        message = str(raised.exception)
        self.assertIn("--subject", message)
        self.assertIn("--catalog", message)

    def test_cli_text_output_has_term_header_courses_and_sections(self):
        code, out, err = self.run_cli(
            ["search", "--subject", "AIE", "--catalog", "1904"], make_sis(FakeTransport()))
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn("[2026-27 Term 2 / 2620] subject=AIE catalog=1904 — 2 course(s)", out)
        self.assertIn("AIE 1904 - AI Exploration IV", out)
        self.assertIn("  L01-LEC(2278)  MoWe 10:00AM - 11:15AM / Fr 10:00AM - 10:50AM  Room 101  Prof A", out)
        self.assertIn("S01-SUP(2549)", out)

    def test_cli_json_output_and_no_secrets_are_printed(self):
        cfg = {"accounts": {"test-user": {"username": "test-user", "password": "test-secret"}},
               "default_account": "test-user"}
        sis = make_sis(FakeTransport(), cfg=cfg)
        code, out, err = self.run_cli(
            ["search", "--subject", "AIE", "--format", "json"], sis)
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        data = json.loads(out)
        self.assertEqual(data["term"], "2026-27 Term 2")
        self.assertEqual(len(data["courses"]), 2)
        for secret in FORBIDDEN_SECRETS:
            self.assertNotIn(secret, out + err)


if __name__ == "__main__":
    unittest.main()
