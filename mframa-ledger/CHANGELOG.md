# AI-Native Product Upgrade & Automation Suite

## Autonomous Ingestion & Pending Review Queue
- Implemented `ai_automation.process_inbound_record` with confidence-based auto-commitment (default 85% threshold).
- Verified product catalog matching and automatic oversell risk detection before auto-committing.
- Implemented `pending_drafts` SQLite table with full audit trail and resolution lifecycle (`approve` / `review` / `reject`).
- Added Pending Inbound Inbox badge and triaged review UI in Streamlit workspace with instant product mapping.

## Multimodal Voice & Receipt Ambient Capture
- Added `ai_parser.parse_media_transaction` using Gemini multimodal `Part.from_bytes` for receipt photos (OCR) and audio voice memos.
- Integrated `st.file_uploader` and `st.audio_input` directly into the shop workspace.
- Pre-populates review drafts and pre-selects inventory items matching parsed names.

## AI Advisor & Conversational Shop CFO
- Added `store.get_shop_analytics` calculating real-time sales velocity, Days of Inventory Remaining (DIR), top items, and net cash flow.
- Added `ai_cfo.ask_cfo` for grounded, hallucination-resistant answers to natural language financial questions.
- Added `ai_cfo.generate_executive_briefing` for WhatsApp/bulletin-ready daily briefings with proactive stockout recommendations.
- Added interactive Stockout Risk & Runway Radar table.

## Point-in-Time Snapshotting & Transaction Void Reversals
- Added `ledger_snapshots` SQLite table storing complete immutable shop states (products, inventory quantities, transactions, metadata) before any deletion or reversal.
- Implemented `store.snapshot_ledger`, `store.list_snapshots`, and `store.get_snapshot`.
- Implemented `store.void_transaction` (restricted to `owner` and `manager` roles):
  - Automatically captures pre-mutation immutable snapshots.
  - Reverses stock changes (e.g. restores units to shelf for voided sales, deducts units for voided restocks with oversell checks).
  - Inserts compensating `void` transaction entry with full reason and links to pre-mutation snapshot ID.
  - Updates original transaction note and cycles shop generation.
- Added Void / Reverse Transaction and Ledger Snapshots History expanders to the Streamlit Ledger page.

## Automated SMTP Email Delivery & Invitations
- Created [`email_service.py`](email_service.py) supporting standard SMTP over SSL (`port 465`) and STARTTLS (`port 587`).
- Added automated HTML & plain-text invitation emails sent upon team member invite creation.
- Configurable via environment variables or `.streamlit/secrets.toml` (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`).
- Added in-app SMTP configuration status check and live test email dispatcher under **Settings**.
- Preserves manual code fallback if SMTP is unconfigured or encounters a network failure.

## Bug Fixes & Resiliency Hardening
- Fixed Windows OpenSSL 3 `hashlib.scrypt` malloc failure by setting `maxmem=64*1024*1024`.
- Fixed `AttributeError: 'NoneType' object has no attribute 'upper'` when AI returns `type: None` on ambiguous inputs.
- Resolved module import and draft source passing in `app.py`.
- Added complete French and Spanish translations for all new AI UI strings.
- Expanded test suite to **52 comprehensive passing tests**.

# Interface & reliability upgrade

## Frontend
- Cohesive forest-green and cream design, branded sidebar, hero sections and consistent forms.
- Responsive stock cards with stock status, thresholds and visual indicators.
- Subtle entrance, hover and brand animations; `prefers-reduced-motion` disables motion.
- Clearer describe → review → save guidance, discard-draft action and confirmation feedback.
- Ledger type filters, literal text search, readable column labels, UTC times and original-text inspection.
- Responsive spacing and mobile layout; no external fonts, scripts or image dependencies.
- Theme stored in `.streamlit/config.toml`; reusable rendering in `ui.py`.

## Bugs fixed / backend hardening
- SQLite connections now close after each operation instead of relying on garbage collection.
- Added maximum transaction totals and maximum resulting stock, with validation before mutation.
- Unknown restock costs now display/export as blank amounts, not misleading zero-cost purchases.
- Previewing a restock with an omitted cost now reports unknown cost without failing numeric parsing.
- Stale drafts from before a demo reset are rejected using a database generation identifier.
- Missing critical AI fields are detected in application code even if the model omits its missing-fields list.
- Non-finite model numbers are explicitly rejected.
- Updating a deleted/nonexistent product threshold now fails visibly.
- Out-of-stock products receive attention warnings even with threshold zero.
- Duplicate product names get a readable UI error.
- AI failures preserve the source text and never write records; retry/manual entry remain available.
- CSV formula injection guards retained; record IDs/source text remain available in full export.

## Verification
- `python -m pytest -q`: **35 passed**.
- Covers atomic saves, local persistence, money/quantity validation, duplicate/concurrent submissions, overselling rollback, stock/amount limits, stale reset drafts, export behavior and inventory validation.
- Streamlit UI tests cover manual sale, expense, unknown-cost restock, preview without writes, invalid/unconfirmed saves, inventory creation and page navigation.
- Mocked AI tests cover successful draft review, missing-field detection, malformed output and simulated network failure. They are explicitly **not live accuracy evidence**.
- Chromium smoke check: desktop rendered with zero Streamlit exception panels; at 390px mobile width the document width was also 390px (no horizontal overflow).
- Local screenshot previews captured in `screenshots/`.

## Still needs your account / real-world checks
No live Gemini call was made. Configure your own key/model, verify free-tier terms and run the included evaluation. Cloud hosting, phone-specific interaction testing, real user observation, authentication and production durability remain outside this verification.

# Global accounts & authorization upgrade

## Internationalization
- Removed the GHS-only restriction from the active application and AI contract.
- Country/region, fixed per-shop currency and IANA timezone settings.
- Current tender currencies from Babel/CLDR plus selected additional codes; exact 0/2/3/4-decimal minor-unit handling.
- English, French and Spanish primary interface translations, locale-aware entry/formatting and timezone-aware display.
- No exchange-rate conversion, cross-currency consolidation or jurisdiction-specific tax compliance.
- 18-prompt multilingual/multi-currency optional live evaluation set; not yet run against Gemini.

## Identity and tenant isolation
- Separate `saysale-global.sqlite3` schema for users, sessions, shops, memberships, invitations and tenant-owned records.
- Salted scrypt passwords; opaque hashed session tokens, 8-hour expiry, logout/password-change revocation and persistent login lockout.
- Owner, manager, clerk and viewer checks at the database service layer, not only UI controls.
- Cross-shop product IDs rejected, shop-bound reads/exports, immediate membership revocation and generation-bound drafts.
- Owner-controlled single-use 48-hour email-bound invitation codes, role changes and member removal.
- Audit events, owner-only per-shop demo reset, local operator password-reset command and basic AI-request budgets.
- New DB file permissions use mode 0600 where supported; XSRF/CORS protections remain enabled.

## Compatibility and verification
- Legacy DB left untouched. No implicit ownership assignment/migration.
- The 35 prior-version tests were archived rather than misrepresented as validation of the new multi-tenant architecture.
- New active suite: **45 passed**. Includes authentication, tenant isolation, roles, invitations, concurrent sales, export, currency precision, AI contracts and multilingual Streamlit UI flows.
- Chromium smoke check passed account creation → sign-in → first-shop creation with zero Streamlit exception panels.
- Mobile check: 390px viewport / 390px content width.
- New screenshots: `screenshots/global-login.png`, `global-dashboard.png`, `global-mobile.png`.

## Explicit limitations
Local authentication is real but prototype-grade: no verified email, MFA or automated email recovery, no global distributed signup/abuse protection, no independently audited identity/security infrastructure, no production cloud durability. Use HTTPS outside localhost, synthetic records and unique demo passwords. Read the updated developer guide before any public or real-data rollout. Live Gemini calls still require the user's own API credentials and free-tier checks.
