# OWFA cuhksz User Notice

For CUHK-Shenzhen users of the alpha test version. Updated 11 November 2026.

[简体中文](USER_NOTICE.zh-CN.md)

The `cuhksz` package connects your OWFA workspace to information you are entitled to access through your own university account. It can retrieve information at your request, organize local files, and support study. This notice explains its scope and data handling. Reading it or joining a test does not authorize arbitrary actions. References to university policies do not establish university or ITSO approval of this tool.

## What you can use it for

- **Find and organize course information.** With the relevant components installed and configured, request announcements, course files, assignment requirements, deadlines, and your own visible grades from Blackboard. Download only the material needed for your study and index it locally.
- **Study with your materials.** Where the course permits AI use, locate sources, request explanations or self-tests, and save personal notes and learning records. Generated answers and assessments of your understanding can be wrong; check them against the original material and your own work.
- **Query your own student records when needed.** If SIS is configured, query your timetable, course history, grades, or enrollment windows. Retrieve only what the current task needs; participating in a test does not require supplying a transcript or extra identity records.
- **Locate academic regulations.** Use the collected rules as a reference. Official systems, university notices, and the responsible university offices remain the source of truth for deadlines, grades, enrollment results, and authoritative interpretations.

These operations can create or update files in your local workspace. Read-only access to university systems does not mean that local files are never changed. Available features depend on the components, configuration, and scope of the particular test.

## Actions that are not supported or not permitted

- Do not use this package to submit assignments, take exams, add, drop or swap classes, or change grades or personal records. Do not ask an agent to bypass these limits through another interface.
- Use only your own account. Do not borrow another person's account, hold credentials on their behalf, retrieve rosters, access information beyond your permissions, or bypass authentication and access controls.
- Do not run site-wide crawls, high-concurrency requests, repeated retry loops, or scheduled bulk downloads. Query at human pace for a current study need. Stop fetching if you encounter rate limits, account anomalies, or an instruction from the university to stop.
- Do not turn retrieved university data into an API, proxy, public collection, or other data service for others. Do not expose unauthorized network services on the campus network.
- Do not bulk-share, sell, or upload course files, lecture recordings, unpublished assessment materials, or other people's personal information to shared spaces or public repositories. Personal study is not blanket permission to copy, upload, or redistribute material; follow course requirements, university rules, and the rights holder's conditions.
- Do not use the tool to breach course AI rules, examination rules, or academic integrity requirements. An AI answer or cognition profile is not evidence that you mastered a topic, completed an assessment, or submitted work.

## Credentials and local files

Enter university credentials yourself in the local terminal's login prompt, for authentication with the university. Do not paste passwords, verification codes, cookies, access tokens, or configuration-file contents into an AI conversation, questionnaire, group chat, or feedback attachment. You do not need to give them to a test helper.

By default, the connectors keep configuration and login sessions in local user directories, normally `~/.bb-cli/` and `~/.sis-cli/`. Custom configuration can change those locations. A default login may also save a password for subsequent login; do not assume that these configuration files are encrypted. A login option such as `--no-store` can avoid saving the password, but the login session can still be saved locally.

Downloaded material, summaries, notes, and learning records can remain in the workspace you select. Protect your device and review backup and synchronization permissions. Credentials, sessions, identity information, grades, and other academic records must not be tracked by Git or uploaded to shared locations. A private repository is not a place to store credentials either.

## What may leave your computer when using AI

Local file storage does not mean all AI processing happens locally. With a cloud AI assistant, text and attachments you provide, and material the assistant reads and submits to the model, may be processed by that service provider. Processing locations, retention, and uses depend on the tool, its terms, and your account settings. A local-model deployment may work differently.

Provide only the material needed for the task and permitted for processing by that tool. Before providing grades, identity details, other people's information, or restricted or unpublished course material, check the applicable requirements. If they are unclear, remove identifying details, reduce the material, or do not provide it. Permission to view a university page does not automatically permit sending its full contents to a third party.

If you separately enable QQ, Lark, email, cloud storage, or another extension, check its recipients, readable pages, and permissions. Installing `cuhksz` does not authorize sending personal academic information to a group chat or shared space.

## Test feedback and questionnaire consent

An OWFA feedback questionnaire may cover the whole project; this notice supplies the additional boundaries for `cuhksz`. Each questionnaire must provide its own complete notice before collecting responses.

The planned feedback concerns AI and information-management experience, broad software and operating-system categories, setup progress and help received, attempted features and task outcomes, source-checking experience, comparisons with previous methods, optional types of saved outputs, reported problems, suggestions, and willingness to continue. The purpose is for project developers to investigate issues and improve OWFA. You do not need to supply your name, student number, major, university credentials, grades, original course files, full logs, screenshots, or learning outputs. A short description with identifying details removed is sufficient; reported issues do not require private evidence.

Participation and optional questions are voluntary. After the questionnaire has explained its actual arrangements, voluntarily submitting it indicates consent to the disclosed handling of that response. This does not authorize additional retrieval of university account data, publication of individual responses, or undisclosed uses. Course reports, public presentations, and quotations are not included in the currently stated improvement purpose; any later proposed use must be explained separately and receive the applicable authorization or consent.

Before a questionnaire is released, its organizers must state:

- the platform, any login requirement, automatically recorded fields, what developers can see, and whether unsubmitted drafts are saved;
- the specific developers who can access responses, retention periods, and deletion or anonymization arrangements;
- a private contact and a feasible way to request access, correction, deletion, or withdrawal of consent, using only the minimum information needed to locate a response;
- whether optional follow-up contact details are stored separately or linked to responses, who can see them, and their retention and disposal arrangements.

Do not assume or promise anonymity before checking those settings and the information collected. If an individual anonymous response cannot be located, the organizers must explain that practical limit rather than promise targeted deletion they cannot perform. Follow-up contact details are optional and only for interview invitations for project improvement; leaving them blank must not block submission. An actual interview needs its own explanation of the activity and arrangements.

Use public GitHub Issues only for general issues that contain no personal information. For troubleshooting, provide the minimum redacted error, steps, and environment details; do not send a complete workspace, credential files, or raw university pages. Agree on what a helper may see before remote assistance.

## Stopping use and managing copies

You can stop queries, disable relevant features, and leave the test. Uninstalling a package does not necessarily delete workspace files, saved connector credentials, or sessions. AI chat history, cloud backups, and submitted questionnaires are separate copies. Manage or request deletion of each through the relevant tool or contact; deleting the workspace alone does not remove all copies.

If you suspect that a password or session has been exposed, stop the relevant operation, follow the university's official account-security guidance, and contact the test organizer privately. Check paths and what you need to retain before cleaning files.

## References

- [Package compliance references and usage rules](COMPLIANCE.md)
- [ITSO campus network rules](https://itso.cuhk.edu.cn/article/383) and [personal data protection policy](https://itso.cuhk.edu.cn/article/374)
- [Cybersecurity Law as amended in 2025](https://www.cac.gov.cn/2025-12/29/c_1768735112911946.htm), [Copyright Law](https://www.ncac.gov.cn/xxfb/flfg/flfg_532/202103/t20210309_50530.html), and [Personal Information Protection Law](https://www.miit.gov.cn/jgsj/zfs/fl/art/2022/art_515a4b20c12f430eab54bb4f56d89f56.html)
