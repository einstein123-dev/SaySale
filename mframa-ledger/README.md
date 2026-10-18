# SaySale

**A multilingual, AI-assisted sales and inventory ledger for small shops.**

SaySale helps shop owners record transactions using ordinary language, receipt
photos, or voice notes. The application extracts transaction details, shows the
operator a reviewable draft, and updates sales and inventory only after the
appropriate safety checks and confirmation.

> **Hackathon prototype:** SaySale is designed for demonstration and
> experimentation. It is not production-certified accounting, tax, identity,
> or financial infrastructure.

## Hackathon submission

| Item | Details |
|---|---|
| Product | SaySale |
| Problem area | Small-shop bookkeeping and inventory visibility |
| Working product | **Add your deployed URL here** |
| Demo video | **Add your video URL here** |
| Repository | **Add the public repository URL here** |
| Team | **Add team member names and roles here** |

See [DEMO_VIDEO_GUIDE.md](DEMO_VIDEO_GUIDE.md) for the timed storyboard,
narration, recording flow, and final upload checklist.

### One-minute pitch

> Small-shop owners often manage sales and inventory with memory, paper, or
> spreadsheets. That makes it easy to lose track of stock, expenses, and cash
> flow—and existing accounting tools can be too complex or language-dependent.
>
> **SaySale** is a multilingual AI-assisted ledger built for small shops. An
> owner can type what happened, speak a voice note, or upload a receipt photo.
> SaySale uses Google Gemini to extract the transaction type, product, quantity,
> price, and currency, then shows a clear review screen before updating the
> ledger and inventory. It also provides low-stock and inventory-runway
> guidance, plus a grounded AI CFO that answers questions using the shop's real
> data.
>
> AI is meaningful here because it converts messy text, audio, and images into
> structured business records—not because it was used to write the code. We
> validate the AI response, block currency mismatches and overselling, and send
> incomplete or low-confidence results to a human review queue. Owners can
> always use manual entry.
>
> Our prototype is practical, tested, and designed around a real need: helping
> small-shop owners spend less time recording transactions and make better
> stock decisions. The current challenges are live AI accuracy, provider
> availability, and production-scale deployment. Next, we would test SaySale
> with shopkeepers, measure time saved and extraction accuracy, improve local
> language support, and add durable cloud storage and stronger identity
> protection. SaySale's goal is simple: make everyday shop management clearer,
> faster, and safer.

## Why this is AI-powered

AI is used as part of the product workflow, not only as a development tool:

1. **Natural-language extraction** — Gemini extracts sales, expenses, and
   restocks from ordinary text.
2. **Multimodal capture** — Gemini processes receipt images and voice recordings.
3. **Structured output** — Responses are validated against a Pydantic schema.
4. **Safety and confidence routing** — Missing fields, low confidence,
   unknown products, currency mismatches, and oversell risks are routed to
   human review.
5. **Grounded shop advisor** — The AI CFO answers questions using the selected
   shop's actual sales, expenses, inventory, and runway data.
6. **Executive briefings** — SaySale can generate concise daily operational
   summaries and stockout recommendations.

The AI does not directly receive database access. The application validates
model output and the storage layer enforces authorization, inventory rules,
currency rules, and transaction atomicity.

## Main features

- Text-based transaction entry with a **describe → review → save** workflow.
- Receipt and invoice image extraction.
- Voice memo transaction extraction.
- Sales, expenses, and restocks.
- Confidence-based automatic routing with a Pending Review inbox.
- Product matching and oversell protection.
- AI Advisor and CFO-style natural-language questions.
- Inventory runway and low-stock guidance.
- English, French, and Spanish primary interfaces.
- Per-shop currency and IANA timezone settings.
- Currency-aware decimal precision, including zero-, two-, three-, and
  four-decimal currencies.
- Owner, manager, clerk, and viewer roles.
- Separate shop data with backend tenant and membership checks.
- Password hashing with salted scrypt.
- Revocable, expiring server-side sessions.
- One-time, email-bound invitation codes.
- Authenticated webhook intake with idempotency and pending review.
- Audit events and point-in-time ledger snapshots before reversals.
- Void/reversal support with inventory compensation.
- CSV export with formula-injection protection.
- Responsive Streamlit interface with light and dark themes.

## Product workflow

### Manual or AI-assisted transaction

1. Sign in and select a shop.
2. Choose text, voice, receipt, or manual entry.
3. Describe the transaction.
4. Review the extracted type, product, quantity, price, currency, and
   confidence.
5. Correct or discard the draft if necessary.
6. Confirm the transaction.
7. SaySale updates the ledger and inventory atomically.

### Automated inbound event

Inbound webhook events are authenticated, deduplicated, stored in an event
queue, and processed by the AI worker. Unsafe or ambiguous results enter
Pending Review. Webhook events are not automatically posted merely because
they were received.

## Responsible AI and safety design

SaySale is intentionally conservative around financial and inventory mutations.

- AI output is treated as untrusted input.
- Structured responses are validated before use.
- The model is instructed not to invent quantities, prices, currencies, or
  transaction types.
- Missing critical fields create a reviewable draft.
- Low-confidence results do not pass the automatic commit gate.
- Unknown products are not silently created.
- Currency mismatches are blocked; no exchange-rate conversion is performed.
- Overselling is rejected.
- Users can use manual entry without AI.
- AI processing requires explicit user consent in the transaction workflow.
- The AI CFO is instructed to answer only from the supplied shop context.
- Synthetic data should be used for demonstrations; do not upload real
  customer information.

Model confidence is a routing signal, not a proof of calibrated accuracy.
Live model accuracy has not been established by the included mocked tests.

## Technology stack

- **Python 3.11+**
- **Streamlit** — primary web interface
- **FastAPI + Uvicorn** — inbound webhook API
- **SQLite** — prototype persistence
- **Google Gemini API** via `google-genai`
- **Pydantic** — model-output validation
- **Pandas** — ledger and chart presentation
- **Babel** — internationalized currency and number formatting
- **Pytest** — automated tests

## Run locally

### Requirements

- Python 3.11 or newer
- A Gemini API key and model name for live AI features

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open the local URL printed by Streamlit. Create an account, create a shop,
choose its country, currency, and timezone, then add products or load the
synthetic demo inventory from **Settings → Demo data**.

There are no default credentials.

## Configure Gemini

Set the following values in the environment or in Streamlit secrets:

```text
GEMINI_API_KEY=your-key
GEMINI_MODEL=your-model
```

For PowerShell, use values only in your local session:

```powershell
$env:GEMINI_API_KEY = "your-key"
$env:GEMINI_MODEL = "your-model"
```

Never commit API keys, `.streamlit/secrets.toml`, databases, exports, or real
records. These files are excluded by `.gitignore`.

Manual transaction entry works without Gemini.

## Run tests and checks

Run the active test suite:

```bash
python -m pytest -q
```

Compile-check the Python files:

```bash
python -m compileall -q .
```

The tests cover authentication, roles, tenant isolation, invitations,
concurrency, inventory and currency validation, exports, AI contracts,
pending-review workflows, webhooks, and selected Streamlit journeys.

### Optional live AI evaluation

After configuring `GEMINI_API_KEY` and `GEMINI_MODEL`:

```bash
python evaluate.py
```

The evaluator uses the synthetic cases in `evaluation.json` and writes
`evaluation-results.json`, which is ignored by Git. It reports development and
held-out extraction behavior, field accuracy, latency, and basic review-gate
metrics.

This is a small synthetic benchmark. It is not proof of calibrated confidence,
real-world accuracy, user satisfaction, or production safety. Do not tune the
system against the held-out cases.

## Roles and permissions

| Capability | Owner | Manager | Clerk | Viewer |
|---|:---:|:---:|:---:|:---:|
| View shop, inventory, ledger, and exports | Yes | Yes | Yes | Yes |
| Record sales | Yes | Yes | Yes | No |
| Record expenses and restocks | Yes | Yes | No | No |
| Add products and change thresholds | Yes | Yes | No | No |
| Read audit events | Yes | Yes | No | No |
| Invite members and change roles | Yes | No | No | No |
| Change shop settings and reset demo data | Yes | No | No | No |

These permissions are enforced in the backend service layer, not only by
hiding UI controls.

## Repository structure

| File or directory | Purpose |
|---|---|
| `app.py` | Streamlit UI, navigation, forms, AI workflow integration |
| `store.py` | SQLite schema, authorization, tenant checks, atomic mutations |
| `auth.py` | Password hashing, session and invitation helpers |
| `ai_parser.py` | Structured text, image, and audio extraction |
| `ai_automation.py` | Confidence gates and inbound automation |
| `ai_cfo.py` | Grounded shop analytics assistant and briefings |
| `webhook_api.py` | Authenticated FastAPI inbound endpoint |
| `intl.py` | Currency precision, locale and timezone helpers |
| `i18n.py` | English, French, and Spanish translations |
| `ui.py` | Shared presentation, charts, cards, and CSV helpers |
| `tests/` | Active automated test suite |
| `screenshots/` | Local desktop and mobile interface previews |
| `DEVELOPER_GUIDE.md` | Detailed operations, architecture, and deployment notes |
| `CHANGELOG.md` | Feature and verification history |

## Current limitations

SaySale is a prototype and has important limitations:

- SQLite is intended for a single-instance demonstration, not horizontal
  scaling.
- Email ownership verification, MFA, and automated password recovery are not
  configured.
- There is no production-grade abuse prevention or distributed rate limiting.
- There is no external audit sink, database encryption-at-rest service, or
  automated backup and restore system.
- No foreign-exchange conversion is performed.
- Returns, credit sales, tax calculations, cost-of-goods accounting, and
  multi-currency consolidation are not implemented.
- Country and currency selection does not provide legal or tax compliance.
- Live Gemini accuracy and user acceptance have not yet been measured.
- AI provider availability, quotas, latency, and pricing remain external
  dependencies.

Use synthetic data for the hackathon demo. Before real users or financial
reliance, add a managed durable database, protected backups, monitoring,
verified identity and recovery flows, operational security controls, and
domain-specific accounting review.

## Privacy and security notes

The application is designed to avoid storing plaintext passwords and raw
session tokens in the database. It uses parameterized SQL, shop membership
checks, bounded inputs, session expiry, lockout handling, and audit events.

Nevertheless, the operator controls the local database and configured AI
account. Do not use customer or personally identifiable information in the
demo. Use HTTPS for any non-local deployment and review the deployment
configuration before exposing the application publicly.

## Third-party services and acknowledgements

SaySale uses the following third-party components:

- Google Gemini API through the `google-genai` package.
- Streamlit, FastAPI, Uvicorn, Pydantic, Pandas, Babel, `tzdata`, and Pytest.

Review the licenses and terms for each dependency and acknowledge any
additional datasets, templates, icons, fonts, or services used in the final
submission. No proprietary customer data is required by the included demo
workflow.

## Team contributions

**Replace this section before submission.**

| Team member | Role | Contribution |
|---|---|---|
| Add name | Team lead / product | Add concrete contribution |
| Add name | AI/ML | Add concrete contribution |
| Add name | Backend | Add concrete contribution |
| Add name | Frontend/UI/UX | Add concrete contribution |
| Add name | Documentation/presentation | Add concrete contribution |

Every listed member should have made a meaningful contribution.

## License

**Add the project license here before public submission.** Confirm that the
license is compatible with all third-party code, assets, APIs, and datasets
included in the repository.
