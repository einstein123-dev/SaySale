# SaySale — developer and operator guide

## What changed

SaySale supports independent shops with country/region, currency and timezone settings; English, French and Spanish primary interfaces; local email/password accounts; and server-enforced shop roles.

This is a **working prototype, not production-certified identity or accounting infrastructure**. Country configuration does not imply local tax/legal compliance. No email verification service, automated recovery email, exchange-rate service, payment integration or production cloud resource has been configured.

## 1. Install and run

Use Python 3.11+ inside the project directory:

```bash
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows PowerShell instead:
# .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open the printed local address. Create an account, sign in, create a shop and select its country/region, currency and timezone. There are **no default administrator credentials**. The user creating a shop becomes that shop’s owner, not a global administrator. Any signed-in user may create an independent shop.

Choose **English / Français / Español** in the sidebar. Language is an in-session preference, not a persisted user setting. Switching language or shop discards an unsaved draft to prevent accidental reuse. Primary interface labels, navigation, forms and monetary formatting are translated. Some backend diagnostics, AI clarification text, audit actions and CSV headers remain English. User-entered product names are never automatically translated. Get native-speaker review before a public multilingual launch.

## 2. Configure a shop and record a sale

1. Open **Settings → Demo data**. Acknowledge deletion and reset this shop, or add products through Inventory. Reset only affects the selected shop; membership and audit records remain.
2. The synthetic stock starts with Cooking oil: 10, Rice: 20 and Soap: 30.
3. Open **Record & overview → Create manual draft**.
4. Choose sale, Cooking oil, quantity 6 and a unit price in the selected interface’s number format.
5. Confirm the shop currency and the review checkbox. Preview the total, then confirm/save.
6. Stock should fall to 4 and a low-stock alert should appear.
7. Repeat a sale with more stock than available. It should fail without changing money or stock.
8. Restart locally and confirm persistence.

French/Spanish decimal entry uses a comma; English uses a decimal point. For example EUR 25.50 is entered as `25,50` in French/Spanish and `25.50` in English. The form shows a locale-specific number example. Whole-unit quantities use ungrouped integer digits. The supported format is based on the chosen language; there is not yet a separate regional-locale selector (e.g. en-US vs en-IN).

Currency is fixed when a shop is created to avoid reinterpreting existing amounts. Create a separate shop for another currency. Countries and currencies are independently selected; inspect both before creation. The currency list uses current tender currencies from installed Babel/CLDR plus a small set of additional supported codes. This is broad international support, not a promise to cover every historical currency or cryptocurrency.

Money uses integer minor units with Babel’s currency precision: e.g. JPY 0 decimal places, USD/EUR/GHS 2, KWD/BHD 3, CLF 4. No foreign exchange conversion is performed. An AI draft explicitly naming another currency is blocked and must be discarded/corrected, not silently converted. Dates are stored as UTC and displayed in the shop’s IANA timezone, including daylight-saving transitions. CSV timestamps stay UTC.

Unknown restock cost is stored as **NULL amount and NULL unit price**, not zero. The ledger and CSV leave it blank. Restocks are separate from general expenses, and sales minus expenses is not labelled profit. No returns, cost-of-goods accounting, credit sales, tax calculations or multi-currency consolidation are implemented.

## 3. Roles and authorization

| Action | Owner | Manager | Clerk | Viewer |
|---|:---:|:---:|:---:|:---:|
| View shop, inventory, ledger; download CSV | ✓ | ✓ | ✓ | ✓ |
| Record sales | ✓ | ✓ | ✓ | — |
| Record expenses / restocks | ✓ | ✓ | — | — |
| Add products / change stock thresholds | ✓ | ✓ | — | — |
| Read recent audit events | ✓ | ✓ | — | — |
| Invite/remove members or change roles | ✓ | — | — | — |
| Change shop settings / reset demo stock | ✓ | — | — | — |

These are backend checks in `store.py`, not merely hidden buttons. Every shop read/write resolves the current session and membership from SQLite. Tenant IDs and foreign product IDs cannot confer authority. Membership changes take effect on the next backend operation; already downloaded/exported data or an already rendered page cannot be recalled. A member may belong to multiple shops with different roles.

The creator’s owner role cannot be changed or removed through this prototype. Ownership transfer, multiple-owner management, global-admin UI, account deletion and shop deletion are not implemented.

### Invite another user

1. As owner, open **Team** and enter the teammate’s intended account email and a manager/clerk/viewer role.
2. Generate a cryptographically random, one-time invitation code. Only its hash is stored.
3. Copy and deliver the code through a trusted channel. **No email is sent automatically.** It expires after 48 hours. Do not put it in public screenshots or URLs.
4. The person creates an account with that email, signs in, then opens **Account → Join shop** and submits the code.
5. Owner can change roles, remove members and revoke outstanding invitations. Regenerating an invitation for an email invalidates its previous code.

Because email ownership is not independently verified, the invitation’s secrecy and your out-of-band identity check matter. Do not assume a matching registered email proves the person’s identity. For production, integrate verified email and robust account recovery before trusting these identities.

## 4. Local authentication details and limits

Implemented:

- Per-user random salts and scrypt password hashes. No plaintext passwords in SQLite.
- Password length 12–128 characters; parameterized SQL; bounded inputs.
- Random server-side sessions; only SHA-256 session-token hashes stored in SQLite.
- Eight-hour absolute session expiry, explicit logout revocation and all-session revocation on password change/reset.
- Persistent per-email sign-in lockout: five failed attempts trigger a five-minute lockout. Unknown accounts get a generic sign-in error.
- No session tokens in URL parameters or browser localStorage. The raw session token lives in Streamlit server-side session state. A refresh/new tab may require signing in again.
- Streamlit XSRF protection and CORS protection remain enabled.
- New SQLite files are created with owner-only file permissions where supported by the operating system. Protect the parent directory and backups too.
- Selected-shop audit events record transaction writes, inventory changes, invitations, role changes, settings changes and demo resets. Audit records are not tamper-proof against someone who controls the database file. UI shows the latest 200.

Limitations to address before a real public deployment:

- No verified email, MFA, automatic forgot-password email, breached-password checks or federation.
- Open signup and shop creation are not globally rate-limited; per-email lockout is not distributed IP/device abuse protection and can be used to deny a known account temporarily.
- No persistent-cookie “remember me” flow or idle-session timeout beyond the absolute expiry.
- No database encryption at rest, external audit sink, backup automation or independent security audit.
- SQLite is intended for a single-instance prototype, not horizontally scaled hosting. The operator controls all account and shop data in the database.
- The app shares one operator-configured AI account across authorized shops. Application budgets reduce abuse but do not guarantee provider spend or quotas.

**Use HTTPS for all non-local deployments**, restrict network/admin access, apply OS-level file permissions and use a durable volume. Never disable XSRF/CORS as a shortcut to make a proxy work. The public preview is a temporary synthetic-data demonstration, not a place for real business records or a password reused elsewhere.

### Forgotten-password operator recovery

There is no public reset link. A trusted operator with direct filesystem access can run:

```bash
python admin.py reset-password person@example.com
```

It prompts using `getpass`, updates the password hash and revokes all account sessions. Verify the requester’s identity separately before doing this. Never expose this command through a web endpoint. Back up the database first. The command uses the same `SAYSALE_DB_PATH` setting as the app.

## 5. Data storage, upgrades and backups

The new database is `saysale-global.sqlite3` next to the code. To select a durable path, set an environment variable **before launching the process**:

```bash
export SAYSALE_DB_PATH='/absolute/path/to/persistent/saysale-global.sqlite3'
# PowerShell:
# $env:SAYSALE_DB_PATH='C:\persistent\saysale-global.sqlite3'
```

Create and protect the parent directory first. This environment variable is read at module startup, not dynamically from Streamlit secrets. Restart after changing it. Do not put the DB in a web-served/static directory. All users, shops, sessions, invitations and ledger records live in this one file.

Audit snapshots are stored in the same SQLite database as the live ledger. They support review of prior states but are not independent backups and do not protect against loss or tampering of that database. Back up the full SQLite database while the app is stopped; CSV is only a ledger export, not an account/inventory restore format. Protect backups as sensitive data. Test restoration. Ephemeral hosting can delete accounts as well as ledgers; use durable storage or keep this local. Streamlit Community Cloud’s local filesystem should not be treated as production persistence.

### Previous single-shop Ghana version

The previous `ledger.sqlite3` is **not overwritten or automatically exposed**. Old backend code and disabled tests are archived under `legacy/`. New users cannot access the old unowned records through the app. Automatic migration would need an explicit owner assignment and a reconciliation of stock balances and restock costs, so it is intentionally not performed.

If you need old demo data, keep the original DB and previous ZIP as backups; export using the previous version in a separate local directory. A developer must review a migration into an explicitly chosen GHS shop. Do not simply rename the old DB to the new filename; schemas differ. No built-in CSV importer is supplied.

## 6. Configure real Gemini extraction — your account required

1. Create your own [Google AI Studio](https://aistudio.google.com/) account/API key if eligible in your region.
2. Check current [pricing and free-tier terms](https://ai.google.dev/gemini-api/docs/pricing) and choose an exact free-eligible model ID supporting [structured output](https://ai.google.dev/gemini-api/docs/structured-output).
3. Do not attach billing for the zero-tool-spend prototype. Eligibility/quotas change; the app does not enforce provider billing.
4. Add environment variables, or create `.streamlit/secrets.toml` locally:

```toml
GEMINI_API_KEY = "YOUR_REAL_KEY"
GEMINI_MODEL = "EXACT_FREE_ELIGIBLE_MODEL_ID"
```

These are placeholders, not working credentials. Never commit this file or paste a real key into source control. `.env` files are ignored but **not automatically loaded**. Restart after changing settings. The sidebar’s “AI configured” label does not prove connectivity.

The API receives only the synthetic transaction text and the shop currency, not the account password/session, membership data or whole ledger. Do not place personal/customer data in source text. Provider terms may allow training use of free-tier inputs. Consent to the external request is explicit in the UI.

Backend AI budgets: **5 attempts per user per rolling minute and 50 attempts per shop per rolling 24 hours**. Failed external requests also consume attempts. Viewers cannot invoke AI through the app. Budgets are local-DB controls, not guaranteed provider cost controls; many shops can still consume aggregate provider quota.

Without credentials or quota, manual entry remains available with the same authorization and transaction validation. Never present manual/mocked extraction as live AI.

### Generic inbound webhook automation

The generic webhook adapter accepts text events from a POS, messaging bridge or integration you operate. It is not a WhatsApp/SMS integration by itself; configure the provider to call the API, or deploy a provider-specific adapter that verifies that provider's signature. Secrets are scoped to a shop, stored as hashes, rotated/revoked by the shop owner, and displayed only when generated. Provider event IDs are unique per shop, making retries idempotent. Accepted events persist to SQLite before a `202` response. A single API process drains the queue, applies existing per-user/per-shop AI request limits, and creates **pending review drafts only**. It never commits a sale or adjusts inventory automatically.

1. In the SaySale UI, open **Settings → Inbound Webhook & Automation Simulator** and generate a secret. Copy it immediately; rotating invalidates the old secret.
2. Launch the webhook API separately from Streamlit, using the same database path and Gemini environment variables. Run one worker only:

```powershell
$env:SAYSALE_DB_PATH = 'C:\persistent\saysale-global.sqlite3'
$env:GEMINI_API_KEY = 'YOUR_REAL_KEY'
$env:GEMINI_MODEL = 'EXACT_CONFIGURED_MODEL_ID'
python -m uvicorn webhook_api:app --host 127.0.0.1 --port 8000 --workers 1
```

Both processes must use the same durable SQLite file and be on the same host. Do not place this SQLite setup behind multiple API workers or multiple app replicas. For public access, place a hardened HTTPS reverse proxy in front of the local API and configure firewall/rate limits; never expose the API over plaintext HTTP. The endpoint rejects request bodies over 16 KiB. The sample includes credential authentication and event-ID deduplication, not provider signature verification, IP allowlists, encryption-at-rest, or distributed queueing.

3. Configure the external sender to POST this JSON, with the generated secret in `X-SaySale-Webhook-Token`:

```http
POST https://YOUR-DOMAIN/webhooks/YOUR_SHOP_ID/transactions
Content-Type: application/json
X-SaySale-Webhook-Token: YOUR_GENERATED_SECRET

{"event_id":"unique-provider-event-id","source_channel":"external_pos","text":"Sold 2 cooking oils at 25 GHS each"}
```

The sender must reuse the same `event_id` when retrying a timed-out delivery. `202` means the event was durably accepted; a duplicate returns the existing event and status. Open **Record & overview → Pending review** to inspect extracted drafts. The owner can see event status/error in Settings and retry failed events. If AI credentials are unavailable or a budget is reached, the event is marked failed for an explicit retry. Long-running `processing` events are made claimable again after two minutes. Restrict logs and event payload access because source text may contain sensitive business information.

Before connecting a real provider, implement and test that provider's signature/timestamp verification, request-rate limits at the proxy, retry/backoff behavior and privacy/retention policy. Use a managed queue and database before horizontal scaling. Validate shop IDs and deduplication in staging with synthetic records first.

## 7. Test and measure

```bash
python -m pytest -q
```

The active suite tests password hashing, login/session expiry/logout, lockout, password-change revocation, invitations, roles and immediate revocation, cross-shop reads/product IDs, atomic stock/ledger writes, duplicate/concurrent saves, overselling rollback, per-currency precision, timezone display, AI budgets, CSV safety and Streamlit UI journeys. Run the command above for the current result; historical test counts are intentionally omitted. The prior version’s disabled tests are archived, not counted as tests of the new architecture.

A Chromium smoke check also exercised account creation → sign-in → first-shop creation, with no Streamlit exception panels. At a 390px mobile viewport, document width was 390px. These are not a penetration test or comprehensive device testing.

**Live Gemini was not tested:** no user API credentials were supplied. Mocked contract tests are explicitly not AI accuracy evidence.

Inventory runway uses a trailing window (30 days by default) to calculate daily sales velocity. Sales, expenses and net cash summary totals remain lifetime totals. Restock guidance is deterministic: target the larger of the shop's minimum-stock threshold or 14 days of average recent demand, then subtract current stock. Products below threshold without recent sales are flagged for review without inventing an order quantity. This is an explainable heuristic, not an AI demand forecast; supplier lead times, seasonality, pack sizes and cash budget are not modeled. `evaluation.json` has 18 synthetic prompts spanning English, French, Spanish and several currencies, with 10 development and 8 held-out cases. Configure API environment variables, then run:

```bash
python evaluate.py
```

The runner makes real API requests and writes `evaluation-results.json` with per-field and exact-case accuracy, success/latency, and separate development versus held-out metrics. It also counts expected-review cases that pass a basic extraction confidence gate. That count is not an unsafe-save rate: the evaluator has no product catalog, stock level, or live authorization context, and model confidence is not proven calibrated. The report is ignored by Git. This operator tool runs outside the signed-in UI, so it does not consume local AI budgets; it is still subject to provider quotas. Do not tune prompts on the held-out set. Item-name accuracy, user correction rate, and unaided task completion require a canonical naming scheme and observed user trials. Test each language/currency you intend to claim; the tiny synthetic set is not proof of global model accuracy.

Manually verify on target devices:

- Create owner/shop A; invite clerk and viewer. Clerk can save sales but not expenses/restocks; viewer can only read/export.
- Create unrelated shop B; verify A users cannot list/access B or submit B’s product IDs.
- Change/revoke membership while another session is open; confirm the next action is denied.
- Preview and confirm EUR input `25,50` in French; JPY rejects fractional amounts; KWD accepts three decimals.
- Verify timezone differences, currency mismatch blocking and no automatic conversion.
- Reset A; confirm B and audit history remain, and A’s previous drafts cannot save.
- Test provider outage, malformed AI output, network disconnect, quota failures and explicit confirmation.
- Inspect backups, logs and staging before committing: no passwords, keys, databases or real records.

## 8. Deployment and what you must do yourself

You must supply your own accounts, domain/hosting choices, secrets, durable storage and operational security. No paid infrastructure has been created.

For a temporary synthetic demo, use the local app or follow [Streamlit deployment](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy) and [secrets management](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management). Push only source/configuration, select `app.py`, install dependencies and set secrets in the hosting UI. Keep TLS and websocket support working. Timebox optional deployment; don’t sacrifice the local journey.

Before real users/data:

- Arrange verified email, recovery, abuse controls, terms and privacy handling with legal/security review.
- Prefer audited managed identity for a public service; migrate password/session flows carefully rather than assuming this prototype is production-ready.
- Provide durable transactional storage/backups, monitoring and tested restoration; adopt a managed relational DB before multi-instance deployment.
- Review audit retention, invitation identity checks and administrative recovery policy.
- Validate the workflow with consented shopkeepers across target regions/languages; validate local accounting requirements separately.
- Add returns/reversals and a proper audit/accounting model before relying on these records financially.

## Architecture

- `app.py`: multilingual Streamlit UI, login/signup, shop routing and role-aware controls.
- `store.py`: authoritative sessions, tenant checks, role permissions and atomic data operations.
- `auth.py`: scrypt and token/email helpers.
- `intl.py`: current currency metadata, minor-unit arithmetic and timezone formatting.
- `i18n.py`: primary English/French/Spanish interface translations.
- `ui.py`: shared design, escaped stock cards and CSV formatting.
- `ai_parser.py`: structured extraction; no database access.
- `admin.py`: local operator-only password recovery.
- `tests/`: active security, backend and UI tests.
- `legacy/`: archived pre-authentication backend/tests; not used by the running app.
