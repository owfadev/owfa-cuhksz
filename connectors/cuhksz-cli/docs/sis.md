# sis backend (cuhksz-cli sis) — CUHK-SZ SIS read-only connector

> Per-backend deep reference of the unified `cuhksz-cli` connector (since 0.2.1; formerly a standalone SIS connector package). Single entry point `cuhksz-cli sis ...` — the legacy wrapper was removed in 0.3.0 (migration table in SKILL.md).

A command-line connector for `sis.cuhk.edu.cn` (Oracle PeopleSoft Campus Solutions): **a purely read-only data plane — no agent logic, no MCP, no monitoring** — serving as a fact interface for upper layers (wiki domain plugins / humans / scripts). The technical route and login findings carry over from the bb backend (the same ADFS `sts.cuhk.edu.cn`, the same `cuhksz\` domain-prefix rule); the PeopleSoft-side login and component access were written from live reverse engineering on 2026-10-05.

## Installation

Use the instance's declared Python environment when one exists. Otherwise, from `connectors/cuhksz-cli` (the unified connector this doc belongs to), choose one of these isolated environments; activation and global PATH changes are unnecessary.

Windows (PowerShell or Git Bash):

```text
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e .
./.venv/Scripts/python.exe -m cuhkszcli sis --help
```

macOS / Linux:

```text
python3 -m venv .venv
./.venv/bin/python -m pip install -e .
./.venv/bin/python -m cuhkszcli sis --help
```

On hosts using uv, `uv venv .venv` and `uv pip install --python .venv -e .` are an alternative; use the corresponding environment's Python path above to run the module. No `--break-system-packages` is needed for a virtual environment.

If an earlier `pip --user` installation succeeded but `cuhksz-cli` is not found, run `python -m cuhkszcli sis --help` using the **same Python that installed it**. This bypasses the missing console-script PATH entry. `No module named cuhkszcli` means that interpreter cannot see the installed package; check `python -m pip show siscli` and use the intended environment instead of reinstalling globally. For the default user-install script directory, use:

```text
python -c "import sysconfig; print(sysconfig.get_path('scripts', scheme=sysconfig.get_preferred_scheme('user')))"
```

The user scheme matters: an unqualified `get_path('scripts')` may report the base interpreter's script directory. Custom install prefixes can differ. Prefer the module invocation over changing persistent PATH settings. `--help` checks the launcher without logging in; run authentication only when needed for the user's task.

Dependencies are only `curl_cffi` (Chrome TLS fingerprint) and `beautifulsoup4`.

## Authentication (ADFS OAuth2 → PeopleSoft session)

Flow (fully HTTP-reproducible, no browser):

1. `sts.cuhk.edu.cn/adfs/oauth2/authorize` (client_id registered to SIS) → ADFS form login (same source as the bb backend: a single POST, the student id automatically gets the `cuhksz\` prefix);
2. the callback `sis.cuhk.edu.cn/sso/dologin.html?code=…` is a static page — replicate its JS form and POST `/psp/csprd/?cmd=login&languageCd=…&code=…` (fixed service account `CUSZ_SSO_LOGIN` + a random password; GET that URL first to warm up `PSJSESSIONID` before POSTing);
3. the PeopleSoft backend exchanges the code for a session; once `PS_TOKEN` lands, the login has succeeded.

Credentials and sessions live only in the local machine substrate: `$OWFA_HOME/connectors/cuhksz-cli/homes/<id>/sis/` — `config.json` (credentials, permission 0600) + `session.json` (cookie jar). `cuhksz-cli home status` prints the effective path; `SIS_CLI_HOME` remains an explicit override (and a machine with no OWFA helper falls back to the legacy `~/.sis-cli`, printed with a migration notice). **Never written into any repository.** Off-disk option: the environment variables `SIS_CLI_USERNAME` / `SIS_CLI_PASSWORD`, or `cuhksz-cli sis login --no-store`.

**Multiple accounts & the default account** (0.4.0): credentials are stored per account (`login --account <name>`, default name = the username) as `{"accounts": {name: {username, password}}, "default_account": name}`; the legacy flat config is still read as an implicit default account and normalized on the next save. **Automatic re-login (per command — see below) only ever uses the default account**: the first stored login becomes it automatically; `cuhksz-cli sis default` shows it, `cuhksz-cli sis default <name>` switches (clearing the session so the next command deterministically logs in as it); `cuhksz-cli sis accounts` lists accounts (passwords never shown). When several accounts are stored and no default is set, auto-login refuses to pick one and says so. Recommended init: run `cuhksz-cli sis login` manually once to leave credentials, and confirm the default (`cuhksz-cli sis default`). The environment variables only apply to explicit `login` (plus a last-resort auto-login fallback when no default account has stored credentials).

**Short-lived sessions**: in live testing `PS_TOKEN` expires in about 5 minutes, and `PORTAL-PSJSESSIONID` is re-issued on a rolling basis with each response. CLI strategy: write through session.json after every request; when component access hits the login shell, automatically re-login once and replay — using the **default account's** stored credentials (the ADFS session persists, so a re-login costs ≈ two requests).

## PeopleSoft access essentials (verified 2026-10-05)

- **PS_DEVICEFEATURES cookie**: the shell-page JS uses it to detect the browser environment; without it, direct psc hits only ever return the bootstrap shell. Format = JSON stripped of `{}`/quotes, commas replaced by spaces (see `/csprd/signin.js`). The CLI always seeds a typical desktop Chrome value on the session.
- **psc/psp ping-pong**: hitting `/psc/…/c/<component>` directly first returns a shell (`self.location` points to the psp-version URL); following it reaches the real content or a portal framework page (the `ptifrmtgtframe` TargetContent iframe — take its src and GET it).
- **PORTALPARAM_PTCNAV**: the student-role permission check carries the navigation context — direct psc hits must include `?PORTALPARAM_PTCNAV=<HC_…>`; without it you get "not authorized" (verified: SSR_STUDENT_SCHEDULE without PTCNAV was rejected; SSR_SSENRL_SCHD_W with it passed). The long FolderPath/EOPP parameters can be omitted entirely.
- Components expose no public REST: the data lives inside PIA HTML; write a parser per component.

## Commands (all read-only, `--format text|json`)

| Command | Purpose |
|---|---|
| `status` | Offline tri-state session/credential evidence (see Status contract below) + the list of available components |
| `login` / `logout` | Interactive login (`--account <name>` stores under an account name; first login becomes the default; `--no-store` keeps credentials off disk) / logout and clear local state (stored passwords wiped, account names kept) |
| `accounts` / `default [<name>]` | List stored accounts (passwords never shown) / show or set the default account — the only one auto-login ever uses |

| `schedule [--days]` | My weekly class schedule: this week's events + the term course table; `--days` adds the **day-of-week timetable** from the student center page (Mo/Tu/We…) |
| `search [--term T] [--subject S] [--catalog C] [--contains] [--career C] [--all-seats] [--all-sections]` | **Class Search**: courses + sections/times/room/instructor for a term (read-only catalog query; open sections only by default; `--all-sections` expands the first-3 view) |
| `grades [--term label\|strm]` | View my grades: per-term course rows (course/units/grading basis/grade/grade points); defaults to the newest term |
| `history` | Full course history: course/description/term/grade/units (page-direct, no interaction needed) |
| `appt [--term label\|strm]` | Enrollment dates: registration windows (start/end times) + unit limits |
| `exam [--term label\|strm]` | Exam schedule (empty when the current term has not published it yet) |
| `transcript [--lang eng\|chi\|ge-edu] [-o F]` | Download the unofficial transcript PDF (View Report → FILEDB_XMLP PDF, AES with empty password) |
| `identity` | Structured student identity: name/id/email/holds (prsnldata page) + college/major/admitted/mode of study (transcript PDF, needs pypdf) |
| `dpr` | Degree progress report (currently requires Request Audit to generate; outputs the page's current state as-is) |
| `center` / `assignments` | Student center page / per-assignment grades (text summaries; assignments often has no data) |
| `raw <url> [--post --action IC-name --set k=v] [--file F]` | GET/POST pass-through — the POST navigation primitive (issue #6 ①): dropdown jumps and View Report style pages are reachable via ICAction POST; probes no longer stop at GET |

**term interaction mechanism** (grades/appt/exam): GET the search page → parse the term radios (`SSR_DUMMY_RECV1$sels$0`, the page is reverse-ordered, newest first) → POST the `win0` form (ICAction=Continue button `DERIVED_SSS_SCT_SSR_PB_GO`) → result page. This POST is a query action (equivalent to clicking "Continue" on the web page) and changes no data. `--term` accepts the strm code (`2620`, derived from the label because these pages expose labels only) or a label substring.

## Enrollment dates and unit limits (`appt`)

`cuhksz-cli sis appt` shows a term's registration windows and that term's unit limits.

**Max is the term cap, Min is the floor.** `Max Total Units` is the ceiling on the term load — the limit behind the SIS "term maximum exceeded" error when you try to add a course beyond it. `Min Total Units` is the enrollment floor (the minimum a full-time student must carry), not a registration limit. Live ground truth (verified 2026-11-23):

| Term | Max Total Units | Min Total Units |
|---|---|---|
| 2026-27 Term 2 | 18.00 | 9.00 |
| 2026-27 Term 1 | 20.00 | 9.00 |
| 2025-26 Term 2 | 18.00 | 9.00 |

Earlier connector versions printed only `Min Total Units: 18.00` — exactly backwards. **Why the parser is table-based:** the live page renders the two labels in one row and the two values in the next (`Term Enrollment Limits` heading, then `Max Total Units | Min Total Units`, then `18.00 | 9.00`), so the text order is label, label, value, value. A per-line label→number regex pairs `Min Total Units` with `18.00` (Max's cell is followed by the other label, not a number) and loses Max. `parse_appt` therefore locates the innermost `<table>` whose text contains `Enrollment Limits`, reads the label cells ending in `Total Units` and the numeric cells in document order, and zips them. A defensive text fallback still pairs the labels with the numbers that follow **all** labels (never per-line adjacency), and a page with no limits leaves `limits` empty instead of raising.

Text output prints Max first, then Min, plus a one-line hint that Max is the cap that blocks registration. JSON keeps the existing `limits` dict shape — `{"Max Total Units": "18.00", "Min Total Units": "9.00"}` — with the same keys and case.

## Class search (course catalog + section times)

`cuhksz-cli sis search` lists the courses a term offers, and for each course its sections with meeting times, room and instructor. It is a **catalog query**, not enrollment: no cart, no selection, no state change.

```text
cuhksz-cli sis search --term '2026-27 Term 2' --subject AIE
cuhksz-cli sis search --term 2620 --subject CSC --catalog 3200
cuhksz-cli sis search --subject ENG --catalog 2002S --contains --all-seats --format json
cuhksz-cli sis search --term 2620 --subject GFH --catalog 1000 --all-sections
```

- `--term` accepts the strm code (`2620`) or a label substring; a substring that matches more than one term (e.g. bare `Term 2`, which exists from 2014-15 to 2035-36) is **refused** with the matching terms listed — pass the full label (`2026-27 Term 2`) or the strm. When omitted it resolves to the newest term that is **not in the future** (the dropdown carries placeholder years far ahead). The resolved term (label + strm) is echoed in both text and JSON output.
- `--subject` / `--catalog`: SIS needs at least two criteria (the term plus a subject and/or catalog). At least one of the two is required; with neither, the command exits with an actionable message. A subject alone can match more than the server's 50-class ceiling, so add `--catalog` to narrow.
- `--contains` switches the catalog match from exact (`E`) to contains (`C`).
- `--all-seats` includes closed/full sections; the default is **open only** (`SSR_CLSRCH_WRK_SSR_OPEN_ONLY$chk$3=Y`).
- `--all-sections` expands every course that carries a "View All Sections" link. SIS renders only the **first 3 sections per course** by default; the expanded list is what a GE course (e.g. GFH 1000: 12 LEC + 34 TUT) actually needs because the tutorial is what occupies the timetable. Expansion is sequential and costs one extra AJAX request per course (see the cap below). In `--format json` each course carries `sections_complete` and `sections_expanded`; a failed expansion leaves `sections_complete: false` and adds a structured entry to `notes`.
- `--career` is passed through verbatim, but must stay empty by default: sending `UGCU` yields 0 results (verified live).
- `--format text|json`. Text groups sections by type (`LEC:` then `TUT:` / `SUP:` …) when a course mixes them; expanded courses are headed `N sections (all)`, unexpanded ones `N sections (first 3 shown; --all-sections to expand)`.

**Protocol** (verified live 2026-11-23): Class Search is a **two-step AJAX flow** on `SA_LEARNER_SERVICES.CLASS_SEARCH.GBL` (nav `HC_CLASS_SEARCH`). Step 1 POSTs a change event (`ICAJAX=1`, `ICNAVTYPEDROPDOWN=0`, `ICChanged=1`, `ICAction=None`) with the term/subject/catalog/open-only fields to prime component state; step 2 POSTs the same fields with `ICStateNum` / `ICResubmit` taken from step 1 (they arrive as JS assignments in the XML response, not as `<input>` fields; `ICSID` is normally not echoed and the page value is kept) and `ICChanged=-1`, `ICAction=CLASS_SRCH_WRK2_SSR_PB_CLASS_SRCH`. Both requests carry `X-Requested-With: XMLHttpRequest`. The response is `<?xml?><PAGE id='SSR_CLSRCH_RSLT'>` with the real HTML inside CDATA blocks (concatenate them, then parse). When the query would return more than 50 classes the server answers with `PAGE id='SSR_SS_WARNING'` ("over 50 classes") instead of results; the CLI surfaces that as a structured notice telling the user to narrow the criteria.

**Section expansion** (`--all-sections`, verified live 2026-11-23): each course with more than 3 sections carries a `javascript:submitAction_win0(document.win0,'$ICFieldNNN$hviewall$<course-index>')` link in the result payload. The CLI re-POSTs the same win0 form action URL with the search fields + the component state re-read from the **current** payload (`ic_state_fields`) + `ICChanged=-1` + `ICAction=<that hviewall action>` (+ `X-Requested-With: XMLHttpRequest`). The response is the full result page again with that course's sections expanded (AIE 1904: 3 → 8; GFH 1000: 3 → 46 = 12 LEC + 34 TUT). Expanding a course can rewrite the page's `$ICFieldNNN$` action numbers, so the payload is re-parsed before **each** expansion and the target is located by course position/title, never by a remembered action string. The merge keeps earlier expansions even if a later response renders them collapsed again.

**Limitations**: only the **first 3 sections per course** are rendered by default (PeopleSoft pagination); `--all-sections` expands them, at the cost of **one extra AJAX request per expandable course**, sequential, capped at `CLASS_SEARCH_MAX_EXPANSIONS` (default 30) with a 45 s per-request timeout. Courses beyond the cap stay at the first-3 view (`sections_complete: false`); a timeout/network/parse failure on one course degrades to its 3 rendered sections and records `{"kind": "expansion_failed", "course": …, "detail": …}` in `notes` — the command never aborts. There is no separate pagination beyond the expanded list in the observed pages (46 sections came back in one response), but a future course with an unusually large list could still be truncated server-side; treat `sections_complete` as the authority. The term list and result columns come from the live PIA page — a school upgrade can break the anchors, in which case re-run with `SIS_CLI_DEBUG=<dir>` to capture evidence (the initial page and every AJAX response are dumped).

> 本命令只提供课程信息的查询与参考建议；AI 不能保证给出最优选课方案，也不代替用户做决定；连接器是**只读**的——不选课、不加购物车、不交作业、不执行任何 state-changing 交易；最终以 SIS 与教务规定为准。

## Known limits (live-tested 2026-10-05)

- `exam` exam schedule: same mechanism as grades (the term POST); empty until the current term publishes it — data will appear naturally once published.
- `assignments` (per-assignment grades) directly shows "There is no information"; keep under observation; use `grades` for per-term grades.
- Tuition bills (Finances-type) and the shopping-cart read views are not registered (visible in the menu; `raw --post` can scout ahead).
- The `dpr` report currently shows "not available" — viewable only after Request Audit (submitting the report task) generates it; that button is a submit-type action, not auto-executed in v0.3, pending a ruling.
- The PDF-side fields of `identity` depend on pypdf (optional dependency; when missing, that group of fields is marked unavailable).
- Page bodies contain the student's real name and other private data — CLI output goes to the terminal/local machine only, **never into any repository**.
- A school PIA upgrade or a login-page redesign will break the chain: re-run with `SIS_CLI_DEBUG=<dir>` to capture evidence.
- **Write operations (enroll/drop/swap/submit) are deliberately not provided** — misuse has real academic-record consequences; if genuinely needed, explicit user instruction and separate design are required.

## Git Bash note

Raw paths starting with `/` get rewritten by MSYS; prefix the command with `MSYS_NO_PATHCONV=1` or drop the leading slash (relative path).

## Status contract (0.3.1)

`status` is an offline diagnostic. It does not attempt silent login or contact the school. Its JSON separates local evidence from facts that require a server check:

- `authenticated: null`, `authentication_checked: false`: authentication is unknown, including when cached cookies exist. This changes the old boolean field; consumers must not treat null as an authenticated state.
- `session`: `cached_unverified` when a local token loads; `absent_or_unusable` when it does not; `unreadable` when a local error escapes the loader (for example, malformed cookie entries). The loader itself handles invalid JSON, unreadable bytes/files and empty/non-list jars by returning no usable session, so those cases report `absent_or_unusable`; `unreadable` is not a complete inventory of damaged files. An absent token does not say whether credentials could establish a new session.
- `reachable: null`, `network_checked: false`: network reachability is unknown, never inferred from cached state or missing credentials.
- `relogin`: `credentials_available_unverified`, `blocked_missing_credentials`, or `blocked_no_default_account` (multiple accounts stored but no default picked — fix with `cuhksz-cli sis default <name>` rather than re-entering credentials), using the same resolver as normal re-login (including its environment-variable policy). No credentials or raw exception messages are emitted.
- `default_account` / `accounts`: which account automatic re-login would use. `default_account` is a local account label that may contain a student identifier (legacy configs name the account after the username) — documented disclosure; passwords and token values remain the non-disclosure line, and output stays on the local machine.
- `components` lists supported commands, not verified server permissions. Exit 0 means the diagnostic completed.
- A non-object JSON configuration is treated as empty, just like missing or invalid JSON; the original file is not rewritten. Constructing the client may create an empty local home directory, but status does not write configuration or session files.

A subsequent user-requested read may report a network failure (check campus network/VPN), or an expired session that cannot re-login (authenticate interactively, especially after `login --no-store`). Status does not claim to probe session validity, network health, or password validity.

### Changelog

- 0.4.2 (2026-11-23): fix `appt` mislabeling the unit limits — the page keeps both labels in one row and both values in the next, so the old per-line regex paired `Min Total Units` with `18.00` and dropped `Max Total Units`; the parser is now table-based (label cells then value cells, document order) with a text fallback. Max is documented as the term cap (the "term maximum exceeded" error) and Min as the floor; text prints Max first with a one-line cap hint. `--term` on the shared grades/appt/exam term path also accepts the strm code (`2620`), derived from the label. JSON `limits` keeps its existing shape (`{"Max Total Units": "18.00", "Min Total Units": "9.00"}`). **Additive only** — no existing command, flag or JSON key changes.
- 0.4.1 (2026-11-23): `sis search --all-sections` — expands every course's "View All Sections" list via the page's own read-only `$ICFieldNNN$hviewall$<course-index>` AJAX action (sequential, capped at 30, 45 s per request; failure degrades with a structured note). JSON adds per-course `sections_complete` / `sections_expanded` and top-level `all_sections` / `notes`; text marks expanded courses `N sections (all)` and groups mixed `LEC:` / `TUT:` / `SUP:` sections. **Additive only** — the default remains the fast first-3 view; no existing command, flag or JSON key changed.
- 0.4.0 (2026-11-23): new read-only `sis search` (Class Search: courses + sections/times/room/instructor for a term; two-step AJAX; open-only default; advisory disclaimer). Non-breaking — a new command, flag and output shape only; no existing command, flag or JSON key changed.
- 0.3.1: replace optimistic status/silent-login behavior with explicit offline evidence, unknown authentication/reachability, and credential availability. Normal login and query behavior is unchanged.
- 0.3.2 (issue #9 follow-up): split `blocked_missing_credentials` into `blocked_missing_credentials` vs. `blocked_no_default_account`; document the `default_account` label disclosure (may contain a student id). This closes the indistinguishable-failure-mode gap with the bb backend's tri-state contract (issue #16).
- 0.3.0 (2026-11-22): machine-substrate adoption — state moves to `$OWFA_HOME/connectors/cuhksz-cli/homes/<id>/sis/` (resolved through `.owfa/scripts/owfa_home.py`), `home status` / `home migrate` added, and the legacy console entry point was removed (single `cuhksz-cli` entry; `cuhksz-cli sis ...` is the only spelling). `SIS_CLI_HOME` stays as an explicit override.
