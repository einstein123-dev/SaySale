from concurrent.futures import ThreadPoolExecutor
import sqlite3
import time
import pytest
import store
from intl import minor_units, money_label, local_time

PASSWORD='a-long-test-password-123'
@pytest.fixture
def env(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DB_PATH',tmp_path/'global.sqlite3')
    store.init_db()
    store.register('owner@example.com','Owner',PASSWORD)
    owner=store.login('owner@example.com',PASSWORD)
    shop=store.create_shop(owner,'Shop A','US','USD','America/New_York')
    other=store.create_shop(owner,'Shop B','JP','JPY','Asia/Tokyo')
    store.reset_demo(owner,shop)
    return owner,shop,other


def state(env):
    owner,shop,_=env
    return store.snapshot(owner,shop)


def save(env,id='one',kind='sale',quantity=2,unit_price='25',**kw):
    owner,shop,_=env
    snap=state(env)
    pid=next(p['id'] for p in snap['products'] if p['name']=='Cooking oil')
    return store.save_transaction(owner,shop,id,kind,'USD',pid,quantity,unit_price,
        expected_generation=snap['shop']['generation'],**kw)


def member(env,role,email=None):
    owner,shop,_=env
    email=email or role+'@example.com'
    store.register(email,role,PASSWORD)
    token=store.login(email,PASSWORD)
    code=store.create_invite(owner,shop,email,role)
    store.accept_invite(token,code)
    return token


def test_registration_hash_and_session(env):
    owner,*_=env
    user=store.current_user(owner)
    assert user['email']=='owner@example.com'
    with store.connection() as c:
        hashed=c.execute('SELECT password_hash FROM users').fetchone()[0]
        assert hashed.startswith('scrypt$') and PASSWORD not in hashed
        assert not c.execute('SELECT 1 FROM sessions WHERE token_hash=?',(owner,)).fetchone()
    store.logout(owner)
    with pytest.raises(PermissionError): store.current_user(owner)


def test_duplicate_email_and_invalid_password(env):
    with pytest.raises(ValueError): store.register('OWNER@example.com','Owner',PASSWORD)
    with pytest.raises(ValueError): store.register('new@example.com','New','short')


def test_login_lockout_persists(env):
    for _ in range(5):
        with pytest.raises(ValueError): store.login('owner@example.com','wrong')
    with pytest.raises(ValueError,match='Too many'): store.login('owner@example.com',PASSWORD)
    with store.connection() as c: c.execute('UPDATE login_attempts SET locked_until=?',(time.time()-1,))
    assert store.login('owner@example.com',PASSWORD)


def test_session_expiry_and_password_revoke(env):
    owner,*_=env
    second=store.login('owner@example.com',PASSWORD)
    store.change_password(owner,PASSWORD,'another-strong-password')
    for tok in [owner,second]:
        with pytest.raises(PermissionError): store.current_user(tok)
    assert store.login('owner@example.com','another-strong-password')


def test_expired_session(env):
    owner,*_=env
    with store.connection() as c: c.execute('UPDATE sessions SET expires_at=0')
    with pytest.raises(PermissionError): store.list_shops(owner)


def test_tenant_isolation_for_reads_and_product_ids(env):
    owner,shop,other=env
    outsider=member(env,'manager')
    with pytest.raises(PermissionError): store.snapshot(outsider,other)
    other_pid=store.add_product(owner,other,'Tokyo oil',10,2)
    snap=state(env)
    with pytest.raises(ValueError,match='belonging'):
        store.save_transaction(outsider,shop,'x','sale','USD',other_pid,1,2,expected_generation=snap['shop']['generation'])
    assert not state(env)['transactions']
    assert len(store.snapshot(owner,other)['products'])==1
    with pytest.raises(ValueError): store.set_threshold(outsider,shop,other_pid,3)


@pytest.mark.parametrize('role',['viewer','clerk','manager'])
def test_role_permissions(env,role):
    owner,shop,_=env
    token=member(env,role)
    snap=store.snapshot(token,shop)
    assert snap['role']==role
    pid=snap['products'][0]['id']
    for kind in ['sale','expense','restock']:
        kwargs=dict(token=token,shop_id=shop,request_id=kind,kind=kind,currency='USD',product_id=pid,
                    quantity=1,unit_price=1,expense_amount=2,expected_generation=snap['shop']['generation'])
        if kind in store.PERMISSIONS[role]: assert store.save_transaction(**kwargs)
        else:
            with pytest.raises(PermissionError): store.save_transaction(**kwargs)
    for operation in [lambda:store.create_invite(token,shop,'a@example.com','viewer'),lambda:store.reset_demo(token,shop),lambda:store.team(token,shop),lambda:store.update_shop(token,shop,'oops','US','UTC')]:
        with pytest.raises(PermissionError): operation()
    if role!='manager':
        with pytest.raises(PermissionError): store.add_product(token,shop,'Not allowed',1,1)


def test_revocation_is_immediate(env):
    owner,shop,_=env
    manager=member(env,'manager')
    uid=store.current_user(manager)['id']
    store.change_role(owner,shop,uid,'viewer')
    with pytest.raises(PermissionError): store.add_product(manager,shop,'No longer allowed',1,1)
    store.remove_member(owner,shop,uid)
    with pytest.raises(PermissionError): store.snapshot(manager,shop)
    assert store.current_user(manager) # account still exists


def test_invite_email_single_use_and_no_owner_escalation(env):
    owner,shop,_=env
    store.register('invite@example.com','Invite',PASSWORD)
    invitee=store.login('invite@example.com',PASSWORD)
    code=store.create_invite(owner,shop,'invite@example.com','clerk')
    with pytest.raises(ValueError): store.accept_invite(owner,code)
    assert store.accept_invite(invitee,code)==shop
    with pytest.raises(ValueError): store.accept_invite(invitee,code)
    with pytest.raises(ValueError): store.create_invite(owner,shop,'foo@example.com','owner')
    with pytest.raises(ValueError): store.remove_member(owner,shop,store.current_user(owner)['id'])


def test_invite_expiry_and_revoke(env):
    owner,shop,_=env
    store.register('invite@example.com','Invite',PASSWORD)
    invitee=store.login('invite@example.com',PASSWORD)
    code=store.create_invite(owner,shop,'invite@example.com','viewer')
    store.revoke_invite(owner,shop,'invite@example.com')
    with pytest.raises(ValueError): store.accept_invite(invitee,code)
    code=store.create_invite(owner,shop,'invite@example.com','viewer')
    with store.connection() as c: c.execute('UPDATE invitations SET expires_at=0')
    with pytest.raises(ValueError): store.accept_invite(invitee,code)


def test_sale_duplicate_and_persistence(env):
    assert save(env)
    assert not save(env)
    store.init_db()
    snap=state(env)
    assert len(snap['transactions'])==1
    assert snap['transactions'][0]['amount_minor']==5000
    assert next(p['quantity'] for p in snap['products'] if p['name']=='Cooking oil')==8


def test_oversell_rollback(env):
    with pytest.raises(ValueError,match='Insufficient stock'): save(env,quantity=11)
    assert not state(env)['transactions']
    assert next(p['quantity'] for p in state(env)['products'] if p['name']=='Cooking oil')==10


def test_concurrent_oversell(env):
    def attempt(id):
        try: return save(env,id=id,quantity=6)
        except ValueError: return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(attempt,['one','two']))==1
    assert len(state(env)['transactions'])==1


def test_concurrent_duplicate(env):
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(lambda _:save(env),range(4)))==1
    assert len(state(env)['transactions'])==1


def test_unknown_cost_and_separate_expense(env):
    save(env,kind='restock',unit_price=None)
    save(env,id='expense',kind='expense',expense_amount='12.50')
    rows=state(env)['transactions']
    assert next(r for r in rows if r['type']=='restock')['amount_minor'] is None
    assert sum(r['amount_minor'] for r in rows if r['type']=='expense')==1250


def test_currency_mismatch_and_reset_generation(env):
    owner,shop,_=env
    snap=state(env)
    pid=snap['products'][0]['id']
    with pytest.raises(ValueError,match='Currency must match'):
        store.save_transaction(owner,shop,'x','sale','EUR',pid,1,1,expected_generation=snap['shop']['generation'])
    store.reset_demo(owner,shop)
    with pytest.raises(ValueError,match='fresh draft'):
        store.save_transaction(owner,shop,'x','sale','USD',pid,1,1,expected_generation=snap['shop']['generation'])
    assert not state(env)['transactions']


@pytest.mark.parametrize('currency,value,expected',[('USD','12.50',1250),('JPY','12',12),('KWD','12.345',12345),('CLF','1.1234',11234)])
def test_currency_precision(currency,value,expected):
    assert minor_units(value,currency)==expected


@pytest.mark.parametrize('currency,value',[('USD','1.001'),('JPY','1.5'),('KWD','1.0001'),('USD','NaN'),('USD','Infinity'),('USD','-1')])
def test_invalid_money(currency,value):
    with pytest.raises(ValueError): minor_units(value,currency)


def test_timezone_and_localization():
    assert local_time('2026-01-01T00:00:00Z','America/New_York').startswith('2025-12-31 19:00')
    assert money_label(12345,'USD','en')!=money_label(12345,'USD','fr')


def test_reset_only_one_shop_and_retains_audit(env):
    owner,shop,other=env
    manager=member(env,'manager')
    store.add_product(owner,other,'Tokyo soap',9,2)
    save(env)
    store.reset_demo(owner,shop)
    assert not state(env)['transactions']
    assert len(store.snapshot(owner,other)['products'])==1
    assert store.snapshot(manager,shop)['role']=='manager'
    assert any(e['action']=='transaction.saved' for e in store.audit(owner,shop))


def test_sql_injection_name_is_literal(env):
    owner,shop,_=env
    pid=store.add_product(owner,shop,"x'); DROP TABLE users;--",3,1)
    assert any(p['id']==pid for p in state(env)['products'])
    assert store.current_user(owner)


def test_ai_budget_and_role(env):
    owner,shop,_=env
    for _ in range(5): store.authorize_ai(owner,shop)
    with pytest.raises(ValueError,match='AI request limit'): store.authorize_ai(owner,shop)
    viewer=member(env,'viewer')
    with pytest.raises(PermissionError): store.authorize_ai(viewer,shop)
