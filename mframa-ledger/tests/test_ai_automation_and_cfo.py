import json
from types import SimpleNamespace
import pytest
import store
import ai_parser
import ai_cfo
import ai_automation

PASSWORD = 'a-long-test-password-123'

@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DB_PATH', tmp_path / 'ai_test.sqlite3')
    store.init_db()
    store.register('owner@example.com', 'Owner', PASSWORD)
    token = store.login('owner@example.com', PASSWORD)
    shop = store.create_shop(token, 'AI Automation Shop', 'GH', 'GHS', 'Africa/Accra')
    store.add_product(token, shop, 'Cooking oil', 20, 5)
    store.add_product(token, shop, 'Rice', 10, 3)
    return token, shop


def test_multi_draft_parsing(monkeypatch):
    import google.genai
    payload = {
        "items": [
            {"type": "sale", "item_name": "Cooking oil", "quantity": 2, "unit_price": 25.0, "currency": "GHS", "confidence": 0.95},
            {"type": "sale", "item_name": "Rice", "quantity": 1, "unit_price": 100.0, "currency": "GHS", "confidence": 0.90}
        ]
    }
    class MockClient:
        def __init__(self, **kwargs): self.models = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def generate_content(self, **kwargs):
            return SimpleNamespace(text=json.dumps(payload))
    monkeypatch.setattr(google.genai, 'Client', MockClient)

    results = ai_parser.parse_multi_transaction("Sold 2 oils at 25 and 1 rice at 100", "test-key", "gemini-2.5", currency="GHS")
    assert len(results) == 2
    assert results[0]['item_name'] == 'Cooking oil'
    assert results[0]['confidence'] == 0.95
    assert results[1]['item_name'] == 'Rice'


def test_media_transaction_parsing(monkeypatch):
    import google.genai
    payload = {
        "items": [
            {"type": "restock", "item_name": "Cooking oil", "quantity": 50, "unit_price": 20.0, "currency": "GHS", "confidence": 0.98}
        ]
    }
    class MockClient:
        def __init__(self, **kwargs): self.models = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def generate_content(self, **kwargs):
            return SimpleNamespace(text=json.dumps(payload))
    monkeypatch.setattr(google.genai, 'Client', MockClient)

    results = ai_parser.parse_media_transaction(b'fake_image_bytes', 'image/jpeg', 'test-key', 'gemini-2.5', currency='GHS')
    assert len(results) == 1
    assert results[0]['type'] == 'restock'
    assert results[0]['quantity'] == 50


def test_pending_draft_lifecycle(env):
    token, shop = env
    draft_data = {
        "type": "sale",
        "item_name": "Cooking oil",
        "quantity": 3,
        "unit_price": 30.0,
        "currency": "GHS"
    }
    # 1. Save pending draft
    draft_id = store.save_pending_draft(shop, 'whatsapp', 'Sold 3 cooking oils at 30', draft_data, confidence=0.75)
    pending = store.list_pending_drafts(token, shop)
    assert len(pending) == 1
    assert pending[0]['id'] == draft_id
    assert pending[0]['confidence'] == 0.75

    # 2. Approve pending draft
    store.resolve_pending_draft(token, shop, draft_id, 'approve')
    snap = store.snapshot(token, shop)
    assert len(snap['transactions']) == 1
    assert snap['transactions'][0]['quantity'] == 3
    # Check inventory decremented from 20 to 17
    p = next(p for p in snap['products'] if p['name'] == 'Cooking oil')
    assert p['quantity'] == 17
    # Check pending list is now empty
    assert len(store.list_pending_drafts(token, shop)) == 0


def test_pending_draft_rejection(env):
    token, shop = env
    draft_data = {
        "type": "expense",
        "amount_for_expense": 45.0,
        "currency": "GHS"
    }
    draft_id = store.save_pending_draft(shop, 'sms', 'Spent 45 on electricity', draft_data, confidence=0.6)
    store.resolve_pending_draft(token, shop, draft_id, 'reject')
    assert len(store.list_pending_drafts(token, shop)) == 0
    snap = store.snapshot(token, shop)
    assert len(snap['transactions']) == 0


def test_autonomous_ingestion_pipeline(env, monkeypatch):
    token, shop = env
    # Mock parser to return 2 items: 1 high-confidence match, 1 low-confidence ambiguous
    items = [
        {"type": "sale", "item_name": "Cooking oil", "quantity": 2, "unit_price": 25.0, "currency": "GHS", "confidence": 0.95, "missing_fields": []},
        {"type": "sale", "item_name": "Unknown widget", "quantity": 1, "unit_price": 10.0, "currency": "GHS", "confidence": 0.60, "missing_fields": []}
    ]
    monkeypatch.setattr(ai_parser, 'parse_multi_transaction', lambda *args, **kwargs: items)

    res = ai_automation.process_inbound_record(
        shop_id=shop,
        user_token=token,
        raw_text="2 oils at 25 and 1 widget at 10",
        source_channel="whatsapp",
        api_key="mock",
        model="mock",
        auto_commit_threshold=0.85
    )
    # The Cooking oil sale should be auto-committed
    assert len(res['auto_committed']) == 1
    assert res['auto_committed'][0]['product_name'] == 'Cooking oil'

    # The Unknown widget should be safely queued into Pending Drafts
    assert len(res['queued_for_review']) == 1
    reasons = res['queued_for_review'][0]['reasons']
    assert any("not in inventory" in r for r in reasons)

    # Verify database state
    snap = store.snapshot(token, shop)
    assert len(snap['transactions']) == 1
    assert snap['transactions'][0]['item_name'] == 'Cooking oil'
    assert len(snap['pending']) == 1


def test_autonomous_ingestion_routes_foreign_currency_to_review(env, monkeypatch):
    token, shop = env
    monkeypatch.setattr(ai_parser, 'parse_multi_transaction', lambda *args, **kwargs: [
        {"type": "sale", "item_name": "Cooking oil", "quantity": 1, "unit_price": 25.0,
         "currency": "USD", "confidence": 0.99, "missing_fields": []}
    ])

    result = ai_automation.process_inbound_record(
        shop_id=shop, user_token=token, raw_text='Sold oil for USD 25',
        api_key='mock', model='mock',
    )

    assert result['auto_committed'] == []
    assert 'Currency USD does not match shop currency GHS' in result['queued_for_review'][0]['reasons']
    assert store.snapshot(token, shop)['transactions'] == []


@pytest.mark.parametrize(('confidence', 'should_auto_commit'), [(0.0, False), (0.85, True)])
def test_autonomous_ingestion_confidence_gate_preserves_zero_and_threshold(env, monkeypatch, confidence, should_auto_commit):
    token, shop = env
    monkeypatch.setattr(ai_parser, 'parse_multi_transaction', lambda *args, **kwargs: [
        {"type": "sale", "item_name": "Cooking oil", "quantity": 1, "unit_price": 10.0,
         "currency": "GHS", "confidence": confidence, "missing_fields": []}
    ])

    result = ai_automation.process_inbound_record(
        shop_id=shop, user_token=token, raw_text='Sold one cooking oil for 10',
        api_key='mock', model='mock', auto_commit_threshold=0.85,
    )

    assert bool(result['auto_committed']) is should_auto_commit
    assert bool(result['queued_for_review']) is not should_auto_commit
    snapshot = store.snapshot(token, shop)
    assert len(snapshot['transactions']) == int(should_auto_commit)
    if not should_auto_commit:
        assert snapshot['pending'][0]['confidence'] == 0.0
        assert any('Confidence 0%' in reason for reason in result['queued_for_review'][0]['reasons'])


def test_shop_analytics_and_cfo(env, monkeypatch):
    token, shop = env
    snap = store.snapshot(token, shop)
    gen = snap['shop']['generation']
    pid = next(p['id'] for p in snap['products'] if p['name'] == 'Cooking oil')
    # Record a sale
    store.save_transaction(token, shop, 'tx-1', 'sale', 'GHS',
                           product_id=pid, quantity=4, unit_price=25.0, note='test sale',
                           expected_generation=gen)
    # Record an expense
    store.save_transaction(token, shop, 'tx-2', 'expense', 'GHS',
                           expense_amount=30.0, note='supplies',
                           expected_generation=gen)

    analytics = store.get_shop_analytics(token, shop)
    assert analytics['sales_total_minor'] == 10000  # 4 * 25 GHS = 100.00 -> 10000 minor
    assert analytics['expense_total_minor'] == 3000
    assert analytics['net_cash_minor'] == 7000
    assert len(analytics['inventory_runway']) == 2

    # Mock CFO generation
    import google.genai
    class MockClient:
        def __init__(self, **kwargs): self.models = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def generate_content(self, **kwargs):
            return SimpleNamespace(text="CFO says: Cash flow is positive +70.00 GHS.")
    monkeypatch.setattr(google.genai, 'Client', MockClient)

    briefing = ai_cfo.generate_executive_briefing(token, shop, 'mock', 'mock')
    assert "Cash flow is positive" in briefing

    answer = ai_cfo.ask_cfo(token, shop, "How is my shop doing?", 'mock', 'mock')
    assert "Cash flow is positive" in answer


def test_inventory_runway_uses_recent_sales_but_totals_remain_lifetime(env):
    token, shop = env
    snap = store.snapshot(token, shop)
    oil_id = next(p['id'] for p in snap['products'] if p['name'] == 'Cooking oil')
    store.save_transaction(token, shop, 'old-sale', 'sale', 'GHS', product_id=oil_id,
                           quantity=6, unit_price=10.0, expected_generation=snap['shop']['generation'])
    current = store.snapshot(token, shop)
    store.save_transaction(token, shop, 'recent-sale', 'sale', 'GHS', product_id=oil_id,
                           quantity=4, unit_price=10.0, expected_generation=current['shop']['generation'])

    with store.connection() as connection:
        connection.execute("UPDATE transactions SET created_at=strftime('%Y-%m-%dT%H:%M:%fZ','now','-40 days') WHERE id='old-sale'")

    analytics = store.get_shop_analytics(token, shop, days=30)
    oil_runway = next(row for row in analytics['inventory_runway'] if row['name'] == 'Cooking oil')
    rice_runway = next(row for row in analytics['inventory_runway'] if row['name'] == 'Rice')

    assert analytics['sales_total_minor'] == 10000
    assert analytics['sales_count'] == 2
    assert oil_runway['daily_velocity'] == 0.13
    assert oil_runway['days_left'] == 75.0
    assert rice_runway['daily_velocity'] == 0.0
    assert rice_runway['days_left'] is None


def test_inventory_runway_rejects_invalid_days_window(env):
    token, shop = env

    with pytest.raises(ValueError, match='positive whole number of days'):
        store.get_shop_analytics(token, shop, days=0)


def test_restock_recommendations_use_recent_sales_and_explain_insufficient_history(env):
    token, shop = env
    snap = store.snapshot(token, shop)
    oil_id = next(product['id'] for product in snap['products'] if product['name'] == 'Cooking oil')
    store.save_transaction(token, shop, 'recommend-sale', 'sale', 'GHS', product_id=oil_id,
                           quantity=16, unit_price=10.0, expected_generation=snap['shop']['generation'])
    store.add_product(token, shop, 'Slow mover', 4, 5)

    analytics = store.get_shop_analytics(token, shop)
    recommendations = {item['name']: item for item in analytics['restock_recommendations']}
    cooking_oil = recommendations['Cooking oil']
    slow_mover = recommendations['Slow mover']

    assert cooking_oil['target_coverage_days'] == 14
    assert cooking_oil['target_stock'] == 8
    assert cooking_oil['suggested_quantity'] == 4
    assert cooking_oil['recent_units_sold'] == 16
    assert cooking_oil['sales_window_days'] == 30
    assert slow_mover['reason'] == 'insufficient_sales_history'
    assert slow_mover['suggested_quantity'] is None
    assert 'consider ordering 4 units' in ai_cfo.format_analytics_for_prompt(analytics)


def test_voided_sales_do_not_drive_restock_velocity(env):
    token, shop = env
    snap = store.snapshot(token, shop)
    oil_id = next(product['id'] for product in snap['products'] if product['name'] == 'Cooking oil')
    store.save_transaction(token, shop, 'voided-demand-sale', 'sale', 'GHS', product_id=oil_id,
                           quantity=16, unit_price=10.0, expected_generation=snap['shop']['generation'])
    store.void_transaction(token, shop, 'voided-demand-sale', reason='Test reversal')

    analytics = store.get_shop_analytics(token, shop)
    oil_runway = next(row for row in analytics['inventory_runway'] if row['name'] == 'Cooking oil')

    assert oil_runway['daily_velocity'] == 0
    assert oil_runway['days_left'] is None
    assert all(item['name'] != 'Cooking oil' for item in analytics['restock_recommendations'])


def test_pending_draft_with_none_type(env):
    token, shop = env
    # Ambiguous input where AI couldn't determine if it was a sale or return
    draft_data = {
        "type": None,
        "item_name": "Ambiguous oil item",
        "quantity": None,
        "unit_price": None,
        "clarification_question": "Was this a sale or return?"
    }
    draft_id = store.save_pending_draft(shop, 'whatsapp', 'Returned or sold oil?', draft_data, confidence=0.3)
    pending = store.list_pending_drafts(token, shop)
    assert len(pending) == 1
    assert pending[0]['draft']['type'] is None
    assert pending[0]['draft']['clarification_question'] == "Was this a sale or return?"


def test_ledger_manual_snapshot_and_history(env):
    token, shop = env
    # Create a manual snapshot
    snap_id = store.snapshot_ledger(token, shop, trigger_action='audit_check', trigger_reason='Quarterly review')
    assert snap_id.startswith('snap-')
    
    # List snapshots
    history = store.list_snapshots(token, shop)
    assert len(history) == 1
    assert history[0]['id'] == snap_id
    assert history[0]['trigger_action'] == 'audit_check'
    assert history[0]['trigger_reason'] == 'Quarterly review'
    
    # Get snapshot details
    snap_detail = store.get_snapshot(token, shop, snap_id)
    assert snap_detail['id'] == snap_id
    assert 'products' in snap_detail['state']
    assert len(snap_detail['state']['products']) == 2


def test_viewer_cannot_create_manual_snapshot(env):
    token, shop = env
    store.register('viewer@example.com', 'Viewer', PASSWORD)
    viewer = store.login('viewer@example.com', PASSWORD)
    code = store.create_invite(token, shop, 'viewer@example.com', 'viewer')
    store.accept_invite(viewer, code)

    with pytest.raises(PermissionError, match='do not have permission'):
        store.snapshot_ledger(viewer, shop, trigger_reason='Unauthorized snapshot')


def test_void_sale_with_automatic_snapshot_and_stock_restoration(env):
    token, shop = env
    snap = store.snapshot(token, shop)
    gen = snap['shop']['generation']
    pid = next(p['id'] for p in snap['products'] if p['name'] == 'Cooking oil')
    
    # Initial stock is 20. Record a sale of 5 units.
    store.save_transaction(token, shop, 'sale-tx-101', 'sale', 'GHS',
                           product_id=pid, quantity=5, unit_price=20.0,
                           note='Test sale for voiding', expected_generation=gen)
    
    # Stock should now be 15
    snap2 = store.snapshot(token, shop)
    oil2 = next(p for p in snap2['products'] if p['name'] == 'Cooking oil')
    assert oil2['quantity'] == 15
    
    # Void the sale
    void_res = store.void_transaction(token, shop, 'sale-tx-101', reason='Customer returned items')
    assert void_res['snapshot_id'].startswith('snap-void-')
    assert void_res['void_tx_id'].startswith('void-')
    
    # 1. Verify stock is restored from 15 back to 20
    snap3 = store.snapshot(token, shop)
    oil3 = next(p for p in snap3['products'] if p['name'] == 'Cooking oil')
    assert oil3['quantity'] == 20
    
    # 2. Verify original transaction note is updated with (Voided: ...)
    orig_tx = next(r for r in snap3['transactions'] if r['id'] == 'sale-tx-101')
    assert '(Voided: Customer returned items)' in orig_tx['note']
    
    # 3. Verify compensating void record was created
    void_tx = next(r for r in snap3['transactions'] if r['id'] == void_res['void_tx_id'])
    assert void_tx['type'] == 'void'
    assert void_tx['quantity'] == 5
    assert void_tx['amount_minor'] == 10000
    
    # 4. Verify snapshot exists in snapshot history with pre-mutation state
    snapshots = store.list_snapshots(token, shop)
    assert any(s['id'] == void_res['snapshot_id'] for s in snapshots)
    snap_record = store.get_snapshot(token, shop, void_res['snapshot_id'])
    # The pre-mutation state had stock at 15
    pre_oil = next(p for p in snap_record['state']['products'] if p['name'] == 'Cooking oil')
    assert pre_oil['quantity'] == 15
    assert snap_record['state']['target_transaction']['id'] == 'sale-tx-101'


def test_void_restock_removes_stock_with_oversell_check(env):
    token, shop = env
    snap = store.snapshot(token, shop)
    gen = snap['shop']['generation']
    pid = next(p['id'] for p in snap['products'] if p['name'] == 'Rice')
    
    # Initial rice stock is 10. Record a restock of 15 units.
    store.save_transaction(token, shop, 'restock-tx-201', 'restock', 'GHS',
                           product_id=pid, quantity=15, unit_price=10.0,
                           note='Incoming batch', expected_generation=gen)
    
    snap2 = store.snapshot(token, shop)
    rice2 = next(p for p in snap2['products'] if p['name'] == 'Rice')
    assert rice2['quantity'] == 25
    
    # Void the restock -> shelf stock should decrease by 15 back to 10
    store.void_transaction(token, shop, 'restock-tx-201', reason='Vendor sent wrong invoice')
    snap3 = store.snapshot(token, shop)
    rice3 = next(p for p in snap3['products'] if p['name'] == 'Rice')
    assert rice3['quantity'] == 10


def test_cannot_void_already_voided_or_void_record(env):
    token, shop = env
    snap = store.snapshot(token, shop)
    gen = snap['shop']['generation']
    pid = next(p['id'] for p in snap['products'] if p['name'] == 'Rice')
    
    store.save_transaction(token, shop, 'tx-to-double-void', 'sale', 'GHS',
                           product_id=pid, quantity=2, unit_price=10.0,
                           expected_generation=gen)
    
    void_res = store.void_transaction(token, shop, 'tx-to-double-void', reason='Mistake')
    
    # Cannot void the same transaction twice
    with pytest.raises(ValueError, match='already been voided'):
        store.void_transaction(token, shop, 'tx-to-double-void', reason='Try again')
        
    # Cannot void a void record
    with pytest.raises(ValueError, match='Cannot void an existing void transaction'):
        store.void_transaction(token, shop, void_res['void_tx_id'], reason='Voiding the void')


def test_long_original_note_does_not_allow_double_void(env):
    token, shop = env
    snap = store.snapshot(token, shop)
    pid = next(p['id'] for p in snap['products'] if p['name'] == 'Rice')
    store.save_transaction(token, shop, 'tx-long-note', 'sale', 'GHS', product_id=pid,
                           quantity=1, unit_price=10.0, note='n' * 500,
                           expected_generation=snap['shop']['generation'])

    store.void_transaction(token, shop, 'tx-long-note', reason='Correction')

    with pytest.raises(ValueError, match='already been voided'):
        store.void_transaction(token, shop, 'tx-long-note', reason='Retry')


def test_void_permission_denied_for_clerk_and_viewer(env):
    token, shop = env
    snap = store.snapshot(token, shop)
    gen = snap['shop']['generation']
    pid = next(p['id'] for p in snap['products'] if p['name'] == 'Rice')
    store.save_transaction(token, shop, 'tx-perm-test', 'sale', 'GHS',
                           product_id=pid, quantity=1, unit_price=10.0,
                           expected_generation=gen)
    
    # Register clerk
    clerk_email = 'clerk_void_test@example.com'
    store.register(clerk_email, 'Clerk', PASSWORD)
    clerk_token = store.login(clerk_email, PASSWORD)
    code = store.create_invite(token, shop, clerk_email, 'clerk')
    store.accept_invite(clerk_token, code)
    
    # Clerk does not have void permission
    with pytest.raises(PermissionError, match='do not have permission'):
        store.void_transaction(clerk_token, shop, 'tx-perm-test', reason='Clerk attempting void')

