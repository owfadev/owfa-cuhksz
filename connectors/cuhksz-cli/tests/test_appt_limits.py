"""Offline regressions for `cuhksz-cli sis appt` enrollment unit limits.

No network, no user config. The fixture mirrors the live result page verified
on 2026-11-23: "Term Enrollment Limits" heads a 2-column grid whose label row
is `Max Total Units | Min Total Units` and whose value row is `18.00 | 9.00`,
nested inside the page's layout tables. The old per-line regex read
`Min Total Units` → `18.00` and dropped Max; the parser must read the table
structurally and keep the JSON `limits` shape.
"""
import contextlib
import io
import json
import unittest
from unittest.mock import patch

from siscli import cli, parser
from siscli.api import Sis

# Live-shaped page (names/ids kept, no personal data): a layout wrapper table
# contains the appointment grid and, below it, the limits grid. Nesting matters:
# every ancestor's text also contains "Enrollment Limits", so the parser must
# choose the innermost limits table.
APPT_PAGE = """<!DOCTYPE html><html><body>
<table class="PSPAGECONTAINER"><tr><td>
<table border="0" cellpadding="0" cellspacing="0" class="PABACKGROUNDINVISIBLE"
       cols="6" id="ACE_DERIVED_REGFRM1_GROUP2">
  <tr><td colspan="3">
    <div id="win0divDERIVED_SSTSNAV_GROUP_BOX">Change Term 2026-27 Term 2 | Undergraduate | CUHK(SZ)</div>
  </td></tr>
  <tr><td align="left" colspan="3" valign="top">
    <div id="win0divSTDNT_ENRL_A_VW$0">
    <table border="1" cellpadding="2" cellspacing="0" class="PSLEVEL1GRIDWBO"
           cols="3" dir="ltr" id="STDNT_ENRL_A_VW$scroll$0" width="540">
      <tr><td align="left" class="PSLEVEL1GRIDLABEL" colspan="3">
        <div id="win0divSTDNT_ENRL_A_VWGP$0">Enrollment Appointments</div></td></tr>
      <tr>
        <th abbr="Session" align="CENTER" class="PSLEVEL1GRIDCOLUMNHDR" scope="col" width="105">Session</th>
        <th abbr="Appointment Begins" align="CENTER" class="PSLEVEL1GRIDCOLUMNHDR" scope="col" width="118">Appointment Begins</th>
        <th abbr="Appointment Ends" align="CENTER" class="PSLEVEL1GRIDCOLUMNHDR" scope="col" width="118">Appointment Ends</th>
      </tr>
      <tr id="trSTDNT_ENRL_A_VW$0_row1" valign="center">
        <td align="left" class="PSLEVEL1GRIDODDROW" height="13">
          <div id="win0divENRL_NAME$0"><span class="PSEDITBOX_DISPONLY" id="ENRL_NAME$0">Regular Academic Session</span></div>
        </td>
        <td align="left" class="PSLEVEL1GRIDODDROW">
          <div id="win0divENRL_START$0"><span class="PSLONGEDITBOX" id="ENRL_START$0">November 23, 2026<br/>12:00AM</span></div>
        </td>
        <td align="left" class="PSLEVEL1GRIDODDROW">
          <div id="win0divENRL_END$0"><span class="PSLONGEDITBOX" id="ENRL_END$0">November 25, 2026<br/>11:59PM</span></div>
        </td>
      </tr>
    </table>
    </div>
  </td></tr>
  <tr><td colspan="6" height="10"></td></tr>
  <tr><td height="53"></td><td align="left" colspan="2" valign="top">
    <div id="win0divSSR_DUMMY_RECVW$0">
    <table border="1" cellpadding="2" cellspacing="0" class="PSLEVEL1GRIDWBO"
           cols="2" dir="ltr" id="SSR_DUMMY_RECVW$scroll$0" width="536">
      <tr><td align="left" class="PSLEVEL1GRIDLABEL" colspan="2">
        <div id="win0divSSR_DUMMY_RECVWGP$0">Term Enrollment Limits</div></td></tr>
      <tr>
        <th abbr="Max Total Units" align="left" class="PSLEVEL1GRIDCOLUMNHDR" scope="col" width="102">Max Total Units</th>
        <th abbr="Min Total Units" align="left" class="PSLEVEL1GRIDCOLUMNHDR" scope="col" width="98">Min Total Units</th>
      </tr>
      <tr id="trSSR_DUMMY_RECVW$0_row1" valign="center">
        <td align="right" class="PSLEVEL1GRIDROW" height="11">
          <div id="win0divDERIVED_SR_APPT_MAX_TOTAL_UNIT$267$$0"><span class="PSEDITBOX_DISPONLY" id="DERIVED_SR_APPT_MAX_TOTAL_UNIT$267$$0">18.00</span></div>
        </td>
        <td align="right" class="PSLEVEL1GRIDROW">
          <div id="win0divDERIVED_SR_APPT_MIN_TOTAL_UNIT$0"><span class="PSEDITBOX_DISPONLY" id="DERIVED_SR_APPT_MIN_TOTAL_UNIT$0">9.00</span></div>
        </td>
      </tr>
    </table>
    </div>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""

EXPECTED_LIMITS = {"Max Total Units": "18.00", "Min Total Units": "9.00"}

# Trap: an OUTER table also carries the text "Enrollment Limits" and its own
# (wrong) Max/Min numbers, with the real grid nested inside it. A parser that
# takes the first table containing the text — instead of the innermost one —
# reads the outer cells' document order (18/9 then 99/1) and returns the last
# pair, 99.00 / 1.00, failing the assertion below.
NESTED_LIMITS_PAGE = """<!DOCTYPE html><html><body>
<table id="outer-summary">
  <tr><td colspan="2">Enrollment Limits (term summary)</td></tr>
  <tr><td colspan="2">
    <table id="inner-real-grid">
      <tr><td colspan="2">Term Enrollment Limits</td></tr>
      <tr><td>Max Total Units</td><td>18.00</td></tr>
      <tr><td>Min Total Units</td><td>9.00</td></tr>
    </table>
  </td></tr>
  <tr><td>Max Total Units</td><td>99.00</td></tr>
  <tr><td>Min Total Units</td><td>1.00</td></tr>
</table>
</body></html>"""

# No limits table: labels on one line, values on the next. Adjacency must not
# pair Min with 18.00; every label comes before every value.
FALLBACK_PAGE = """<html><body>
<div>Term 2026-27 Term 2</div>
<div>Term Enrollment Limits</div>
<div>Max Total Units | Min Total Units</div>
<div>18.00 | 9.00</div>
</body></html>"""

# Truncated/empty pages must yield an empty limits dict, never raise.
MALFORMED_PAGES = [
    "",
    "<html><body>",
    "<html><body><p>Enrollment dates are not available for this term",
    "<html><body><table><tr><td>Enrollment Limits",
]


class ParseApptTests(unittest.TestCase):
    def test_two_row_limits_table_is_zipped_in_document_order(self):
        data = parser.parse_appt(APPT_PAGE)
        self.assertEqual(data["limits"], EXPECTED_LIMITS)
        # Max first (the old regex produced only {"Min Total Units": "18.00"}).
        self.assertEqual(list(data["limits"]), ["Max Total Units", "Min Total Units"])

    def test_innermost_limits_table_wins_over_an_outer_table_with_limits_text(self):
        data = parser.parse_appt(NESTED_LIMITS_PAGE)
        # An outer-table pick would read 99.00 / 1.00 instead.
        self.assertEqual(data["limits"], EXPECTED_LIMITS)

    def test_term_and_appointment_rows_survive_the_table_parse(self):
        data = parser.parse_appt(APPT_PAGE)
        self.assertEqual(data["term"], "2026-27 Term 2")
        self.assertEqual(data["appointments"], [{
            "session": "Regular Academic Session",
            "begins": "November 23, 2026", "begin_time": "12:00AM",
            "ends": "November 25, 2026", "end_time": "11:59PM"}])

    def test_text_fallback_pairs_labels_with_the_numbers_after_all_labels(self):
        data = parser.parse_appt(FALLBACK_PAGE)
        self.assertEqual(data["limits"], EXPECTED_LIMITS)

    def test_malformed_pages_leave_limits_empty_and_never_raise(self):
        for html in MALFORMED_PAGES:
            with self.subTest(html=html):
                data = parser.parse_appt(html)
                self.assertEqual(data["limits"], {})


class FakeApptSis:
    def __init__(self, data):
        self.data = data
        self.terms = []

    def ensure_session(self):  # cli.main bootstraps the session before dispatch
        return True

    def appt(self, term):
        self.terms.append(term)  # record what the CLI actually passed
        return self.data


APPT_DATA = {
    "term": "2026-27 Term 2",
    "appointments": [{"session": "Regular Academic Session",
                      "begins": "November 23, 2026", "begin_time": "12:00AM",
                      "ends": "November 25, 2026", "end_time": "11:59PM"}],
    "limits": dict(EXPECTED_LIMITS),
    "terms_available": ["2026-27 Term 2"],
}


class ApptCliTests(unittest.TestCase):
    def run_cli(self, argv, data):
        sis = FakeApptSis(data)
        with patch.object(cli, "Sis", return_value=sis), \
                contextlib.redirect_stdout(io.StringIO()) as out, \
                contextlib.redirect_stderr(io.StringIO()) as err:
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue(), sis

    def test_text_prints_max_first_then_min_with_a_short_cap_hint(self):
        code, out, err, _sis = self.run_cli(["appt", "--term", "2026-27 Term 2"], APPT_DATA)
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn("Max Total Units: 18.00", out)
        self.assertIn("Min Total Units: 9.00", out)
        self.assertLess(out.index("Max Total Units: 18.00"), out.index("Min Total Units: 9.00"))
        self.assertIn("Max Total Units is the term cap", out)

    def test_json_keeps_the_existing_limits_dict_shape(self):
        code, out, err, _sis = self.run_cli(["appt", "--format", "json"], APPT_DATA)
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(set(data), {"term", "appointments", "limits", "terms_available"})
        self.assertEqual(data["limits"], EXPECTED_LIMITS)

    def test_term_flag_reaches_sis_appt(self):
        code, _out, _err, sis = self.run_cli(["appt", "--term", "2026-27 Term 2"], APPT_DATA)
        self.assertEqual(code, 0)
        self.assertEqual(sis.terms, ["2026-27 Term 2"])

    def test_no_term_passes_none_so_sis_resolves_the_default(self):
        code, _out, _err, sis = self.run_cli(["appt", "--format", "json"], APPT_DATA)
        self.assertEqual(code, 0)
        self.assertEqual(sis.terms, [None])


class CourseHeaderCappedTests(unittest.TestCase):
    def test_capped_course_says_capped_not_expansion_failed(self):
        course = {"course": "CCC 3000 - Gamma", "sections": [1, 2, 3],
                  "sections_complete": False, "sections_expanded": False}
        header = cli._course_header(course, True, capped=True)
        self.assertIn("expansion capped", header)
        self.assertNotIn("expansion failed", header)

    def test_capped_ids_exclude_failed_and_expanded_courses(self):
        expanded = {"course": "AAA 1000 - Alpha", "sections_complete": True,
                    "sections_expanded": True}
        failed = {"course": "BBB 2000 - Beta", "sections_complete": False,
                  "sections_expanded": False}
        capped = {"course": "CCC 3000 - Gamma", "sections_complete": False,
                  "sections_expanded": False}
        data = {"courses": [expanded, failed, capped],
                "notes": [{"kind": "expansion_cap", "cap": 1, "expandable": 3},
                          {"kind": "expansion_failed", "course": "BBB 2000 - Beta"}]}
        self.assertEqual(cli._capped_course_ids(data), {id(capped)})

    def test_same_title_courses_are_matched_by_occurrence(self):
        failed = {"course": "DUP 1000 - Same", "sections_complete": False,
                  "sections_expanded": False}
        capped = {"course": "DUP 1000 - Same", "sections_complete": False,
                  "sections_expanded": False}
        data = {"courses": [failed, capped],
                "notes": [{"kind": "expansion_cap", "cap": 1, "expandable": 2},
                          {"kind": "expansion_failed", "course": "DUP 1000 - Same",
                           "occurrence": 0}]}
        # Keying by title alone would drop the never-attempted duplicate too.
        self.assertEqual(cli._capped_course_ids(data), {id(capped)})


class TermStrmTests(unittest.TestCase):
    def test_strm_is_derived_from_the_label(self):
        self.assertEqual(parser.term_strm("2026-27 Term 1"), "2610")
        self.assertEqual(parser.term_strm("2026-27 Term 2"), "2620")
        self.assertEqual(parser.term_strm("2025-26 Term 2"), "2520")
        self.assertEqual(parser.term_strm("2025-26 Summer Session"), "2550")
        self.assertEqual(parser.term_strm("2026-27 Summer Session"), "2650")
        self.assertIsNone(parser.term_strm("not a term"))

    def test_term_query_accepts_a_strm_code_or_a_label(self):
        class FakeTermTransport:
            def __init__(self):
                self.idx = None

            def get_content(self, comp, nav):
                return TERM_PAGE

            def submit_search(self, html, idx):
                self.idx = idx
                return "<html><body>result</body></html>"

        for query, expected_idx, expected_term in (
                ("2620", "3", "2026-27 Term 2"),
                ("2026-27 Term 1", "0", "2026-27 Term 1")):
            sis = Sis.__new__(Sis)
            sis.cfg = {}
            sis.transport = FakeTermTransport()
            result = sis.term_query("appt", query)
            self.assertEqual(result["term"], expected_term)
            self.assertEqual(sis.transport.idx, expected_idx)

    def test_newest_term_orders_by_label_not_page_position(self):
        # Live radios are 0-based; the newest term sits in the middle here so a
        # page-order pick (terms[0] or terms[-1]) would fail.
        terms = [{"idx": "0", "term": "2025-26 Term 1"},
                 {"idx": "1", "term": "2026-27 Term 2"},   # newest, in the middle
                 {"idx": "2", "term": "2025-26 Term 2"},
                 {"idx": "3", "term": "2026-27 Term 1"}]
        self.assertEqual(parser.newest_term(terms, year=2026)["term"], "2026-27 Term 2")

    def test_explicit_substring_keeps_the_first_page_order_match(self):
        class FakeTermTransport:
            def __init__(self):
                self.idx = None

            def get_content(self, comp, nav):
                return TERM_PAGE

            def submit_search(self, html, idx):
                self.idx = idx
                return "<html><body>result</body></html>"

        sis = Sis.__new__(Sis)
        sis.cfg = {}
        sis.transport = FakeTermTransport()
        # "Term 2" also matches 2026-27 Term 2 (idx 4), but an explicit query
        # keeps the first page-order hit — unchanged from 0.4.2.
        result = sis.term_query("appt", "Term 2")
        self.assertEqual(result["term"], "2025-26 Term 2")
        self.assertEqual(sis.transport.idx, "2")


TERM_PAGE = """<html><body><table>
<tr><td><input type='radio' name='SSR_DUMMY_RECV1$sels$0' value='0'></td>
    <td>Academic 2026-27 Term 1 session</td></tr>
<tr><td><input type='radio' name='SSR_DUMMY_RECV1$sels$0' value='1'></td>
    <td>Academic 2025-26 Term 1 session</td></tr>
<tr><td><input type='radio' name='SSR_DUMMY_RECV1$sels$0' value='2'></td>
    <td>Academic 2025-26 Term 2 session</td></tr>
<tr><td><input type='radio' name='SSR_DUMMY_RECV1$sels$0' value='3'></td>
    <td>Academic 2026-27 Term 2 session</td></tr>
</table></body></html>"""


# The term-query pages can be oldest-first (live `appt`/`exam`; `grades` is
# newest-first). The default must come from label ordering, never position.
TERMS_OLDEST_FIRST = ["2025-26 Term 1", "2025-26 Term 2", "2025-26 Summer Session",
                      "2026-27 Term 1", "2026-27 Term 2"]
TERM_LABEL_BY_IDX = {str(i): label for i, label in enumerate(TERMS_OLDEST_FIRST)}  # live radios are 0-based
TERM_PAGE_OLDEST_FIRST = ("<html><body><table>" + "".join(
    f"<tr><td><input type='radio' name='SSR_DUMMY_RECV1$sels$0' value='{i}'></td>"
    f"<td>Academic {label} session</td></tr>"
    for i, label in enumerate(TERMS_OLDEST_FIRST)) + "</table></body></html>")


class FakeTermResultTransport:
    """Term page + a result page echoing the selected label (no network)."""

    def __init__(self, page, labels):
        self.page = page
        self.labels = labels
        self.idx = None

    def load_session(self):  # cli.main bootstraps the session before dispatch
        return True

    def get_content(self, comp, nav):
        return self.page

    def submit_search(self, html, idx):
        self.idx = idx
        return f"<html><body><div>Term {self.labels[idx]}</div></body></html>"


class DefaultTermCliTests(unittest.TestCase):
    def run_cli(self, argv):
        transport = FakeTermResultTransport(TERM_PAGE_OLDEST_FIRST, TERM_LABEL_BY_IDX)
        sis = Sis.__new__(Sis)
        sis.cfg = {}
        sis.transport = transport
        with patch.object(cli, "Sis", return_value=sis), \
                contextlib.redirect_stdout(io.StringIO()) as out, \
                contextlib.redirect_stderr(io.StringIO()) as err:
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue(), transport

    def test_no_term_on_appt_exam_grades_resolves_the_newest_label(self):
        for cmd in ("appt", "exam", "grades"):
            with self.subTest(cmd=cmd):
                code, out, err, transport = self.run_cli([cmd, "--format", "json"])
                self.assertEqual(code, 0)
                self.assertEqual(err, "")
                self.assertEqual(json.loads(out)["term"], "2026-27 Term 2")
                # Oldest-first page: the newest term is the LAST row (idx 4),
                # not the first (idx 0) that page-order picking would take.
                self.assertEqual(transport.idx, "4")


if __name__ == "__main__":
    unittest.main()
