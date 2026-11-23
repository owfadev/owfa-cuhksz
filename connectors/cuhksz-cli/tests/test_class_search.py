"""Offline regressions for the read-only SIS Class Search (`cuhksz-cli sis search`).

No network, no user config: the fabricated term page / CDATA payload mirror the
live shapes verified on 2026-11-23, and a fake transport stands in for the
PeopleSoft session.
"""
import contextlib
import io
import json
import unittest
from datetime import date
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

# Full live-shaped dropdown: placeholder years run far into the future, and
# inside each academic year the Summer row comes FIRST (live order: 2650, 2610,
# 2620). The class-search default must still land on Term 2, not on the future
# Summer row — that regression is what this fixture pins.
FULL_TERM_PAGE = ("<html><body><form name='win0' "
                  "action='/psc/csprd/EMPLOYEE/HRMS/c/SA_LEARNER_SERVICES.CLASS_SEARCH.GBL'>"
                  "<select name='CLASS_SRCH_WRK2_STRM$35$'>" + "".join(
                      f'<option value="{y % 100:02d}50">{y}-{str(y+1)[-2:]} Summer Session</option>'
                      f'<option value="{y % 100:02d}10">{y}-{str(y+1)[-2:]} Term 1</option>'
                      f'<option value="{y % 100:02d}20">{y}-{str(y+1)[-2:]} Term 2</option>'
                      for y in range(2014, 2036)) + "</select></form></body></html>")

# ---- synthetic "View All Sections" fixtures (shapes verified live 2026-11-23):
# each course with more than 3 rendered sections carries one
# `javascript:submitAction_win0(document.win0,'$ICFieldNNN$hviewall$N')` link.
A_ACTION = "$ICField106$hviewall$0"
B_ACTION = "$ICField106$hviewall$1"
C_ACTION = "$ICField106$hviewall$2"
C_SHIFTED_ACTION = "$ICField200$hviewall$2"  # action names shift after an expansion
PAYLOAD_STATE = ("<script>oDoc.win0.ICStateNum.value=301;"
                 "oDoc.win0.ICResubmit.value='0';</script>")


def _course_html(idx: int, title: str, sections: list[tuple],
                 action: str | None = None) -> str:
    parts = [f"<div id='win0divDERIVED_CLSRCH_DESCR200${idx}'>{title}</div>"]
    if action:
        parts.append(
            f"<div id='win0div$ICField106${idx}'>"
            f"<a name='{action}' id='{action}' "
            f"href=\"javascript:submitAction_win0(document.win0,'{action}');\" "
            f"class='HEADERLINK'>View All Sections</a></div>")
    for j, (name, when, room, instructor) in enumerate(sections):
        parts.append(f"<div id='DERIVED_CLSRCH_SSR_CLASSNAME_LONG${idx}${j}'>{name}</div>")
        if when:
            parts.append(f"<div id='MTG_DAYTIME${idx}${j}'>{when}</div>")
        if room:
            parts.append(f"<div id='MTG_ROOM${idx}${j}'>{room}</div>")
        if instructor:
            parts.append(f"<div id='MTG_INSTR${idx}${j}'>{instructor}</div>")
    return "".join(parts)


def _lec_sections(prefix: str, count: int, start: int = 1000) -> list[tuple]:
    return [(f"{prefix}{i:02d}-LEC({start + i})", "Mo 9:00AM - 10:00AM", "Room 1", "Prof X")
            for i in range(1, count + 1)]


def _tut_sections(prefix: str, count: int, start: int = 2000) -> list[tuple]:
    return [(f"{prefix}{i:02d}-TUT({start + i})", "Fr 2:00PM - 3:00PM", "Room 2", "TA Y")
            for i in range(1, count + 1)]


def _results_payload(*blocks: str, state: str = "") -> str:
    return ("<?xml version='1.0'?><PAGE id='SSR_CLSRCH_RSLT'><![CDATA["
            + state + "".join(blocks) + "]]></PAGE>")


MULTI_INITIAL = _results_payload(
    _course_html(0, "AAA 1000 - Alpha", _lec_sections("L", 3), action=A_ACTION),
    _course_html(1, "BBB 2000 - Beta", _lec_sections("L", 2)),
    _course_html(2, "CCC 3000 - Gamma",
                 _lec_sections("L", 2) + _tut_sections("T", 1), action=C_ACTION),
    state=PAYLOAD_STATE,
)
AFTER_A = _results_payload(
    _course_html(0, "AAA 1000 - Alpha", _lec_sections("L", 6), action=A_ACTION),
    _course_html(1, "BBB 2000 - Beta", _lec_sections("L", 2)),
    _course_html(2, "CCC 3000 - Gamma",
                 _lec_sections("L", 2) + _tut_sections("T", 1), action=C_SHIFTED_ACTION),
    state=PAYLOAD_STATE,
)
AFTER_C = _results_payload(
    # A collapsed again on purpose: the merge must keep the earlier expansion.
    _course_html(0, "AAA 1000 - Alpha", _lec_sections("L", 3), action=A_ACTION),
    _course_html(1, "BBB 2000 - Beta", _lec_sections("L", 2)),
    _course_html(2, "CCC 3000 - Gamma",
                 _lec_sections("L", 4) + _tut_sections("T", 1), action=C_SHIFTED_ACTION),
)
AFTER_C_ONLY = _results_payload(
    _course_html(0, "AAA 1000 - Alpha", _lec_sections("L", 3), action=A_ACTION),
    _course_html(1, "BBB 2000 - Beta", _lec_sections("L", 2)),
    _course_html(2, "CCC 3000 - Gamma",
                 _lec_sections("L", 4) + _tut_sections("T", 1), action=C_ACTION),
)
GFH_PAYLOAD = _results_payload(
    _course_html(0, "GFH 1000 - In Dialogue with Humanity",
                 _lec_sections("L", 3) + _tut_sections("T", 4), action=A_ACTION))

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


class ExpandingTransport(FakeTransport):
    """FakeTransport + per-action "View All Sections" responses."""

    def __init__(self, page=TERM_PAGE, step1=STEP1_RESPONSE, payload=RESULT_PAYLOAD,
                 expansions=None, fail_actions=()):
        super().__init__(page=page, step1=step1, payload=payload)
        self.expansions = dict(expansions or {})
        self.fail_actions = set(fail_actions)

    def post_ajax(self, action_url, fields, timeout=None):
        self.posts.append((action_url, dict(fields), timeout))
        if len(self.posts) == 1:
            return self.step1
        if len(self.posts) == 2:
            return self.payload
        action = fields.get("ICAction")
        if action in self.fail_actions:
            raise TransportError("synthetic expansion failure")
        return self.expansions.get(action, self.payload)


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
        # Page-order rule: inside a year SIS lists Summer first, Term 2 last, so
        # the default is the year's Term 2 — NOT the future Summer row, which a
        # chronological max would pick.
        self.assertEqual(parser.default_term(terms, year=2026)["label"], "2026-27 Term 2")
        self.assertEqual(parser.default_term(terms, year=2020)["label"], "2020-21 Term 2")
        self.assertNotIn("Summer", parser.default_term(terms, year=2026)["label"])

    def test_newest_term_is_the_chronological_max_not_the_page_order_max(self):
        # The term-query radios use the other rule; keep both documented and pinned.
        terms = parser.class_search_terms(FULL_TERM_PAGE)
        self.assertEqual(parser.newest_term(terms, year=2026)["label"], "2026-27 Summer Session")

    def test_default_term_uses_the_injected_clock(self):
        terms = parser.class_search_terms(FULL_TERM_PAGE)
        with patch.object(parser, "_today", return_value=date(2020, 6, 1)):
            self.assertEqual(parser.default_term(terms)["label"], "2020-21 Term 2")

    def test_term_candidates_take_an_explicit_today(self):
        terms = parser.class_search_terms(FULL_TERM_PAGE)
        hits = parser.match_terms(terms, "Term 2")
        candidates = parser.term_candidates(hits, today=date(2026, 11, 23))
        self.assertEqual(len(candidates), 6)
        self.assertIn({"strm": "2620", "label": "2026-27 Term 2"}, candidates)

    def test_parse_class_search_attaches_view_all_actions_to_their_course(self):
        courses = parser.parse_class_search(MULTI_INITIAL)["courses"]
        self.assertEqual(courses[0]["view_all_action"], A_ACTION)
        self.assertFalse(courses[0]["sections_complete"])
        self.assertIsNone(courses[1]["view_all_action"])
        self.assertTrue(courses[1]["sections_complete"])
        self.assertEqual(courses[2]["view_all_action"], C_ACTION)
        self.assertFalse(courses[2]["sections_complete"])

    def test_parse_terms_finds_a_label_embedded_in_the_row(self):
        # The unanchored label scan is what parse_terms/grades/appt rely on; a
        # second, anchored `_TERM_LABEL` definition used to shadow it.
        html = ("<table><tr><td>Pick a term</td>"
                "<td><input type='radio' name='SSR_DUMMY_RECV1$sels$0' value='0'></td>"
                "<td>Academic 2026-27 Term 2 session</td></tr></table>")
        self.assertEqual(parser.parse_terms(html), [{"idx": "0", "term": "2026-27 Term 2"}])

    def test_grade_and_appt_term_labels_are_found_mid_page(self):
        grades = ("<html><body><div>Grades for 2026-27 Term 2</div>"
                  "<table><tr><th>Grading</th><th>Grade Points</th></tr></table></body></html>")
        self.assertEqual(parser.parse_grade_report(grades)["term"], "2026-27 Term 2")
        appt = "<html><body><div>Enrollment for 2026-27 Term 1 opens soon</div></body></html>"
        self.assertEqual(parser.parse_appt(appt)["term"], "2026-27 Term 1")


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
        # Inject the year: the fixture only runs to 2035-36, so a real
        # date.today() would move the candidate window past it after 2029.
        with patch.object(parser, "_today", return_value=date(2026, 11, 23)):
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

    def test_default_marks_incomplete_courses_without_expanding(self):
        transport = ExpandingTransport(payload=MULTI_INITIAL)
        sis = make_sis(transport)
        data = sis.class_search(subject="AIE")
        self.assertFalse(data["all_sections"])
        courses = {c["course"]: c for c in data["courses"]}
        self.assertFalse(courses["AAA 1000 - Alpha"]["sections_complete"])
        self.assertFalse(courses["AAA 1000 - Alpha"]["sections_expanded"])
        self.assertTrue(courses["BBB 2000 - Beta"]["sections_complete"])
        self.assertEqual(len(transport.posts), 2)  # no expansion request without the flag

    def test_all_sections_expands_every_course_and_marks_completeness(self):
        transport = ExpandingTransport(
            payload=MULTI_INITIAL,
            expansions={A_ACTION: AFTER_A, C_SHIFTED_ACTION: AFTER_C})
        sis = make_sis(transport)
        data = sis.class_search(subject="AIE", all_sections=True)

        self.assertTrue(data["all_sections"])
        self.assertEqual([c["course"] for c in data["courses"]],
                         ["AAA 1000 - Alpha", "BBB 2000 - Beta", "CCC 3000 - Gamma"])
        courses = {c["course"]: c for c in data["courses"]}
        # AFTER_C renders A collapsed again; the merge keeps the earlier expansion.
        self.assertEqual(len(courses["AAA 1000 - Alpha"]["sections"]), 6)
        self.assertTrue(courses["AAA 1000 - Alpha"]["sections_complete"])
        self.assertTrue(courses["AAA 1000 - Alpha"]["sections_expanded"])
        self.assertEqual(len(courses["BBB 2000 - Beta"]["sections"]), 2)
        self.assertTrue(courses["BBB 2000 - Beta"]["sections_complete"])
        self.assertFalse(courses["BBB 2000 - Beta"]["sections_expanded"])
        self.assertEqual(len(courses["CCC 3000 - Gamma"]["sections"]), 5)
        self.assertTrue(courses["CCC 3000 - Gamma"]["sections_complete"])
        for course in data["courses"]:
            self.assertNotIn("view_all_action", course)  # page plumbing is not output
        self.assertNotIn("notes", data)

        self.assertEqual(len(transport.posts), 4)  # step 1, step 2, two expansions
        # Action names shift after an expansion: the second expansion must use
        # the action re-read from the current payload, not the remembered one.
        self.assertEqual(transport.posts[3][1]["ICAction"], C_SHIFTED_ACTION)
        # State comes from the current payload, not from step 1.
        self.assertEqual(transport.posts[2][1]["ICStateNum"], "301")
        self.assertEqual(transport.posts[2][1]["ICChanged"], "-1")

    def test_failed_expansion_degrades_without_aborting_the_command(self):
        transport = ExpandingTransport(
            payload=MULTI_INITIAL, expansions={C_ACTION: AFTER_C_ONLY},
            fail_actions={A_ACTION})
        sis = make_sis(transport)
        data = sis.class_search(subject="AIE", all_sections=True)  # must not raise

        courses = {c["course"]: c for c in data["courses"]}
        self.assertEqual(len(courses["AAA 1000 - Alpha"]["sections"]), 3)
        self.assertFalse(courses["AAA 1000 - Alpha"]["sections_complete"])
        self.assertFalse(courses["AAA 1000 - Alpha"]["sections_expanded"])
        # The rest of the run still expands.
        self.assertEqual(len(courses["CCC 3000 - Gamma"]["sections"]), 5)
        self.assertTrue(courses["CCC 3000 - Gamma"]["sections_complete"])
        notes = data["notes"]
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["kind"], "expansion_failed")
        self.assertEqual(notes[0]["course"], "AAA 1000 - Alpha")
        self.assertEqual(notes[0]["occurrence"], 0)  # row identity, not just title
        self.assertIn("kept", notes[0]["detail"])

    def test_expansion_cap_is_respected_and_noted(self):
        transport = ExpandingTransport(
            payload=MULTI_INITIAL, expansions={A_ACTION: AFTER_A})
        sis = make_sis(transport)
        with patch.object(config, "CLASS_SEARCH_MAX_EXPANSIONS", 1):
            data = sis.class_search(subject="AIE", all_sections=True)

        courses = {c["course"]: c for c in data["courses"]}
        self.assertEqual(len(courses["AAA 1000 - Alpha"]["sections"]), 6)
        self.assertEqual(len(courses["CCC 3000 - Gamma"]["sections"]), 3)
        self.assertFalse(courses["CCC 3000 - Gamma"]["sections_complete"])
        self.assertEqual(len(transport.posts), 3)  # only one expansion request
        cap_notes = [n for n in data.get("notes", []) if n["kind"] == "expansion_cap"]
        self.assertEqual(len(cap_notes), 1)
        self.assertEqual(cap_notes[0]["cap"], 1)

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

    def test_cli_text_groups_lec_and_tut_sections(self):
        sis = make_sis(ExpandingTransport(payload=GFH_PAYLOAD))
        code, out, err = self.run_cli(
            ["search", "--subject", "GFH", "--catalog", "1000"], sis)
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn("LEC:", out)
        self.assertIn("TUT:", out)
        self.assertLess(out.index("LEC:"), out.index("TUT:"))
        self.assertIn("    L01-LEC(1001)  Mo 9:00AM - 10:00AM", out)
        self.assertIn("    T01-TUT(2001)  Fr 2:00PM - 3:00PM", out)

    def test_cli_text_marks_expanded_courses_with_all_section_counts(self):
        transport = ExpandingTransport(
            payload=MULTI_INITIAL,
            expansions={A_ACTION: AFTER_A, C_SHIFTED_ACTION: AFTER_C})
        code, out, err = self.run_cli(
            ["search", "--subject", "AIE", "--all-sections"], make_sis(transport))
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn("[all sections]", out)
        self.assertIn("AAA 1000 - Alpha  — 6 sections (all)", out)
        self.assertIn("BBB 2000 - Beta  — 2 sections", out)
        self.assertIn("CCC 3000 - Gamma  — 5 sections (all)", out)

    def test_cli_text_reports_a_failed_expansion_as_a_note(self):
        transport = ExpandingTransport(
            payload=MULTI_INITIAL, expansions={C_ACTION: AFTER_C_ONLY},
            fail_actions={A_ACTION})
        code, out, err = self.run_cli(
            ["search", "--subject", "AIE", "--all-sections"], make_sis(transport))
        self.assertEqual(code, 0)
        self.assertIn("[note] AAA 1000 - Alpha:", out)
        self.assertIn("3 sections (expansion failed; first 3 shown)", out)

    def test_cli_json_exposes_per_course_completeness(self):
        code, out, err = self.run_cli(
            ["search", "--subject", "AIE", "--format", "json"],
            make_sis(ExpandingTransport(payload=MULTI_INITIAL)))
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertFalse(data["all_sections"])
        self.assertFalse(data["courses"][0]["sections_complete"])
        self.assertTrue(data["courses"][1]["sections_complete"])

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
