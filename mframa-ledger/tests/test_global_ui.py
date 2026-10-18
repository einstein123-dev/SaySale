from pathlib import Path
from streamlit.testing.v1 import AppTest
import pytest
import store

APP=str(Path(__file__).resolve().parents[1]/'app.py')
PASSWORD='a-long-test-password-123'

@pytest.fixture
def shop_env(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DB_PATH',tmp_path/'ui-global.sqlite3')
    store.init_db()
    store.register('owner@example.com','Owner',PASSWORD)
    token=store.login('owner@example.com',PASSWORD)
    shop=store.create_shop(token,'World shop','FR','EUR','Europe/Paris')
    store.reset_demo(token,shop)
    return token,shop


def w(app,group,label):
    return next(x for x in getattr(app,group) if x.label==label)


def navigate(app,page,timeout=15):
    button=next(item for item in app.button if item.key and item.key.startswith('sidebar_nav_') and page in item.key)
    button.click().run(timeout=timeout)


def logged(token):
    app=AppTest.from_file(APP,default_timeout=15)
    app.session_state['auth_token']=token
    app.run(timeout=15)
    assert not app.exception
    return app


def test_signin_logout_ui(shop_env):
    token,shop=shop_env
    app=AppTest.from_file(APP,default_timeout=15).run(timeout=15)
    assert not app.exception
    # Login email/password are the first fields, signup fields have explicit keys.
    app.text_input[0].set_value('owner@example.com')
    app.text_input[1].set_value(PASSWORD)
    w(app,'button','Sign in').click().run()
    assert not app.exception
    assert any(m.label=='Sales recorded' for m in app.metric)
    w(app,'button','Sign out').click().run()
    assert not app.exception
    assert not app.metric


def test_record_overview_keeps_summary_collapsed_after_entry(shop_env):
    token,shop=shop_env
    app=logged(token)

    assert w(app,'text_area','What happened?')
    summary=w(app,'expander','Shop summary')
    assert summary.proto.expanded is False
    assert any(metric.label=='Sales recorded' for metric in app.metric)


def test_sale_ui_and_localized_input(shop_env):
    token,shop=shop_env
    app=logged(token)
    w(app,'selectbox','Language / Langue / Idioma').select('fr').run()
    w(app,'button','Créer un brouillon manuel').click().run()
    w(app,'selectbox','Type d’opération').select('sale')
    pid=next(p['id'] for p in store.snapshot(token,shop)['products'] if p['name']=='Cooking oil')
    w(app,'selectbox','Article du stock').select(pid)
    w(app,'text_input','Quantité (unités entières)').set_value('6')
    w(app,'text_input','Prix / coût unitaire (EUR)').set_value('25,50')
    w(app,'checkbox','Confirmer la devise: EUR').check()
    w(app,'checkbox','J’ai vérifié les détails et j’autorise cette opération.').check()
    w(app,'button','Vérifier le total calculé').click().run()
    assert not store.snapshot(token,shop)['transactions']
    w(app,'button','Confirmer et enregistrer').click().run()
    assert not app.exception
    rows=store.snapshot(token,shop)['transactions']
    assert len(rows)==1 and rows[0]['amount_minor']==15300


def test_viewer_has_no_write_controls(shop_env):
    token,shop=shop_env
    store.register('viewer@example.com','Viewer',PASSWORD)
    viewer=store.login('viewer@example.com',PASSWORD)
    store.accept_invite(viewer,store.create_invite(token,shop,'viewer@example.com','viewer'))
    app=logged(viewer)
    assert not any(b.label=='Create manual draft' for b in app.button)
    for page in ['Inventory','Team','Settings','Ledger','Account']:
        navigate(app,page)
        assert not app.exception
    assert not store.snapshot(token,shop)['transactions']


def test_inventory_settings_team_and_spanish(shop_env):
    token,shop=shop_env
    app=AppTest.from_file(APP,default_timeout=10)
    app.session_state['auth_token']=token
    app.run(timeout=10)
    assert not app.exception
    for page in ['Inventory','Settings','Team','Ledger','Account']:
        navigate(app,page,timeout=10)
        assert not app.exception
    w(app,'selectbox','Language / Langue / Idioma').select('es').run(timeout=10)
    assert not app.exception
    assert any('Cuenta' in item.options for item in app.radio)


def test_create_first_shop_ui(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DB_PATH',tmp_path/'new.sqlite3')
    store.init_db()
    store.register('new@example.com','New',PASSWORD)
    token=store.login('new@example.com',PASSWORD)
    app=logged(token)
    w(app,'text_input','Shop name').set_value('New shop')
    w(app,'button','Create shop').click().run()
    assert not app.exception
    assert len(store.list_shops(token))==1
    assert any(m.label=='Sales recorded' for m in app.metric)


def test_shop_switch_clears_draft(shop_env):
    token,shop=shop_env
    other=store.create_shop(token,'Tokyo shop','JP','JPY','Asia/Tokyo')
    app=logged(token)
    w(app,'selectbox','Your shops').select(shop).run()
    w(app,'button','Create manual draft').click().run()
    assert any(x.label=='Confirm & save' for x in app.button)
    w(app,'selectbox','Your shops').select(other).run()
    assert not app.exception
    assert not any(x.label=='Confirm & save' for x in app.button)
    assert not store.snapshot(token,other)['transactions']


def test_owner_invite_ui_and_join_ui(shop_env):
    token,shop=shop_env
    app=logged(token)
    navigate(app,'Team')
    w(app,'text_input','Email').set_value('new@example.com')
    w(app,'selectbox','Role').select('clerk')
    w(app,'button','Create invitation').click().run()
    assert not app.exception
    code=app.session_state['invite_code']
    store.register('new@example.com','New',PASSWORD)
    new=store.login('new@example.com',PASSWORD)
    app=logged(new)
    w(app,'text_input','Invitation code').set_value(code)
    w(app,'button','Join shop').click().run()
    assert not app.exception
    assert store.snapshot(new,shop)['role']=='clerk'
