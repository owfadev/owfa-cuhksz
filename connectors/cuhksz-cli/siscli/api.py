"""API layer: component access and parsing orchestration. Read-only — this connector provides no write operations."""

from __future__ import annotations

import re

from . import config, parser
from .auth import login
from .transport import Transport, extract_win0_form


class Sis:
    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or config.load_config()
        self.transport = Transport(relogin=self._relogin)

    # ---- Session ----
    def _relogin(self) -> None:
        # Automatic re-login (per command — sessions last only minutes) uses the
        # DEFAULT account exclusively; a non-default account is never auto-logged-in.
        username, password = config.resolve_auto_credentials(self.cfg)
        login(self.transport, username, password)

    def ensure_session(self) -> bool:
        if self.transport.load_session():
            return True
        self._relogin()
        return True

    def login(self, username: str, password: str, *, store: bool,
              account: str | None = None, make_default: bool = False) -> dict:
        info = login(self.transport, username, password)
        name = account or username
        config.store_account(self.cfg, name, username, password if store else None,
                             make_default=make_default)
        config.save_config(self.cfg)
        info["account"] = name
        info["default_account"] = config.default_account(self.cfg)
        d = info["default_account"]
        info["note"] = (f"account '{name}' is now the default — automatic re-login will use this account only"
                        if d == name else
                        f"note: default account is '{d}' — automatic re-login uses that one; "
                        f"switch with `cuhksz-cli sis default {name}`")
        return info

    def logout(self) -> None:
        from .auth import logout
        logout(self.transport)
        # Same contract as before 0.4.0: logging out clears every stored password
        # (account names and usernames are kept for a quick re-login).
        for a in (self.cfg.get("accounts") or {}).values():
            if isinstance(a, dict):
                a.pop("password", None)
        self.cfg.pop("password", None)
        config.save_config(self.cfg)

    # ---- Components ----
    def component_html(self, name: str) -> str:
        comp, nav = config.COMPONENTS[name]
        return self.transport.get_content(comp, nav)

    def term_query(self, name: str, term: str | None = None) -> dict:
        """term-interaction component: GET the search page → pick a term → POST Continue → return {terms, term, html}.

        term=None picks the newest term by academic-year/session label ordering
        (the radio order differs per component: `grades` is newest-first,
        `appt`/`exam` are oldest-first, so page position is never trusted). Passing an exact
        strm code (e.g. '2620') or a label substring (e.g. '2026-27 Term 2')
        chooses the term, the substring matching the first hit in page order.
        The term-search page carries labels only, so a strm is matched against
        the code derived from each label.
        """
        html = self.component_html(name)
        terms = parser.parse_terms(html)
        if not terms:
            return {"terms": [], "term": None, "html": html}  # no radios: the page is already the result
        pick = parser.newest_term(terms)
        if term:
            for t in terms:
                if parser.term_strm(t["term"]) == term:
                    pick = t
                    break
            else:
                for t in terms:
                    if term.lower() in t["term"].lower():
                        pick = t
                        break
                else:
                    options = [f"{t['term']} ({parser.term_strm(t['term']) or '?'})" for t in terms]
                    raise SystemExit(f"Term not matched: {term!r}; available: {options}")
        result = self.transport.submit_search(html, pick["idx"])
        return {"terms": terms, "term": pick["term"], "html": result}

    def schedule(self) -> dict:
        return parser.parse_weekly(self.component_html("schedule"))

    def class_search(self, term: str | None = None, subject: str | None = None,
                     catalog: str | None = None, career: str | None = None,
                     open_only: bool = True, contains: bool = False,
                     all_sections: bool = False) -> dict:
        """Read-only Class Search: list courses and their sections/times for a term.

        SIS wants at least two criteria (a term plus a subject and/or catalog
        number), so no subject/catalog at all is refused up front with an
        actionable message. The search is a two-step AJAX flow on the same
        component (verified live 2026-11-23): a change-event POST primes the
        component state, then the search POST copies `ICStateNum`/`ICSID`/
        `ICResubmit` back and triggers `CLASS_SRCH_WRK2_SSR_PB_CLASS_SRCH`.

        `all_sections` expands every course that carries a "View All Sections"
        action (SIS renders only the first 3 sections by default). Expansion
        re-POSTs the same win0 action with the search fields + the state
        echoed by the *current* payload + `ICChanged=-1` + the course's
        `$ICFieldNNN$hviewall$0` action. A failure degrades to the rendered
        sections for that course and records a structured note — it never
        aborts the command. Advisory only: nothing is added to a cart and no
        state is changed (only `ICAction=None`, the search button and the
        hviewall query actions are ever sent).
        """
        if not subject and not catalog:
            raise SystemExit(
                "Class search needs at least two criteria: pass --subject and/or "
                "--catalog together with a term (e.g. `cuhksz-cli sis search "
                "--subject AIE --catalog 1904`). A subject alone can match, but "
                "adding --catalog narrows the result; more than "
                f"{config.CLASS_SEARCH_MAX_CLASSES} classes is refused by SIS.")
        html = self.component_html("class_search")
        terms = parser.class_search_terms(html)
        if not terms:
            raise SystemExit(
                "Class Search page exposes no term dropdown (page structure "
                "changed; re-run with SIS_CLI_DEBUG=<dir> to capture evidence)")
        if term:
            hits = parser.match_terms(terms, term)
            if not hits:
                options = [f"{r['label']} ({r['strm']})" for r in terms]
                raise SystemExit(f"Term not matched: {term!r}; available: {options}")
            if len(hits) > 1:
                options = [f"{r['label']} ({r['strm']})" for r in parser.term_candidates(hits)]
                raise SystemExit(
                    f"Term {term!r} is ambiguous — it matches {len(hits)} terms. "
                    f"Pass the full label or the strm code, e.g. one of: {options}")
            pick = hits[0]
        else:
            pick = parser.default_term(terms)
            if pick is None:
                raise SystemExit("Class Search exposes no usable term; pass --term explicitly")
        strm = pick["strm"]
        action, fields = extract_win0_form(html)

        # Step 1 — change event: write the criteria into the component state.
        change = dict(fields)
        change.update({"ICAJAX": "1", "ICNAVTYPEDROPDOWN": "0",
                       "ICChanged": "1", "ICAction": "None",
                       config.CLASS_SEARCH_OPEN_FIELD: "Y" if open_only else "N"})
        # Keep the career field explicitly empty by default: sending UGCU
        # yields 0 results (verified live); a caller may still override it.
        change[config.CLASS_SEARCH_CAREER_FIELD] = career or ""
        change[config.CLASS_SEARCH_TERM_FIELD] = strm
        if subject:
            change[config.CLASS_SEARCH_SUBJECT_FIELD] = subject
        if catalog:
            change[config.CLASS_SEARCH_CATALOG_FIELD] = catalog
            change[config.CLASS_SEARCH_EXACT_FIELD] = "C" if contains else "E"
        step1 = self.transport.post_ajax(action, change, timeout=60)

        # Step 2 — search: same fields + state echoed by step 1.
        step2 = dict(change)
        step2.update(parser.ic_state_fields(step1))
        step2["ICChanged"] = "-1"
        step2["ICAction"] = config.CLASS_SEARCH_ACTION
        payload = self.transport.post_ajax(action, step2, timeout=90)
        data = parser.parse_class_search(payload)
        courses = data["courses"]
        notes: list[dict] = []
        if all_sections and courses:
            courses, notes = self._expand_all_sections(action, step2, payload, courses)
        # The raw page action is internal plumbing: keep only the derived,
        # user-facing completeness flags in the output.
        for course in courses:
            course.pop("view_all_action", None)
        out = {"term": pick["label"], "strm": strm,
               "subject": subject, "catalog": catalog,
               "career": career or None, "open_only": open_only,
               "contains": contains, "all_sections": all_sections,
               "courses": courses}
        if data.get("notice"):
            out["notice"] = data["notice"]
        if notes:
            out["notes"] = notes
        return out

    # ---- Class Search: per-course "View All Sections" expansion ----
    @staticmethod
    def _course_key(courses: list[dict], index: int) -> tuple[str, int]:
        """Stable identity of a result row: (course title, occurrence of that title)."""
        title = courses[index]["course"]
        occurrence = sum(1 for c in courses[:index] if c["course"] == title)
        return title, occurrence

    @staticmethod
    def _find_course(courses: list[dict], key: tuple[str, int]) -> dict | None:
        """The course matching `key` in this payload (titles may repeat)."""
        title, occurrence = key
        seen = 0
        for course in courses:
            if course["course"] != title:
                continue
            if seen == occurrence:
                return course
            seen += 1
        return None

    @classmethod
    def _merge_expanded(cls, base: list[dict], response: list[dict],
                        key: tuple[str, int]) -> list[dict] | None:
        """Fold an expansion response into the accumulated result.

        The live response is the full result page with the target course
        expanded. `None` means the response carried no usable target and the
        caller must degrade instead of accepting a half-empty payload. A
        previously expanded course keeps its longer section list even if a
        later response renders it collapsed again.
        """
        target = cls._find_course(response, key)
        if target is None or not target.get("sections"):
            return None
        base_keys = [cls._course_key(base, i) for i in range(len(base))]
        out: list[dict] = []
        for i, course in enumerate(base):
            course_key = base_keys[i]
            fresh = cls._find_course(response, course_key)
            if course_key == key:
                expanded = dict(fresh)
                expanded["sections_complete"] = True
                expanded["sections_expanded"] = True
                out.append(expanded)
            elif course.get("sections_expanded"):
                kept = dict(course)
                if fresh is not None:
                    kept["view_all_action"] = fresh.get("view_all_action")
                out.append(kept)
            elif fresh is not None:
                out.append(fresh)
            else:
                out.append(course)
        for i, course in enumerate(response):
            if cls._course_key(response, i) not in base_keys:
                out.append(course)
        return out

    def _expand_all_sections(self, action_url: str, search_fields: dict[str, str],
                             payload: str, courses: list[dict]) -> tuple[list[dict], list[dict]]:
        """Expand up to `CLASS_SEARCH_MAX_EXPANSIONS` courses; never abort the command.

        Each iteration re-parses the *current* payload before building the
        request: expanding a course rewrites the page's `$ICFieldNNN$` action
        names, so a remembered action is not trustworthy. The target is
        located by course position/title (never by the field number).
        """
        notes: list[dict] = []
        targets = [self._course_key(courses, i) for i, c in enumerate(courses)
                   if c.get("view_all_action")]
        cap = config.CLASS_SEARCH_MAX_EXPANSIONS
        if len(targets) > cap:
            notes.append({
                "kind": "expansion_cap",
                "detail": (f"{len(targets)} courses offer 'View All Sections'; only the "
                           f"first {cap} were expanded — the rest keep the first-3-section "
                           f"view (raise CLASS_SEARCH_MAX_EXPANSIONS only knowingly)"),
                "expandable": len(targets), "cap": cap})
            targets = targets[:cap]
        for key in targets:
            # Re-parse the CURRENT payload: action names shift after an expansion.
            fresh = parser.parse_class_search(payload)
            matched = self._find_course(fresh["courses"], key)
            action = matched.get("view_all_action") if matched else None
            if not action:  # fall back to the accumulated row (partial payload)
                accumulated = self._find_course(courses, key)
                action = accumulated.get("view_all_action") if accumulated else None
            if not action or not parser.HVIEWALL_ACTION.fullmatch(action):
                notes.append({
                    "kind": "expansion_failed", "course": key[0], "occurrence": key[1],
                    "detail": "no View All Sections action in the current result payload; "
                              "the rendered sections were kept"})
                continue
            fields = dict(search_fields)
            fields.update(parser.ic_state_fields(payload))
            fields["ICChanged"] = "-1"
            fields["ICAction"] = action
            try:
                expanded_payload = self.transport.post_ajax(
                    action_url, fields, timeout=config.CLASS_SEARCH_EXPANSION_TIMEOUT)
                parsed = parser.parse_class_search(expanded_payload)
            except Exception as exc:  # network/timeout/parse: degrade, never abort
                notes.append({
                    "kind": "expansion_failed", "course": key[0], "occurrence": key[1],
                    "detail": f"{type(exc).__name__}; the rendered sections were kept"})
                continue
            merged = self._merge_expanded(courses, parsed["courses"], key)
            if merged is None:
                notes.append({
                    "kind": "expansion_failed", "course": key[0], "occurrence": key[1],
                    "detail": "the expansion response carried no matching course; "
                              "the rendered sections were kept"})
                continue
            courses = merged
            payload = expanded_payload
        return courses, notes

    def schedule_with_days(self) -> dict:
        """Weekly schedule + day-of-week attribution from the student center page (the center page is the authoritative source)."""
        data = self.schedule()
        data["timetable"] = parser.parse_center_schedule(self.component_html("center"))
        return data

    def grades(self, term: str | None = None) -> dict:
        q = self.term_query("grades", term)
        report = parser.parse_grade_report(q["html"])
        report["term"] = report["term"] or q["term"] or ""
        report["terms_available"] = [t["term"] for t in q["terms"]]
        return report

    def appt(self, term: str | None = None) -> dict:
        q = self.term_query("appt", term)
        data = parser.parse_appt(q["html"])
        data["terms_available"] = [t["term"] for t in q["terms"]]
        return data

    def exam(self, term: str | None = None) -> dict:
        q = self.term_query("exam", term)
        return {"term": q["term"], "rows": parser.parse_exam(q["html"]),
                "terms_available": [t["term"] for t in q["terms"]]}

    def history(self) -> list[dict]:
        return parser.parse_history(self.component_html("history"))

    def transcript_pdf(self, lang: str = "eng") -> tuple[bytes, str]:
        """Unofficial transcript: View Report POST → extract the PDF URL → download. Returns (bytes, url)."""
        code = config.TRANSCRIPT_TYPES.get(lang)
        if not code:
            raise SystemExit(f"Unknown transcript language {lang!r}; available: {sorted(config.TRANSCRIPT_TYPES)}")
        html = self.transport.submit_icaction(
            *config.COMPONENTS["transcript"],
            action=config.IC_VIEW_REPORT,
            extra={config.TRANSCRIPT_TYPE_FIELD: code})
        m = re.search(r'''['"]([^'"]*\.pdf[^'"]*)['"]''', html, re.I)
        if not m:
            raise RuntimeError("No PDF link found on the report page (structure changed or report generation failed)")
        url = m.group(1)
        r = self.transport.request("GET", url, absolute=True)
        if r.status_code != 200 or "pdf" not in (r.headers.get("content-type") or "").lower():
            raise RuntimeError(f"PDF download failed: HTTP {r.status_code}")
        return r.content, url

    def identity(self) -> dict:
        """Student identity: prsnldata (HTML: name/email/student id/holds) + transcript PDF (college/major/admitted)."""
        data = parser.parse_prsnldata(self.component_html("prsnldata"))
        try:
            pdf, _url = self.transcript_pdf("eng")
            data.update(parser.parse_pdf_identity(pdf))
        except Exception as e:
            data["transcript_identity"] = f"unavailable: {e}"
        return data

    def dpr_html(self) -> str:
        return self.component_html("dpr")

    def raw(self, url: str) -> str:
        return self.transport.follow_shell(self.transport.request("GET", url)).text
