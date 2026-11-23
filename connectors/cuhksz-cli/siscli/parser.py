"""Content-page parsing: full weekly-schedule parsing; the other components get a generic textifier in v0.1.

Parsing anchors all come from live page structures verified on 2026-10-05
(PeopleSoft CS classic PIA).
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from . import config

_COURSE_CODE = re.compile(r"^[A-Z]{2,4}\s\d{3,4}\s-\s[A-Z]\d{2}")
_COURSE_CODE_TIGHT = re.compile(r"^[A-Z]{2,4}\s\d{3,4}$")
_TERM_LABEL = re.compile(r"\d{4}-\d{2}\s+(?:Term\s+\d|Summer Session)")


def parse_terms(html: str) -> list[dict]:
    """Term list from the term search page: radio idx → term name (the page is reverse-ordered, newest first)."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()
    for row in soup.find_all("tr"):
        rad = row.find("input", {"type": "radio", "name": "SSR_DUMMY_RECV1$sels$0"})
        if rad is None:
            continue
        m = _TERM_LABEL.search(row.get_text(" ", strip=True))
        if not m:
            continue
        label = m.group(0)
        if label in seen:
            continue
        seen.add(label)
        out.append({"idx": rad.get("value"), "term": label})
    return out


def class_search_terms(html: str) -> list[dict]:
    """Term dropdown on the Class Search page: [{"strm", "label"}] (empty option excluded).

    The option order is the page order (oldest → newest), so the last entry is
    the newest term; labels look like "2026-27 Term 2" and strm like "2620".
    """
    soup = BeautifulSoup(html, "html.parser")
    sel = soup.find("select", {"name": config.CLASS_SEARCH_TERM_FIELD})
    if sel is None:
        return []
    out = []
    for opt in sel.find_all("option"):
        strm = (opt.get("value") or "").strip()
        label = opt.get_text(" ", strip=True)
        if strm:
            out.append({"strm": strm, "label": label})
    return out


def ic_state_fields(html: str) -> dict[str, str]:
    """PeopleSoft component state inputs (ICStateNum/ICSID/ICResubmit) echoed by an AJAX response.

    Class Search step 2 must copy these back from the step-1 response; missing
    fields simply stay absent (the caller overlays what is present).
    """
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, str] = {}
    for inp in soup.find_all("input"):
        name = inp.get("name")
        if name in ("ICStateNum", "ICSID", "ICResubmit"):
            out[name] = inp.get("value") or ""
    return out


_CDATA_BLOCK = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)
_CLASS_SEARCH_WARNING = re.compile(r"<PAGE[^>]*id=['\"]SSR_SS_WARNING['\"]", re.I)


def parse_class_search(payload: str) -> dict:
    """Class Search response → {"courses": [...], "notice": optional}.

    The response is an XML wrapper (`<PAGE id='SSR_CLSRCH_RSLT'>`) whose real
    HTML sits in CDATA blocks: concatenate them, then parse. Beyond ~50 classes
    the server answers with an `SSR_SS_WARNING` page instead of results, which
    is surfaced as a structured notice (no courses). Course headers are the
    `win0divDERIVED_CLSRCH_DESCR200$…` divs; a section is a
    `DERIVED_CLSRCH_SSR_CLASSNAME_LONG$…` element; meeting rows contribute
    `MTG_DAYTIME` times (1–2 per section), the first `MTG_ROOM`/`MTG_INSTR`.
    """
    if "over 50 classes" in payload or _CLASS_SEARCH_WARNING.search(payload):
        return {"courses": [], "notice": (
            "SIS refused the query because it matched more than "
            f"{config.CLASS_SEARCH_MAX_CLASSES} classes; add a subject and/or "
            "catalog number to narrow it (e.g. --subject AIE --catalog 1904) "
            "and retry")}
    html = "".join(_CDATA_BLOCK.findall(payload)) or payload
    soup = BeautifulSoup(html, "html.parser")
    courses: list[dict] = []
    current: dict | None = None
    section: dict | None = None
    for el in soup.find_all(id=True):
        eid = el.get("id") or ""
        if (eid.startswith("win0divDERIVED_CLSRCH_DESCR200$")
                or eid.startswith("DERIVED_CLSRCH_DESCR200$")):
            text = el.get_text(" ", strip=True)
            if text and (current is None or text != current["course"]):
                current = {"course": text, "sections": []}
                courses.append(current)
                section = None
        elif eid.startswith("DERIVED_CLSRCH_SSR_CLASSNAME_LONG$") and "span" not in eid:
            text = el.get_text(" ", strip=True)
            if current is not None and text:
                section = {"section": text, "times": [], "room": None, "instructor": None}
                current["sections"].append(section)
        elif section is not None and eid.startswith("MTG_DAYTIME") and not eid.endswith("lbl"):
            t = el.get_text(" ", strip=True)
            if t and t not in section["times"]:
                section["times"].append(t)
        elif section is not None and eid.startswith("MTG_ROOM") and section["room"] is None:
            section["room"] = el.get_text(" ", strip=True) or None
        elif section is not None and eid.startswith("MTG_INSTR") and section["instructor"] is None:
            section["instructor"] = el.get_text(" ", strip=True) or None
    return {"courses": courses}


def parse_grade_report(html: str) -> dict:
    """View My Grades result page: Class Grades table + GPA (nested tables hit repeatedly; dedupe by key)."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    term = ""
    m = _TERM_LABEL.search(text)
    if m:
        term = m.group(0)
    rows, seen = [], set()
    for tb in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in tb.find_all("th")]
        if "Grading" not in headers or "Grade Points" not in headers:
            continue
        for row in tb.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
            if len(cells) >= 6 and _COURSE_CODE_TIGHT.match(cells[0]):
                key = tuple(cells[:6])
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"course": cells[0], "description": cells[1],
                             "units": cells[2], "grading": cells[3],
                             "grade": cells[4], "points": cells[5]})
    gpa = {}
    flat = soup.get_text("\n", strip=True)
    for m2 in re.finditer(r"(Cumulative GPA|Term GPA)\s*:?\s*([\d.]+)", flat):
        gpa[m2.group(1)] = m2.group(2)
    return {"term": term, "rows": rows, "gpa": gpa}


def parse_history(html: str) -> list[dict]:
    """Course history (the page directly contains the full table): Course/Description/Term/Grade/Units/Status."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for td in soup.find_all("td"):
        if not _COURSE_CODE_TIGHT.match(td.get_text(strip=True)):
            continue
        row = td.find_parent("tr")
        if row is None:
            continue
        cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
        if len(cells) >= 6 and _TERM_LABEL.search(cells[2] or ""):
            out.append({"course": cells[0], "description": cells[1], "term": cells[2],
                        "grade": cells[3], "units": cells[4], "status": cells[5]})
    # Dedupe (nested tables may hit repeatedly)
    seen, dedup = set(), []
    for r in out:
        key = (r["course"], r["term"])
        if key not in seen:
            seen.add(key)
            dedup.append(r)
    return dedup


def parse_appt(html: str) -> dict:
    """Enrollment Dates result page: term name + enrollment windows + unit limits."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    term = ""
    m = _TERM_LABEL.search(text)
    if m:
        term = m.group(0)
    appts = []
    lines = text.split("\n")
    for i, l in enumerate(lines):
        if l.strip() == "Regular Academic Session" and i + 4 < len(lines):
            appts.append({"session": "Regular Academic Session",
                          "begins": lines[i + 1], "begin_time": lines[i + 2],
                          "ends": lines[i + 3], "end_time": lines[i + 4]})
    limits = {}
    for m2 in re.finditer(r"(Max Total Units|Min Total Units)\s*\n\s*([\d.]+)", text):
        limits[m2.group(1)] = m2.group(2)
    return {"term": term, "appointments": appts, "limits": limits}


def parse_exam(html: str) -> list[dict]:
    """Exam schedule result page: anchored on table headers (Class/Date/Time/Room…, per the live page)."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tb in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in tb.find_all("th")]
        if not headers or "Class" not in headers:
            continue
        for row in tb.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
            if cells and any(cells) and _COURSE_CODE.match(cells[0].split(" - ")[0].split(" (")[0]):
                out.append(dict(zip([h or f"c{i}" for i, h in enumerate(headers)], cells)))
    return out


def parse_prsnldata(html: str) -> dict:
    """Personal Data Summary: name/email/holds/todo (the HTML source for the identity command)."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    out: dict = {"holds": [], "todo": [], "emails": []}
    m = re.search(r"([^\s]+)'s Personal Data Summary", text)
    if m:
        out["display_name"] = m.group(1)
    if re.search(r"No Holds", text):
        out["holds"] = []
    for line in text.split("\n"):
        s = line.strip()
        if "@" in s and re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", s):
            out["emails"].append(s)
    # Student id: the school email local part looks like <student-id>@link.cuhk.edu.cn
    for e in out["emails"]:
        if e.endswith("@link.cuhk.edu.cn") and e.split("@")[0].isdigit():
            out["student_id"] = e.split("@")[0]
    return out


def parse_pdf_identity(data: bytes) -> dict:
    """Identity block on the first page of the unofficial transcript PDF (best-effort; needs pypdf; AES decrypt with empty password).

    Returns identity fields such as admitted/college/school/major/programme;
    when pypdf is absent, returns {"unavailable": "pypdf not installed"}.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"unavailable": "pypdf not installed"}
    import io
    r = PdfReader(io.BytesIO(data))
    if r.is_encrypted:
        try:
            r.decrypt("")
        except Exception:
            return {"unavailable": "pdf decrypt failed"}
    text = (r.pages[0].extract_text() or "")
    out: dict = {}
    for key, pat in [
        ("name", r"Name:\s*([A-Z][A-Za-z, ]+?)(?:\s+Chinese|\s*$)"),
        ("student_id", r"Student ID No\.?:?\s*(\d+)"),
        ("admitted", r"Admitted in:?\s*([^\n]+)"),
        ("college", r"College:?\s*([^\n]+)"),
        ("school", r"School:?\s*([^\n]+)"),
        ("major", r"Major/Programme:?\s*([^\n]+)"),
        ("mode_of_study", r"Mode of Study:?\s*([^\n]+)"),
    ]:
        m = re.search(pat, text)
        if m:
            out[key] = m.group(1).strip()[:60]
    return out


_CENTER_EVENT = re.compile(
    r"^([A-Z]{2,4}\s\d{3,4}-[A-Z]\d{2})\s+(LEC|TUT|SUP|LAB|SEM)\s+\((\d+)\)"
    r"(?:\s+((?:Mo|Tu|We|Th|Fr|Sa|Su){1,4})\s+(\d{1,2}:\d{2}(?:AM|PM))\s*-\s*(\d{1,2}:\d{2}(?:AM|PM)))?"
    r"\s+(.*)$")


def parse_center_schedule(html: str) -> list[dict]:
    """This Week's Schedule on the student center page: course-section/type/classNbr/weekday/time-slot/room.

    Weekday abbreviations (Mo/Tu/We/Th/Fr/Sa/Su) sit inline in the row — the
    week-view DOM has no column anchors; this page is the authoritative
    source for day-of-week attribution. SUP sections have no fixed meeting
    (weekday/time empty).
    """
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tr in soup.find_all("tr"):
        t = tr.get_text(" ", strip=True)
        m = _CENTER_EVENT.match(t)
        if not m:
            continue
        out.append({"class": m.group(1), "type": m.group(2), "class_nbr": m.group(3),
                    "days": m.group(4) or "", "time": (m.group(5) + " - " + m.group(6)) if m.group(5) else "",
                    "location": m.group(7).strip()})
    # Oversized container rows re-hit as longer text (prefixed with the page header); keep the shortest match set: dedupe by class+type
    seen, dedup = set(), []
    for r in out:
        key = (r["class"], r["type"], r["days"], r["time"])
        if key not in seen:
            seen.add(key)
            dedup.append(r)
    return dedup


def parse_weekly(html: str) -> dict:
    """Weekly schedule: this week's event list + the term course table + the week range.

    An event block = the four lines of the span.SSSTEXTWEEKLY parent
    container (code/type/time-slot/room); the DOM renders duplicates — dedupe
    by the 4-tuple. Day-of-week grid attribution is v0.2 (nested DOM, no
    column anchors).
    """
    soup = BeautifulSoup(html, "html.parser")
    week = ""
    m = re.search(r"Week of \d{1,2}/\d{1,2}/\d{4} - \d{1,2}/\d{1,2}/\d{4}", html)
    if m:
        week = m.group(0)

    events, seen = [], set()
    for span in soup.find_all("span", class_="SSSTEXTWEEKLY"):
        if not _COURSE_CODE.match(span.get_text(" ", strip=True)):
            continue
        lines = [l.strip() for l in span.parent.get_text("\n", strip=True).split("\n")
                 if l.strip()][:4]
        if len(lines) < 4 or not _COURSE_CODE.match(lines[0]):
            continue
        key = tuple(lines[:4])
        if key in seen:
            continue
        seen.add(key)
        events.append({"class": lines[0], "type": lines[1],
                       "time": lines[2], "location": lines[3]})

    courses = []
    for tb in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in tb.find_all("th")]
        if "Course Title" not in headers:
            continue
        for row in tb.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
            if len(cells) >= 5 and _COURSE_CODE.match(cells[0].split(" (")[0]):
                courses.append({"class": cells[0], "title": cells[1],
                                "instructor": cells[2], "start": cells[3], "end": cells[4]})
    return {"week": week, "events": events, "courses": courses}


def textify(html: str, limit: int = 4000) -> str:
    """Generic textifier fallback: strip portal menu/navigation phrases line by line, keeping approximate body text (v0.1)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "head"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    drop = {
        "English", "Simplified Chinese", "Traditional Chinese", "go to ...",
        "My Academics", "Personal Data Summary", "Student Center", "搜索:",
        "Menu", "主菜单", "My Favorites", "我的收藏夹", "t", "Help", "test",
        "Add to Favorites", "Sign out", "登出", "Data Language:",
        "Class Search / Browse Catalog", "Academic Planning", "Enrollment",
        "Academics Records", "My Application", "Campus Personal Information",
        "Academic Records", "Degree Progress/Graduation", "Faculty Center",
        "Personal Center", "Records and Enrollment", "Curriculum Management",
        "Worklist", "Reporting Tools", "PeopleTools", "New Window", "Close",
        "Default Local Node:", "DbName:", "Portal:", "Node:", "WorkCenter Id:",
        "Url:", "Related Content", "主页", "添加到收藏夹",
    }
    lines = []
    for l in text.split("\n"):
        s = l.strip()
        if s and s not in drop:
            lines.append(s)
        if sum(len(x) + 1 for x in lines) > limit:
            break
    return "\n".join(lines)
