import ui
from i18n import tr
from datetime import date
import pytest


class Column:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_stock_cards_use_status_pills_without_progress_bars(monkeypatch):
    rendered=[]
    monkeypatch.setattr(ui.st,'columns',lambda count:[Column() for _ in range(count)])
    monkeypatch.setattr(ui.st,'markdown',lambda value,**kwargs:rendered.append(value))

    ui.stock_cards([
        {'name':'Oil <script>', 'quantity':0, 'threshold':5},
        {'name':'Rice', 'quantity':2, 'threshold':5},
        {'name':'Soap', 'quantity':10, 'threshold':5},
    ])

    assert len(rendered)==3
    assert all('status-dot' in card for card in rendered)
    assert all('track' not in card for card in rendered)
    assert '&lt;script&gt;' in rendered[0]
    assert 'Out of stock' in rendered[0]
    assert 'Low stock' in rendered[1]
    assert 'In stock' in rendered[2]


def test_pending_reasons_hide_technical_confidence(monkeypatch):
    assert ui.pending_reason_copy(['Confidence 70% below 85% threshold']) == 'Review the transaction details before approving.'
    assert ui.pending_reason_copy(["Product 'Beans' not in inventory"]) == 'Match this item to a product in your inventory.'
    assert ui.pending_reason_copy(['Oversell risk: requesting 4 units']) == 'Check the requested quantity against available stock.'
    assert ui.pending_reason_copy([], 'Which product was sold?') == 'Which product was sold?'
    assert tr('Needs a quick check','fr') == 'À vérifier rapidement'
    assert tr('Needs a quick check','es') == 'Requiere una revisión rápida'


def test_activity_table_escapes_values_and_adds_type_badge(monkeypatch):
    rendered=[]
    monkeypatch.setattr(ui.st,'markdown',lambda value,**kwargs:rendered.append(value))
    base_row={
        'id':'activity-1',
        'created_at':'2026-06-01T12:00:00Z',
        'type':'sale',
        'product_id':'product-1',
        'item_name':'<img src=x onerror=alert(1)>',
        'quantity':2,
        'unit_price_minor':None,
        'amount_minor':250,
        'currency':'USD',
        'note':'<script>alert(1)</script>',
        'source_text':'',
        'created_by':'user-1',
    }
    rows=[dict(base_row,id=f'activity-{kind}',type=kind) for kind in ('sale','void','expense')]
    ui.activity_table(rows)

    html=rendered[0]
    assert '<table class="activity-table"' in html
    assert 'type-badge sale' in html
    assert 'type-badge void' in html
    assert 'type-badge expense' in html
    assert '&lt;img src=x onerror=alert(1)&gt;' in html
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html
    assert '<img src=x' not in html
    assert '<script>' not in html


def test_ui_style_hooks_cover_requested_actions_and_table():
    assert '.activity-table tbody tr:hover td' in ui.STYLE
    assert '.activity-table tbody tr:nth-child(even)' in ui.STYLE
    assert '.type-badge.void' in ui.STYLE
    assert '.type-badge.expense' in ui.STYLE
    assert '.st-key-parse_ai_button' in ui.STYLE
    assert '.st-key-manual_draft_button' in ui.STYLE


def test_sales_chart_groups_by_shop_local_day_and_excludes_voided_sales():
    rows=[
        {'id':'local-day-sale','type':'sale','created_at':'2026-01-02T02:00:00Z','amount_minor':1000},
        {'id':'old-sale','type':'sale','created_at':'2025-12-31T20:00:00Z','amount_minor':5000},
        {'id':'voided-sale','type':'sale','created_at':'2026-01-30T12:00:00Z','amount_minor':2500},
        {'id':'void-1','type':'void','created_at':'2026-01-30T13:00:00Z','amount_minor':2500,'note':'Void of voided-sale · Reason: returned'},
        {'id':'expense','type':'expense','created_at':'2026-01-30T12:00:00Z','amount_minor':9000},
    ]

    chart=ui.sales_over_time_frame(rows,'America/Los_Angeles','USD',today=date(2026,1,30))

    assert len(chart)==30
    assert chart.loc['2026-01-01','Sales']==10.0
    assert chart.loc['2026-01-30','Sales']==0.0


def test_sales_chart_includes_zero_days_and_rejects_invalid_range():
    chart=ui.sales_over_time_frame([],days=7,today=date(2026,1,30))

    assert len(chart)==7
    assert chart['Sales'].sum()==0
    with pytest.raises(ValueError,match='positive whole number of days'):
        ui.sales_over_time_frame([],days=0)
