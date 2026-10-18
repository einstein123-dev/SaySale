"""Autonomous Ingestion Pipeline & Webhook Automation Engine.
Processes inbound text, audio, and receipt images with confidence-based auto-commitment.
"""
import uuid
import secrets
import store
import ai_parser


def process_inbound_record(
    shop_id: str,
    user_token: str,
    raw_text: str | None = None,
    media_bytes: bytes | None = None,
    mime_type: str | None = None,
    source_channel: str = 'whatsapp',
    api_key: str | None = None,
    model: str | None = None,
    auto_commit_threshold: float = 0.85
) -> dict:
    """Process inbound shop data with confidence-based auto-commitment or triage routing."""
    snap = store.snapshot(user_token, shop_id)
    shop = snap['shop']
    products = {p['name'].strip().lower(): p for p in snap['products']}
    currency = shop['currency']
    
    # 1. Parse using AI
    store.authorize_ai(user_token, shop_id)
    if media_bytes and mime_type:
        drafts = ai_parser.parse_media_transaction(media_bytes, mime_type, api_key, model, currency=currency)
        source_label = f"Media scan ({mime_type})"
    elif raw_text:
        drafts = ai_parser.parse_multi_transaction(raw_text, api_key, model, currency=currency)
        source_label = raw_text[:200]
    else:
        raise ValueError("Either raw_text or media_bytes must be provided.")
        
    auto_committed = []
    queued_for_review = []
    
    for draft in drafts:
        kind = draft.get('type')
        conf = float(draft.get('confidence', 1.0))
        missing = draft.get('missing_fields', [])
        clarification = draft.get('clarification_question')
        item_name = (draft.get('item_name') or '').strip().lower()
        
        # Determine safety and matchability
        is_safe = True
        matched_product = None
        reasons = []
        
        if missing or clarification:
            is_safe = False
            reasons.append("Missing required fields or clarification needed")
            
        if conf < auto_commit_threshold:
            is_safe = False
            reasons.append(f"Confidence {round(conf*100)}% below {round(auto_commit_threshold*100)}% threshold")

        draft_currency = draft.get('currency')
        if draft_currency and draft_currency.upper() != currency:
            is_safe = False
            reasons.append(f"Currency {draft_currency.upper()} does not match shop currency {currency}")
            
        if kind in ('sale', 'restock'):
            matched_product = products.get(item_name)
            if not matched_product:
                is_safe = False
                reasons.append(f"Product '{draft.get('item_name')}' not in inventory")
            elif kind == 'sale':
                qty = draft.get('quantity') or 0
                if matched_product['quantity'] < qty:
                    is_safe = False
                    reasons.append(f"Oversell risk: requesting {qty} units, only {matched_product['quantity']} available")
                    
        # Decision gate: Auto-commit or Queue
        if is_safe and kind in ('sale', 'expense', 'restock'):
            req_id = f"auto-{secrets.token_hex(6)}"
            try:
                store.save_transaction(
                    token=user_token,
                    shop_id=shop_id,
                    request_id=req_id,
                    kind=kind,
                    currency=currency,
                    product_id=matched_product['id'] if matched_product else None,
                    quantity=draft.get('quantity'),
                    unit_price=draft.get('unit_price'),
                    expense_amount=draft.get('amount_for_expense'),
                    note=f"Auto-committed from {source_channel} (Confidence: {round(conf*100)}%)",
                    source_text=source_label,
                    expected_generation=shop['generation']
                )
                auto_committed.append({
                    'draft': draft,
                    'transaction_id': req_id,
                    'status': 'committed',
                    'product_name': matched_product['name'] if matched_product else None
                })
                # Update local memory copy of product stock to prevent oversell in same batch
                if matched_product and kind == 'sale':
                    matched_product['quantity'] -= draft.get('quantity', 0)
                elif matched_product and kind == 'restock':
                    matched_product['quantity'] += draft.get('quantity', 0)
            except Exception as e:
                # If auto-commit fails for any validation reason, safely queue for human review
                draft['error_reason'] = str(e)
                draft_id = store.save_pending_draft(
                    shop_id=shop_id,
                    source_channel=source_channel,
                    source_text=f"{source_label} (Auto-commit error: {e})",
                    draft=draft,
                    confidence=conf,
                    user_id=snap['user']['id']
                )
                queued_for_review.append({
                    'draft': draft,
                    'pending_id': draft_id,
                    'reasons': [str(e)]
                })
        else:
            # Enqueue to Pending Drafts Inbox
            draft['review_reasons'] = reasons
            draft_id = store.save_pending_draft(
                shop_id=shop_id,
                source_channel=source_channel,
                source_text=source_label,
                draft=draft,
                confidence=conf,
                user_id=snap['user']['id']
            )
            queued_for_review.append({
                'draft': draft,
                'pending_id': draft_id,
                'reasons': reasons
            })
            
    return {
        'total_parsed': len(drafts),
        'auto_committed': auto_committed,
        'queued_for_review': queued_for_review
    }
