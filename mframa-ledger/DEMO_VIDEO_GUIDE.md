# SaySale Demo Video Guide

This guide is designed for a **2-minute hackathon demo video**. It shows the
problem, the working product, the meaningful AI component, safety controls,
technical approach, limitations, and future potential required by the NYLP AI
Hackathon judging criteria.

## Before recording

### Prepare the demo

- Use synthetic data only.
- Configure `GEMINI_API_KEY` and `GEMINI_MODEL` locally.
- Start the app with:

  ```bash
  python -m streamlit run app.py
  ```

- Create a demo account and one shop.
- Load demo inventory from **Settings → Demo data**.
- Confirm that the shop has products such as Cooking oil, Rice, and Soap.
- Keep a second browser tab or screenshot ready in case the live AI provider is
  unavailable.
- Close unrelated applications, notifications, browser tabs, terminals, and
  personal information before recording.
- Use a readable browser zoom level and record at 1080p if possible.

### Recommended demo data

Use a shop with:

- Currency: USD or GHS
- A product with enough stock for a sale
- A product close to its low-stock threshold
- At least one existing transaction for the AI CFO screen

## Two-minute storyboard

| Time | What to show | What to say | Judging criteria |
|---|---|---|---|
| 0:00–0:12 | Product title and dashboard | “Small-shop owners often use paper, memory, or spreadsheets to track sales and stock. That makes everyday decisions slower and errors more likely.” | Impact |
| 0:12–0:25 | SaySale dashboard, language selector, shop and inventory | “SaySale is a multilingual AI-assisted ledger for small shops. It helps owners record transactions and understand inventory without learning complicated accounting software.” | Impact, feasibility |
| 0:25–0:52 | Record & overview → Text input; enter a realistic sale | “The owner can describe a transaction naturally. SaySale sends the text to Gemini, which extracts the transaction type, product, quantity, price, and currency into a structured draft.” | Innovation, AI role |
| 0:52–1:08 | Review draft and confirm | “The result is never silently posted. The owner reviews the details, confirms them, and only then does SaySale update the ledger and stock atomically.” | Feasibility, responsible design |
| 1:08–1:22 | Show inventory decrease and low-stock card | “The inventory now reflects the sale, and the owner immediately sees low-stock and sales information.” | Impact, feasibility |
| 1:22–1:38 | Submit an incomplete or ambiguous transaction and show Pending Review | “If the AI is uncertain, a product is unknown, a currency does not match, or a sale could oversell inventory, SaySale blocks automatic posting and sends the draft to a human review queue.” | Responsible AI, feasibility |
| 1:38–1:52 | AI Advisor & CFO screen; ask a question about sales or stock | “The grounded AI CFO answers questions using this shop’s actual data, such as which items may run out soon and what action the owner should consider.” | Innovation, impact |
| 1:52–2:00 | Architecture/feature summary and closing screen | “SaySale is practical, tested, and still honest about its limits: live accuracy and production-scale deployment need further validation. Our next step is testing with real shopkeepers and measuring time saved, accuracy, and stock decisions.” | Presentation, feasibility |

## Exact demo flow

### Scene 1 — Establish the problem

Show the SaySale landing page or dashboard.

Say:

> Small-shop owners often manage sales and inventory with paper, memory, or
> spreadsheets. They need a faster way to record what happened and understand
> what needs attention.

Do not spend more than 12 seconds on the problem. Move quickly to the product.

### Scene 2 — Show the product

Show the main dashboard and briefly point out:

- Shop name and currency.
- Inventory cards.
- Sales or ledger summary.
- Language selector if visible.

Say:

> SaySale is a multilingual AI-assisted ledger designed for small shops. It
> combines transaction recording, inventory visibility, and practical guidance
> in one simple workflow.

### Scene 3 — Demonstrate meaningful AI

Open **Record & overview**, choose the text input mode, and enter:

```text
Sold 2 cooking oils at 25 USD each.
```

Click the AI extraction action.

Make sure the video clearly captures:

- The original text.
- The extracted transaction type.
- The matched product.
- Quantity.
- Unit price.
- Currency.
- Confidence or review information.

Say:

> This is not just an AI-generated interface. Gemini performs the core product
> task: converting unstructured text into a structured retail transaction that
> the ledger can validate and use.

If the live response is slow, pause briefly rather than cutting the scene.

### Scene 4 — Demonstrate human control

Show the review step before saving.

Say:

> The owner remains in control. SaySale validates the model response and shows
> a reviewable draft before changing financial or inventory records.

Confirm the transaction and show the updated stock or ledger.

Say:

> After confirmation, the transaction is saved atomically and the product
> quantity is updated.

### Scene 5 — Demonstrate safe failure

Use one of these examples:

```text
I sold cooking oil.
```

or:

```text
Sold 100 cooking oils at 25 USD each.
```

Show that the system requests clarification or routes the draft to Pending
Review rather than making an unsafe change.

Say:

> SaySale is deliberately conservative. Missing information, low confidence,
> unknown products, currency mismatches, and oversell risks are not silently
> accepted. They go to human review.

This scene is essential because it proves that the AI is responsible and not
just an uncontrolled automation layer.

### Scene 6 — Demonstrate the AI CFO

Open **AI Advisor & CFO** and ask a question such as:

```text
Which products are at risk of running out, and what should I reorder first?
```

Show the answer and the inventory/runway information.

Say:

> The AI CFO is grounded in this shop’s real analytics. It can summarize sales,
> expenses, inventory velocity, and runway instead of giving generic business
> advice.

Do not claim that the CFO is a certified accountant or that its advice is
financially guaranteed.

### Scene 7 — Close with evidence and honesty

Show the final dashboard, repository README, or a simple title card containing:

- SaySale name.
- Repository URL.
- Demo URL.
- Team names.
- “84 automated tests passed” only if that remains current at submission time.

Say:

> SaySale is a practical prototype for a real small-business problem. It is
> tested and designed with review gates, but we are transparent about the
> next steps: measuring live AI accuracy with shopkeepers, validating time
> saved, improving local-language support, and moving from prototype storage to
> production-grade infrastructure.

End with:

> SaySale makes everyday shop management clearer, faster, and safer.

## Optional multimodal insert

If the live demo is stable, replace part of Scene 3 or add a short insert:

1. Open the receipt upload or voice input.
2. Upload a synthetic receipt image or record a short synthetic voice note.
3. Show the extracted draft.
4. Return to the review screen.

Narration:

> The same workflow also supports receipt photos and voice notes, so the owner
> can use the input method that fits the shop's daily routine.

Do not let this optional insert make the video longer than two minutes. The
text-based flow is the safest primary demonstration.

## What the video must prove

The recording should visibly prove all four judging criteria:

### Innovation

- AI handles text, image, or audio transaction extraction.
- The product combines extraction, inventory, safety routing, and grounded
  business guidance.

### Impact

- The target user is a small-shop owner.
- The product addresses bookkeeping friction and stockout visibility.
- The owner can use natural language rather than a complex accounting form.

### Feasibility

- The application works end to end.
- A confirmed transaction updates the ledger and inventory.
- Unsafe AI output is blocked or routed to review.
- The product has a clear path to testing and deployment improvements.

### Presentation

- The problem is explained simply.
- The main user journey is shown without unnecessary screens.
- The AI method is explained in plain language.
- Limitations and future improvements are stated honestly.

## Recording and editing rules

- Keep the final video between **90 seconds and 2 minutes** unless the
  submission form specifies another limit.
- Use one continuous primary demo where possible.
- If editing, do not hide failed attempts or alter evidence of product behavior.
- Keep cursor movement deliberate and slow enough to follow.
- Zoom in on extracted fields and review decisions.
- Add short captions such as `AI extraction`, `Human review`, and
  `Inventory updated`.
- Use captions/subtitles for accessibility.
- Avoid background music that competes with narration.
- Do not show API keys, passwords, email addresses, real customer data, or
  private database files.
- Do not claim live accuracy, production readiness, user adoption, or impact
  metrics that have not been measured.

## Final upload checklist

- [ ] Product name is visible.
- [ ] Problem and target users are explained.
- [ ] A working product flow is shown.
- [ ] The AI component is demonstrated, not merely described.
- [ ] Review and safety behavior is shown.
- [ ] Inventory or ledger impact is visible.
- [ ] AI CFO or another differentiated feature is shown.
- [ ] Technical approach is explained simply.
- [ ] Limitations and future improvements are included.
- [ ] Repository and demo links are readable.
- [ ] Team names and contributions are documented in the README.
- [ ] No secrets or personal data appear in the recording.
- [ ] The final repository state matches the demonstrated product.
