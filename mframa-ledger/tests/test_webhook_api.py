import pytest
from fastapi.testclient import TestClient

import webhook_api


def test_webhook_payload_rejects_oversized_text():
    with pytest.raises(ValueError):
        webhook_api.InboundEvent(event_id='evt-1', source_channel='external_pos', text='x' * 5001)


def test_webhook_endpoint_authenticates_and_enforces_body_limit(monkeypatch):
    monkeypatch.setattr(webhook_api.store, 'init_db', lambda: None)
    monkeypatch.setattr(webhook_api.store, 'accept_webhook_event',
                        lambda shop, secret, event_id, channel, text: {'event_id': event_id, 'duplicate': False})
    with TestClient(webhook_api.app) as client:
        accepted = client.post('/webhooks/shop-1/transactions', headers={'X-SaySale-Webhook-Token': 'secret'},
                               json={'event_id': 'evt-1', 'source_channel': 'pos', 'text': 'sold item'})
        too_large = client.post('/webhooks/shop-1/transactions', content=b'x' * 16_385)
    assert accepted.status_code == 202
    assert accepted.json()['event_id'] == 'evt-1'
    assert too_large.status_code == 413


def test_webhook_endpoint_rejects_unknown_payload_fields(monkeypatch):
    monkeypatch.setattr(webhook_api.store, 'init_db', lambda: None)
    with TestClient(webhook_api.app) as client:
        response = client.post('/webhooks/shop-1/transactions',
                               json={'event_id': 'evt-1', 'source_channel': 'pos', 'text': 'sold item', 'role': 'owner'})
    assert response.status_code == 422


def test_webhook_worker_routes_extraction_only_to_pending_review(monkeypatch):
    event = {'id': 'internal-id', 'shop_id': 'shop-id', 'source_text': 'sold an item',
             'source_channel': 'external_pos'}
    recorded = {}
    monkeypatch.setattr(webhook_api.store, 'claim_webhook_event', lambda: event)
    monkeypatch.setattr(webhook_api.store, 'authorize_webhook_ai', lambda _event: None)
    monkeypatch.setattr(webhook_api.store, 'webhook_shop_context', lambda _shop: {'currency': 'GHS'})
    monkeypatch.setattr(webhook_api.ai_parser, 'parse_multi_transaction',
                        lambda *_args, **_kwargs: [{'type': 'sale', 'confidence': 0.99}])
    monkeypatch.setattr(webhook_api.store, 'finish_webhook_event',
                        lambda _event_id, drafts: recorded.setdefault('drafts', drafts))
    monkeypatch.setattr(webhook_api.store, 'fail_webhook_event', lambda *_args: pytest.fail('unexpected failure'))

    assert webhook_api.process_one_event('key', 'model') is True
    assert recorded['drafts'] == [{'type': 'sale', 'confidence': 0.99}]


def test_webhook_worker_marks_parse_errors_failed(monkeypatch):
    event = {'id': 'internal-id', 'shop_id': 'shop-id', 'source_text': 'text', 'source_channel': 'sms'}
    failed = []
    monkeypatch.setattr(webhook_api.store, 'claim_webhook_event', lambda: event)
    monkeypatch.setattr(webhook_api.store, 'authorize_webhook_ai', lambda _event: None)
    monkeypatch.setattr(webhook_api.store, 'webhook_shop_context', lambda _shop: {'currency': 'USD'})
    monkeypatch.setattr(webhook_api.ai_parser, 'parse_multi_transaction', lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('offline')))
    monkeypatch.setattr(webhook_api.store, 'fail_webhook_event', lambda event_id, error: failed.append((event_id, str(error))))

    assert webhook_api.process_one_event('key', 'model') is True
    assert failed == [('internal-id', 'offline')]
