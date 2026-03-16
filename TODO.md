# TODO

## Completed
- [x] Initialize git repository
- [x] Scaffold FastAPI backend, services, and CLI for week-one MVP
- [x] Add Playwright prefill stub and seed tests
- [x] Commit automation spec and supporting docs
- [x] Implement real LLM integration (Anthropic Claude API)
- [x] Add OpenAI provider option
- [x] Dual-model strategy (extraction vs tailoring)
- [x] Multi-stage resume parsing (section detection + per-section block extraction)
- [x] Resume intake UI with Quill.js rich text editing
- [x] Side-by-side resume comparison and AI improvement features
- [x] PDF layout-mode extraction fix
- [x] Security hardening (localhost binding, XSS escaping)
- [x] Fix deprecation warnings (datetime.utcnow, FastAPI on_event)

## Bugs
- [ ] Double Quill toolbar rendering on resume block editor (Resume Intake tab) — two toolbars appear per block
- [ ] `#blocks-list` element missing from HTML but referenced in `displayBlocks()` JS — guarded with null check, root element should be added back or code removed
- [ ] Tailor results UI is cluttered — clean up layout, spacing, and visual hierarchy for coverage/compliance/uncovered keywords display
- [ ] P2: Skills group labels stripped — KEY SKILLS / TECHNICAL PROFICIENCIES labels lost during section heading strip, renders as unlabeled flat list
- [ ] P2: "Agentic Workflows" orphaned on own line — last item from pipe-delimited group split by source line break
- [ ] P3: Certifications merged on single lines — upstream PDF extraction concatenates distinct certs (e.g., "Comptia Network+ Comptia A+")
- [ ] P3: Trailing spaces before periods — PDF extraction artifacts ("precisely .", "Networker .") not caught by cleanup
- [ ] P3: Contact header uses `~` separator instead of `|` — less polished than original resume
- [ ] P3: Education blocks don't extract structured start_date/end_date during resume intake — dates stay baked into text instead of structured header
- [ ] P2: Polish prompt hallucinating header line — LLM adds "Server, Restaurant Name, Date Range" placeholder when block lacks structured metadata, instead of omitting it
- [ ] P1: Intake reports success on bot challenge pages — Cloudflare/CAPTCHA interstitial captured as job posting with title=None, empty must_haves, no warning to user. Should detect thin extraction (no title, no requirements) and fail or warn instead of "Captured Successfully!"

## In Progress
- [ ] Resume object model and normalized export pipeline (`feat/resume-object-model` branch)
- [x] Update hardcoded models in detect_sections/parse_section to use configured model

## Up Next
- [x] Enhanced compliance heuristics (LLM-powered) — implemented by Clawdbot, OpenAI provider added
- [ ] Job inspection view (see `specs/job-inspection-view.md`)
- [ ] Multi-step form workflows
- [ ] Portal-specific selector catalogs
- [ ] Scoring and ranking engine
