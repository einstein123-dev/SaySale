# SaySale Presentation Script

**Target duration:** 80 seconds

Use synthetic shop data. Keep credentials, customer records, and unrelated tabs
off screen.

## 1. Explain the problem simply — 0:00–0:10

**Show:** Dashboard with synthetic records.

**Say:**

> Small shops need a reliable way to record sales, expenses, and stock. Paper
> notes and disconnected spreadsheets make it harder to keep those records
> consistent.

## 2. Show the main features — 0:10–0:24

**Show:** Record & overview, inventory cards, then the ledger.

**Say:**

> SaySale records sales, expenses, and restocks; tracks inventory; and provides
> searchable ledger exports. Shops can use different currencies, languages,
> and team roles.

## 3. Explain the technical approach — 0:24–0:40

**Show:** Project files, then save a reviewed transaction and show the stock
change.

**Say:**

> Streamlit provides the interface, and SQLite stores the prototype data.
> `store.py` checks permissions and validates each write. A sale updates the
> ledger and stock in one database transaction, preventing partial updates.

## 4. Demonstrate the AI component — 0:40–1:04

**Show:** Parse “Sold 2 cooking oils at 25 USD each,” review the structured
draft, then show an incomplete example in Pending Review.

**Say:**

> `ai_parser.py` sends consented text, images, or audio to Gemini and validates
> the structured response. The automation layer checks required fields,
> confidence, currency, product matching, and stock risk. Unclear drafts go to
> human review; AI never writes directly to the ledger.

## 5. Share challenges, limitations, and future improvements — 1:04–1:20

**Show:** CFO analytics, then the SQLite or webhook component.

**Say:**

> Provider latency and extraction errors still need measurement. SQLite is for
> a single-instance prototype, and the app does not convert currencies.
> Future work includes measured language testing, durable managed storage,
> protected backups, and production monitoring.

## Recording checklist

- [ ] Keep the complete presentation within 80 seconds.
- [ ] Use synthetic shops, products, and transactions.
- [ ] Configure Gemini before a live AI demo; otherwise label the capture as
      prerecorded.
- [ ] Do not show credentials, private records, or raw provider responses.
