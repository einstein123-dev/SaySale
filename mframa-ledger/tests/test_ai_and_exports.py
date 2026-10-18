import json
from types import SimpleNamespace
import pytest
from ai_parser import Draft, parse_transaction
from ui import ledger_frame, csv_bytes


def test_model_receives_shop_currency_and_marks_missing(monkeypatch):
    import google.genai
    captured={}
    payload=dict(type='sale',item_name='oil',quantity=None,unit_price=None,amount_for_expense=None,currency='EUR',missing_fields=[],clarification_question=None)
    class Client:
        def __init__(self,**kwargs): self.models=self
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def generate_content(self,**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text=json.dumps(payload))
    monkeypatch.setattr(google.genai,'Client',Client)
    result=parse_transaction('Vendu de l’huile','test-only','test-model',currency='EUR')
    assert json.loads(captured['contents'])['shop_currency']=='EUR'
    assert {'quantity','unit_price'}<=set(result['missing_fields'])


@pytest.mark.parametrize('raw',['{}','bad JSON','{"type":"transfer"}'])
def test_bad_model_response(raw):
    with pytest.raises(ValueError): Draft.model_validate_json(raw)


def test_csv_uses_iso_currency_and_blank_unknown_cost():
    r=dict(id='one',created_at='2026-01-01T00:00:00Z',type='restock',item_name='Oil',quantity=2,
           unit_price_minor=None,amount_minor=None,currency='KWD',note='=BAD()',source_text='test',created_by='uid')
    frame=ledger_frame([r],display=False)
    assert frame.iloc[0]['Amount'] is None
    assert frame.iloc[0]['Currency']=='KWD'
    assert "'=BAD()" in csv_bytes(frame).decode('utf-8-sig')


def test_multilingual_currency_schema_not_ghs_only():
    payload=dict(type='sale',item_name='oil',quantity=1,unit_price=1.234,currency='KWD',amount_for_expense=None,missing_fields=[],clarification_question=None)
    assert Draft.model_validate(payload).currency=='KWD'
