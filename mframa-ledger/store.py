"""Global multi-shop backend. Every shop operation authenticates and authorizes.
Never accept a user ID or role from the browser as an authority.
"""
import json
import math
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from decimal import Decimal, InvalidOperation
from auth import email_key, password_hash, password_matches, token_hash
from intl import CURRENCIES, COUNTRIES, TIMEZONES, minor_units

DB_PATH=Path(os.environ.get('SAYSALE_DB_PATH',str(Path(__file__).parent/'saysale-global.sqlite3')))
RESTOCK_COVERAGE_DAYS=14
ROLES=('owner','manager','clerk','viewer')
PERMISSIONS={
 'owner': {'read','sale','expense','restock','inventory','team','settings','audit','reset','void'},
 'manager': {'read','sale','expense','restock','inventory','audit','void'},
 'clerk': {'read','sale'},
 'viewer': {'read'},
}
SESSION_SECONDS=8*60*60
DUMMY_HASH=password_hash('not-a-real-password-for-timing')

@contextmanager
def connection(path=None):
    file_path=Path(path or DB_PATH)
    try:
        fd=os.open(file_path,os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600)
        os.close(fd)
    except FileExistsError:
        pass
    conn=sqlite3.connect(file_path,timeout=15,check_same_thread=False)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db(path=None):
    with connection(path) as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,
          name TEXT NOT NULL,password_hash TEXT NOT NULL,created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),
          expires_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS login_attempts(identity TEXT PRIMARY KEY,failures INTEGER NOT NULL,locked_until REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS shops(id TEXT PRIMARY KEY,name TEXT NOT NULL,country TEXT NOT NULL,
          currency TEXT NOT NULL,timezone TEXT NOT NULL,generation TEXT NOT NULL,created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS memberships(shop_id TEXT REFERENCES shops(id),user_id TEXT REFERENCES users(id),
          role TEXT NOT NULL CHECK(role IN ('owner','manager','clerk','viewer')),PRIMARY KEY(shop_id,user_id));
        CREATE TABLE IF NOT EXISTS invitations(token_hash TEXT PRIMARY KEY,shop_id TEXT REFERENCES shops(id),
          email TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('manager','clerk','viewer')),
          expires_at REAL NOT NULL,created_by TEXT REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS products(id TEXT PRIMARY KEY,shop_id TEXT NOT NULL REFERENCES shops(id),
          name TEXT NOT NULL COLLATE NOCASE,quantity INTEGER NOT NULL CHECK(quantity>=0 AND quantity<=100000000),
          threshold INTEGER NOT NULL CHECK(threshold>=0),UNIQUE(shop_id,name));
        CREATE TABLE IF NOT EXISTS transactions(id TEXT NOT NULL,shop_id TEXT NOT NULL REFERENCES shops(id),
          created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
          type TEXT NOT NULL CHECK(type IN ('sale','expense','restock','void')),product_id TEXT REFERENCES products(id),
          item_name TEXT,quantity INTEGER,unit_price_minor INTEGER,amount_minor INTEGER,
          currency TEXT NOT NULL,note TEXT NOT NULL,source_text TEXT NOT NULL,created_by TEXT NOT NULL REFERENCES users(id),
          PRIMARY KEY(shop_id,id),CHECK(amount_minor IS NULL OR amount_minor>=0));
        CREATE TABLE IF NOT EXISTS audit_events(id INTEGER PRIMARY KEY,shop_id TEXT NOT NULL REFERENCES shops(id),
          user_id TEXT NOT NULL REFERENCES users(id),created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
          action TEXT NOT NULL,details TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ai_requests(user_id TEXT NOT NULL REFERENCES users(id),shop_id TEXT NOT NULL REFERENCES shops(id),created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS pending_drafts(id TEXT PRIMARY KEY,shop_id TEXT NOT NULL REFERENCES shops(id),
          created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
          source_channel TEXT NOT NULL,source_text TEXT,
          status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
          draft_json TEXT NOT NULL,confidence REAL NOT NULL DEFAULT 1.0,created_by TEXT REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS webhook_credentials(shop_id TEXT PRIMARY KEY REFERENCES shops(id),
          secret_hash TEXT NOT NULL,created_by TEXT NOT NULL REFERENCES users(id),created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS inbound_webhook_events(id TEXT PRIMARY KEY,shop_id TEXT NOT NULL REFERENCES shops(id),
          provider_event_id TEXT NOT NULL,source_channel TEXT NOT NULL,source_text TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'received' CHECK(status IN ('received','processing','processed','failed')),
          attempts INTEGER NOT NULL DEFAULT 0,created_by TEXT NOT NULL REFERENCES users(id),created_at REAL NOT NULL,
          updated_at REAL NOT NULL,last_error TEXT,result_json TEXT,
          UNIQUE(shop_id,provider_event_id));
        CREATE TABLE IF NOT EXISTS ledger_snapshots(id TEXT PRIMARY KEY,shop_id TEXT NOT NULL REFERENCES shops(id),
          created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
          trigger_action TEXT NOT NULL,trigger_reason TEXT NOT NULL,state_json TEXT NOT NULL,
          created_by TEXT NOT NULL REFERENCES users(id));
        CREATE INDEX IF NOT EXISTS ai_request_time ON ai_requests(created_at);
        CREATE INDEX IF NOT EXISTS product_shop ON products(shop_id);
        CREATE INDEX IF NOT EXISTS transaction_shop ON transactions(shop_id,created_at);
        CREATE INDEX IF NOT EXISTS pending_shop_status ON pending_drafts(shop_id,status);
        CREATE INDEX IF NOT EXISTS snapshot_shop ON ledger_snapshots(shop_id,created_at);
        CREATE INDEX IF NOT EXISTS webhook_queue ON inbound_webhook_events(status,created_at);
        ''')
        # Migrate existing transactions table if created prior to 'void' support
        tx_sql = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='transactions'").fetchone()
        if tx_sql and "'void'" not in tx_sql[0]:
            c.execute('PRAGMA foreign_keys=OFF')
            c.execute('''
            CREATE TABLE IF NOT EXISTS transactions_new(id TEXT NOT NULL,shop_id TEXT NOT NULL REFERENCES shops(id),
              created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
              type TEXT NOT NULL CHECK(type IN ('sale','expense','restock','void')),product_id TEXT REFERENCES products(id),
              item_name TEXT,quantity INTEGER,unit_price_minor INTEGER,amount_minor INTEGER,
              currency TEXT NOT NULL,note TEXT NOT NULL,source_text TEXT NOT NULL,created_by TEXT NOT NULL REFERENCES users(id),
              PRIMARY KEY(shop_id,id),CHECK(amount_minor IS NULL OR amount_minor>=0));
            ''')
            c.execute('INSERT OR IGNORE INTO transactions_new SELECT * FROM transactions;')
            c.execute('DROP TABLE transactions;')
            c.execute('ALTER TABLE transactions_new RENAME TO transactions;')
            c.execute('CREATE INDEX IF NOT EXISTS transaction_shop ON transactions(shop_id,created_at);')
            c.execute('PRAGMA foreign_keys=ON')


def _user(c,token):
    row=c.execute('''SELECT u.id,u.email,u.name FROM sessions s JOIN users u ON u.id=s.user_id
                     WHERE s.token_hash=? AND s.expires_at>?''',(token_hash(token),time.time())).fetchone()
    if not row:
        raise PermissionError('Your session expired. Please sign in again.')
    return dict(row)


def _access(c,token,shop_id,permission='read'):
    user=_user(c,token)
    row=c.execute('SELECT role FROM memberships WHERE shop_id=? AND user_id=?',(shop_id,user['id'])).fetchone()
    if not row or permission not in PERMISSIONS[row['role']]:
        raise PermissionError('You do not have permission for this action in this shop.')
    return user,row['role']


def _audit(c,shop_id,user_id,action,details):
    c.execute('INSERT INTO audit_events(shop_id,user_id,action,details) VALUES (?,?,?,?)',
              (shop_id,user_id,action,json.dumps(details)))


def _text(value,label,max_len,empty=False):
    if not isinstance(value,str) or len(value)>max_len or (not empty and not value.strip()):
        raise ValueError(f'{label}: enter {"0" if empty else "1"}–{max_len} characters.')
    return value.strip()


def whole(value,label,minimum=0):
    try:
        v=Decimal(str(value))
        if not v.is_finite() or v!=v.to_integral_value() or not minimum<=v<=100000000:
            raise ValueError()
        return int(v)
    except (InvalidOperation,TypeError,ValueError):
        raise ValueError(f'{label}: enter a whole number between {minimum} and 100,000,000.')


def register(email,name,password,path=None):
    email=email_key(email)
    name=_text(name,'Name',80)
    hashed=password_hash(password)
    with connection(path) as c:
        try:
            c.execute('INSERT INTO users VALUES (?,?,?,?,?)',(str(uuid.uuid4()),email,name,hashed,time.time()))
        except sqlite3.IntegrityError:
            raise ValueError('Unable to create account with these details. Try signing in instead.')


def login(email,password,path=None):
    # Lockout state is persisted and serialized so concurrent failed logins cannot bypass it.
    try:
        identity=email_key(email)
    except ValueError:
        identity=str(email)[:254].strip().lower()
    denied=False
    locked=False
    raw=None
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        now=time.time()
        attempt=c.execute('SELECT * FROM login_attempts WHERE identity=?',(identity,)).fetchone()
        if attempt and attempt['locked_until']>now:
            locked=True
        else:
            user=c.execute('SELECT * FROM users WHERE email=?',(identity,)).fetchone()
            valid=password_matches(password,user['password_hash'] if user else DUMMY_HASH)
            if not user or not valid:
                # Reset counter after a lockout expires; accumulate during active lockout-free streaks (locked_until==0).
                prior=attempt['failures'] if attempt and attempt['locked_until']==0 else 0
                fails=prior+1
                c.execute('INSERT OR REPLACE INTO login_attempts VALUES (?,?,?)',
                          (identity,fails,now+300 if fails>=5 else 0))
                denied=True
            else:
                c.execute('DELETE FROM login_attempts WHERE identity=?',(identity,))
                c.execute('DELETE FROM sessions WHERE expires_at<=?',(now,))
                raw=secrets.token_urlsafe(32)
                c.execute('INSERT INTO sessions VALUES (?,?,?)',(token_hash(raw),user['id'],now+SESSION_SECONDS))
    if locked:
        raise ValueError('Too many attempts. Try again in five minutes.')
    if denied:
        raise ValueError('Email or password is incorrect.')
    return raw


def current_user(token,path=None):
    with connection(path) as c:
        return _user(c,token)


def logout(token,path=None):
    with connection(path) as c:
        c.execute('DELETE FROM sessions WHERE token_hash=?',(token_hash(token),))


def change_password(token,current,new,path=None):
    hashed=password_hash(new)
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        user=_user(c,token)
        old=c.execute('SELECT password_hash FROM users WHERE id=?',(user['id'],)).fetchone()[0]
        if not password_matches(current,old):
            raise ValueError('Current password is incorrect.')
        c.execute('UPDATE users SET password_hash=? WHERE id=?',(hashed,user['id']))
        c.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))


def list_shops(token,path=None):
    with connection(path) as c:
        user=_user(c,token)
        return [dict(r) for r in c.execute('''SELECT s.*,m.role FROM shops s JOIN memberships m ON s.id=m.shop_id
            WHERE m.user_id=? ORDER BY s.name''',(user['id'],))]


def create_shop(token,name,country,currency,timezone,path=None):
    name=_text(name,'Shop name',100)
    if country not in COUNTRIES or currency not in CURRENCIES or timezone not in TIMEZONES:
        raise ValueError('Choose a supported country, currency and timezone.')
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        user=_user(c,token)
        shop_id=str(uuid.uuid4())
        c.execute('INSERT INTO shops VALUES (?,?,?,?,?,?,?)',(shop_id,name,country,currency,timezone,str(uuid.uuid4()),time.time()))
        c.execute('INSERT INTO memberships VALUES (?,?,?)',(shop_id,user['id'],'owner'))
        _audit(c,shop_id,user['id'],'shop.created',{'name':name,'currency':currency})
        return shop_id


def snapshot(token,shop_id,path=None):
    with connection(path) as c:
        c.execute('BEGIN')
        user,role=_access(c,token,shop_id)
        shop=dict(c.execute('SELECT * FROM shops WHERE id=?',(shop_id,)).fetchone())
        products=[dict(r) for r in c.execute('SELECT * FROM products WHERE shop_id=? ORDER BY name',(shop_id,))]
        rows=[dict(r) for r in c.execute('SELECT * FROM transactions WHERE shop_id=? ORDER BY created_at DESC,rowid DESC',(shop_id,))]
        pending_rows=c.execute("SELECT * FROM pending_drafts WHERE shop_id=? AND status='pending' ORDER BY created_at DESC",(shop_id,)).fetchall()
        pending=[]
        for pr in pending_rows:
            d=dict(pr)
            try: d['draft']=json.loads(d['draft_json'])
            except Exception: d['draft']={}
            pending.append(d)
        return {'shop':shop,'products':products,'transactions':rows,'role':role,'user':user,'pending':pending}


def add_product(token,shop_id,name,opening,threshold,path=None):
    name=_text(name,'Product name',120)
    opening=whole(opening,'Opening stock')
    threshold=whole(threshold,'Threshold')
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        user,_=_access(c,token,shop_id,'inventory')
        pid=str(uuid.uuid4())
        try:
            c.execute('INSERT INTO products VALUES (?,?,?,?,?)',(pid,shop_id,name,opening,threshold))
        except sqlite3.IntegrityError:
            raise ValueError('This product name already exists in your shop.')
        _audit(c,shop_id,user['id'],'product.created',{'id':pid,'name':name,'opening':opening})
        return pid


def set_threshold(token,shop_id,product_id,threshold,path=None):
    threshold=whole(threshold,'Threshold')
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        user,_=_access(c,token,shop_id,'inventory')
        updated=c.execute('UPDATE products SET threshold=? WHERE id=? AND shop_id=?',(threshold,product_id,shop_id))
        if updated.rowcount!=1:
            raise ValueError('Product not found in this shop.')
        _audit(c,shop_id,user['id'],'product.threshold',{'id':product_id,'threshold':threshold})


def save_transaction(token,shop_id,request_id,kind,currency,product_id=None,quantity=None,
                     unit_price=None,expense_amount=None,note='',source_text='',expected_generation=None,path=None):
    if kind not in ('sale','expense','restock'):
        raise ValueError('Choose a valid transaction type.')
    request_id=_text(request_id,'Request ID',100)
    note=_text(note,'Note',500,True)
    source_text=_text(source_text,'Source text',2000,True)
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        user,_=_access(c,token,shop_id,kind)
        shop=c.execute('SELECT * FROM shops WHERE id=?',(shop_id,)).fetchone()
        if shop['currency']!=currency:
            raise ValueError('Currency must match the shop currency. No automatic conversion is performed.')
        if expected_generation!=shop['generation']:
            raise ValueError('Shop data changed or was reset. Create a fresh draft.')
        if c.execute('SELECT 1 FROM transactions WHERE shop_id=? AND id=?',(shop_id,request_id)).fetchone():
            return False
        q=whole(quantity,'Quantity',1) if kind!='expense' else None
        price=minor_units(unit_price,currency) if kind!='expense' and unit_price is not None else None
        if kind=='sale' and price is None:
            raise ValueError('A sale requires a unit price.')
        amount=minor_units(expense_amount,currency) if kind=='expense' else q*price if price is not None else None
        if amount is not None and amount>minor_units(100000000,currency):
            raise ValueError('Transaction total exceeds 100,000,000.')
        item=None
        if kind!='expense':
            p=c.execute('SELECT * FROM products WHERE id=? AND shop_id=?',(product_id,shop_id)).fetchone()
            if not p:
                raise ValueError('Select a product belonging to this shop.')
            item=p['name']
            next_qty=p['quantity']+(-q if kind=='sale' else q)
            if next_qty<0:
                raise ValueError(f"Insufficient stock: {p['quantity']} units available.")
            if next_qty>100000000:
                raise ValueError('Stock cannot exceed 100,000,000 units.')
            c.execute('UPDATE products SET quantity=? WHERE id=? AND shop_id=?',(next_qty,product_id,shop_id))
        c.execute('''INSERT INTO transactions(id,shop_id,type,product_id,item_name,quantity,unit_price_minor,amount_minor,currency,note,source_text,created_by)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (request_id,shop_id,kind,product_id if item else None,item,q,price,amount,currency,note,source_text,user['id']))
        _audit(c,shop_id,user['id'],'transaction.saved',{'id':request_id,'type':kind,'amount_minor':amount,'currency':currency})
        return True


def team(token,shop_id,path=None):
    with connection(path) as c:
        _access(c,token,shop_id,'team')
        return [dict(r) for r in c.execute('''SELECT u.id,u.name,u.email,m.role FROM memberships m
                     JOIN users u ON m.user_id=u.id WHERE m.shop_id=? ORDER BY u.name''',(shop_id,))]


def create_invite(token,shop_id,email,role,path=None):
    email=email_key(email)
    if role not in ('manager','clerk','viewer'):
        raise ValueError('Choose manager, clerk or viewer.')
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        user,_=_access(c,token,shop_id,'team')
        if c.execute('SELECT 1 FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.shop_id=? AND u.email=?',(shop_id,email)).fetchone():
            raise ValueError('This account is already a member.')
        raw=secrets.token_urlsafe(32)
        c.execute('DELETE FROM invitations WHERE shop_id=? AND email=?',(shop_id,email))
        c.execute('INSERT INTO invitations VALUES (?,?,?,?,?,?)',(token_hash(raw),shop_id,email,role,time.time()+48*3600,user['id']))
        _audit(c,shop_id,user['id'],'invite.created',{'email':email,'role':role})
        return raw


def accept_invite(token,code,path=None):
    try:
        code_hash=token_hash(code.strip())
    except (PermissionError,AttributeError):
        raise ValueError('Invitation is invalid, expired, or addressed to a different account.')
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        user=_user(c,token)
        invite=c.execute('SELECT * FROM invitations WHERE token_hash=? AND expires_at>?',(code_hash,time.time())).fetchone()
        if not invite or invite['email']!=user['email']:
            raise ValueError('Invitation is invalid, expired, or addressed to a different account.')
        if c.execute('SELECT 1 FROM memberships WHERE shop_id=? AND user_id=?',(invite['shop_id'],user['id'])).fetchone():
            raise ValueError('You are already a member.')
        c.execute('INSERT INTO memberships VALUES (?,?,?)',(invite['shop_id'],user['id'],invite['role']))
        c.execute('DELETE FROM invitations WHERE token_hash=?',(code_hash,))
        _audit(c,invite['shop_id'],user['id'],'invite.accepted',{'role':invite['role']})
        return invite['shop_id']


def change_role(token,shop_id,member_id,role,path=None):
    if role not in ('manager','clerk','viewer'):
        raise ValueError('Role must be manager, clerk or viewer.')
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        user,_=_access(c,token,shop_id,'team')
        changed=c.execute("UPDATE memberships SET role=? WHERE shop_id=? AND user_id=? AND role!='owner'",(role,shop_id,member_id))
        if changed.rowcount!=1:
            raise ValueError('Member not found, or owner role cannot be changed.')
        _audit(c,shop_id,user['id'],'member.role',{'member_id':member_id,'role':role})


def remove_member(token,shop_id,member_id,path=None):
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        user,_=_access(c,token,shop_id,'team')
        removed=c.execute("DELETE FROM memberships WHERE shop_id=? AND user_id=? AND role!='owner'",(shop_id,member_id))
        if removed.rowcount!=1:
            raise ValueError('Member not found, or owner cannot be removed.')
        # Revoke any outstanding invitation too, to prevent immediate rejoining.
        email=c.execute('SELECT email FROM users WHERE id=?',(member_id,)).fetchone()[0]
        c.execute('DELETE FROM invitations WHERE shop_id=? AND email=?',(shop_id,email))
        _audit(c,shop_id,user['id'],'member.removed',{'member_id':member_id})


def pending_invites(token,shop_id,path=None):
    with connection(path) as c:
        _access(c,token,shop_id,'team')
        return [dict(r) for r in c.execute('SELECT email,role,expires_at FROM invitations WHERE shop_id=? AND expires_at>?',(shop_id,time.time()))]


def revoke_invite(token,shop_id,email,path=None):
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        user,_=_access(c,token,shop_id,'team')
        c.execute('DELETE FROM invitations WHERE shop_id=? AND email=?',(shop_id,email))
        _audit(c,shop_id,user['id'],'invite.revoked',{'email':email})


def audit(token,shop_id,path=None):
    with connection(path) as c:
        _access(c,token,shop_id,'audit')
        return [dict(r) for r in c.execute('SELECT * FROM audit_events WHERE shop_id=? ORDER BY id DESC LIMIT 200',(shop_id,))]


def update_shop(token,shop_id,name,country,timezone,path=None):
    name=_text(name,'Shop name',100)
    if country not in COUNTRIES or timezone not in TIMEZONES:
        raise ValueError('Choose a supported country and timezone.')
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        user,_=_access(c,token,shop_id,'settings')
        c.execute('UPDATE shops SET name=?,country=?,timezone=? WHERE id=?',(name,country,timezone,shop_id))
        _audit(c,shop_id,user['id'],'shop.updated',{'name':name,'country':country,'timezone':timezone})


def reset_demo(token,shop_id,path=None):
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        user,_=_access(c,token,shop_id,'reset')
        c.execute('DELETE FROM transactions WHERE shop_id=?',(shop_id,))
        c.execute('DELETE FROM products WHERE shop_id=?',(shop_id,))
        c.execute('UPDATE shops SET generation=? WHERE id=?',(str(uuid.uuid4()),shop_id))
        for name,qty,threshold in [('Cooking oil',10,5),('Rice',20,5),('Soap',30,8)]:
            c.execute('INSERT INTO products VALUES (?,?,?,?,?)',(str(uuid.uuid4()),shop_id,name,qty,threshold))
        _audit(c,shop_id,user['id'],'demo.reset',{})


def authorize_ai(token,shop_id,path=None):
    """Check live membership and consume a bounded AI-attempt budget before API calls."""
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        user,role=_access(c,token,shop_id)
        if not any(k in PERMISSIONS[role] for k in ('sale','expense','restock')):
            raise PermissionError('Your role cannot perform this action.')
        now=time.time()
        c.execute('DELETE FROM ai_requests WHERE created_at<?',(now-86400,))
        personal=c.execute('SELECT count(*) FROM ai_requests WHERE user_id=? AND created_at>?',(user['id'],now-60)).fetchone()[0]
        shop_total=c.execute('SELECT count(*) FROM ai_requests WHERE shop_id=? AND created_at>?',(shop_id,now-86400)).fetchone()[0]
        if personal>=5 or shop_total>=50:
            raise ValueError('AI request limit reached (5 per user/minute, 50 per shop/24 hours). Use manual entry or try later.')
        c.execute('INSERT INTO ai_requests VALUES (?,?,?)',(user['id'],shop_id,now))


def save_pending_draft(shop_id,source_channel,source_text,draft,confidence=1.0,user_id=None,path=None):
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        draft_id=str(uuid.uuid4())
        draft_str=json.dumps(draft)
        c.execute('''INSERT INTO pending_drafts(id,shop_id,source_channel,source_text,status,draft_json,confidence,created_by)
                     VALUES (?,?,?,?,?,?,?,?)''',
                  (draft_id,shop_id,source_channel[:50],source_text[:2000] if source_text else '',
                   'pending',draft_str,max(0.0,min(1.0,float(confidence))),user_id))
        return draft_id


def create_webhook_secret(token,shop_id,path=None):
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        user,_=_access(c,token,shop_id,'settings')
        secret='sswh_'+secrets.token_urlsafe(36)
        digest=__import__('hashlib').sha256(secret.encode()).hexdigest()
        c.execute('INSERT OR REPLACE INTO webhook_credentials VALUES (?,?,?,?)',
                  (shop_id,digest,user['id'],time.time()))
        _audit(c,shop_id,user['id'],'webhook.secret.rotated',{})
        return secret


def revoke_webhook_secret(token,shop_id,path=None):
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        user,_=_access(c,token,shop_id,'settings')
        c.execute('DELETE FROM webhook_credentials WHERE shop_id=?',(shop_id,))
        _audit(c,shop_id,user['id'],'webhook.secret.revoked',{})


def accept_webhook_event(shop_id,secret,provider_event_id,source_channel,source_text,path=None):
    if not isinstance(secret,str) or len(secret)>200:
        raise PermissionError('Invalid webhook credential.')
    if not all(isinstance(value,str) and value.strip() for value in (provider_event_id,source_channel,source_text)):
        raise ValueError('Event ID, source channel and text are required.')
    if len(provider_event_id)>200 or len(source_channel)>50 or len(source_text)>5000:
        raise ValueError('Webhook event exceeds the supported field length.')
    digest=__import__('hashlib').sha256(secret.encode()).hexdigest()
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        credential=c.execute('SELECT secret_hash,created_by FROM webhook_credentials WHERE shop_id=?',(shop_id,)).fetchone()
        if not credential or not secrets.compare_digest(digest,credential['secret_hash']):
            raise PermissionError('Invalid webhook credential.')
        event_id=str(uuid.uuid4())
        now=time.time()
        try:
            c.execute('''INSERT INTO inbound_webhook_events(id,shop_id,provider_event_id,source_channel,source_text,
                      created_by,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)''',
                      (event_id,shop_id,provider_event_id.strip(),source_channel.strip(),source_text.strip(),
                       credential['created_by'],now,now))
            return {'event_id':event_id,'duplicate':False,'status':'received'}
        except sqlite3.IntegrityError:
            row=c.execute('SELECT id,status FROM inbound_webhook_events WHERE shop_id=? AND provider_event_id=?',
                          (shop_id,provider_event_id.strip())).fetchone()
            return {'event_id':row['id'],'duplicate':True,'status':row['status']}


def claim_webhook_event(path=None):
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute("UPDATE inbound_webhook_events SET status='received',updated_at=? WHERE status='processing' AND updated_at<?",
                  (time.time(),time.time()-120))
        row=c.execute("SELECT * FROM inbound_webhook_events WHERE status='received' ORDER BY created_at LIMIT 1").fetchone()
        if not row:
            return None
        now=time.time()
        c.execute("UPDATE inbound_webhook_events SET status='processing',attempts=attempts+1,updated_at=? WHERE id=?",
                  (now,row['id']))
        return dict(row)


def webhook_shop_context(shop_id,path=None):
    with connection(path) as c:
        row=c.execute('SELECT id,currency FROM shops WHERE id=?',(shop_id,)).fetchone()
        if not row:
            return None
        return dict(row)


def authorize_webhook_ai(event,path=None):
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('''SELECT e.shop_id,e.created_by FROM inbound_webhook_events e
          JOIN memberships m ON m.shop_id=e.shop_id AND m.user_id=e.created_by AND m.role='owner'
          WHERE e.id=? AND e.status='processing' ''',(event['id'],)).fetchone()
        if not row:
            raise PermissionError('Webhook owner is no longer authorized.')
        now=time.time()
        c.execute('DELETE FROM ai_requests WHERE created_at<?',(now-86400,))
        personal=c.execute('SELECT count(*) FROM ai_requests WHERE user_id=? AND created_at>?',(row['created_by'],now-60)).fetchone()[0]
        shop_total=c.execute('SELECT count(*) FROM ai_requests WHERE shop_id=? AND created_at>?',(row['shop_id'],now-86400)).fetchone()[0]
        if personal>=5 or shop_total>=50:
            raise ValueError('AI request limit reached (5 per user/minute, 50 per shop/24 hours).')
        c.execute('INSERT INTO ai_requests VALUES (?,?,?)',(row['created_by'],row['shop_id'],now))


def finish_webhook_event(event_id,drafts,path=None):
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        event=c.execute("SELECT * FROM inbound_webhook_events WHERE id=? AND status='processing'",(event_id,)).fetchone()
        if not event:
            return False
        for draft in drafts:
            draft_id=str(uuid.uuid4())
            c.execute('''INSERT INTO pending_drafts(id,shop_id,source_channel,source_text,status,draft_json,confidence,created_by)
              VALUES (?,?,?,?,?,?,?,?)''',(draft_id,event['shop_id'],event['source_channel'][:50],event['source_text'][:2000],
              'pending',json.dumps(draft),max(0.0,min(1.0,float(draft.get('confidence',0.5)))),event['created_by']))
        c.execute("UPDATE inbound_webhook_events SET status='processed',updated_at=?,result_json=?,last_error=NULL WHERE id=?",
                  (time.time(),json.dumps({'draft_count':len(drafts)}),event_id))
        _audit(c,event['shop_id'],event['created_by'],'webhook.event.processed',{'event_id':event_id,'draft_count':len(drafts)})
        return True


def fail_webhook_event(event_id,error,path=None):
    with connection(path) as c:
        c.execute("UPDATE inbound_webhook_events SET status='failed',updated_at=?,last_error=? WHERE id=? AND status='processing'",
                  (time.time(),str(error)[:500],event_id))


def retry_webhook_event(token,shop_id,event_id,path=None):
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        user,_=_access(c,token,shop_id,'settings')
        changed=c.execute("UPDATE inbound_webhook_events SET status='received',updated_at=?,last_error=NULL WHERE id=? AND shop_id=? AND status='failed'",
                          (time.time(),event_id,shop_id)).rowcount
        if changed:
            _audit(c,shop_id,user['id'],'webhook.event.retried',{'event_id':event_id})
        return bool(changed)


def list_webhook_events(token,shop_id,limit=20,path=None):
    with connection(path) as c:
        _access(c,token,shop_id,'settings')
        return [dict(row) for row in c.execute('''SELECT id,provider_event_id,source_channel,status,attempts,created_at,
          updated_at,last_error,result_json FROM inbound_webhook_events WHERE shop_id=? ORDER BY created_at DESC LIMIT ?''',
          (shop_id,max(1,min(int(limit),100))))]


def list_pending_drafts(token,shop_id,status='pending',path=None):
    with connection(path) as c:
        _access(c,token,shop_id,'read')
        rows=c.execute('''SELECT * FROM pending_drafts WHERE shop_id=? AND status=? ORDER BY created_at DESC''',
                       (shop_id,status)).fetchall()
        result=[]
        for r in rows:
            d=dict(r)
            try: d['draft']=json.loads(d['draft_json'])
            except Exception: d['draft']={}
            result.append(d)
        return result


def resolve_pending_draft(token,shop_id,draft_id,action,product_id=None,path=None):
    if action not in ('approve','reject'):
        raise ValueError('Invalid action. Choose approve or reject.')
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        user,_=_access(c,token,shop_id,'sale')
        row=c.execute('SELECT * FROM pending_drafts WHERE id=? AND shop_id=?',(draft_id,shop_id)).fetchone()
        if not row or row['status']!='pending':
            raise ValueError('Pending draft not found or already resolved.')
        if action=='reject':
            c.execute("UPDATE pending_drafts SET status='rejected' WHERE id=?",(draft_id,))
            _audit(c,shop_id,user['id'],'pending_draft.rejected',{'id':draft_id})
            return True
        draft=json.loads(row['draft_json'])
        kind=draft.get('type')
        if not kind or kind not in ('sale','expense','restock'):
            raise ValueError('Draft has no valid transaction type.')
        _access(c,token,shop_id,kind)
        shop=c.execute('SELECT * FROM shops WHERE id=?',(shop_id,)).fetchone()
        currency=shop['currency']
        draft_currency=draft.get('currency')
        if draft_currency and str(draft_currency).upper()!=currency:
            raise ValueError(f"Draft currency {draft_currency} does not match shop currency {currency}.")
        req_id=f"pd-{draft_id[:8]}-{secrets.token_hex(4)}"
        
        pid=product_id
        if kind!='expense' and not pid:
            item_name=(draft.get('item_name') or '').strip()
            p_match=c.execute('SELECT id FROM products WHERE shop_id=? AND name=? COLLATE NOCASE',(shop_id,item_name)).fetchone()
            if p_match:
                pid=p_match['id']
            else:
                raise ValueError(f"Product '{item_name}' not found. Please map to a product first.")
        
        q=whole(draft.get('quantity'),'Quantity',1) if kind!='expense' else None
        price=minor_units(draft.get('unit_price'),currency) if kind!='expense' and draft.get('unit_price') is not None else None
        if kind=='sale' and price is None:
            raise ValueError('A sale requires a unit price.')
        amount=minor_units(draft.get('amount_for_expense'),currency) if kind=='expense' else q*price if price is not None else None
        item=None
        if kind!='expense':
            p=c.execute('SELECT * FROM products WHERE id=? AND shop_id=?',(pid,shop_id)).fetchone()
            if not p:
                raise ValueError('Product does not belong to this shop.')
            item=p['name']
            next_qty=p['quantity']+(-q if kind=='sale' else q)
            if next_qty<0:
                raise ValueError(f"Insufficient stock: {p['quantity']} units available.")
            c.execute('UPDATE products SET quantity=? WHERE id=? AND shop_id=?',(next_qty,pid,shop_id))
        
        c.execute('''INSERT INTO transactions(id,shop_id,type,product_id,item_name,quantity,unit_price_minor,amount_minor,currency,note,source_text,created_by)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (req_id,shop_id,kind,pid if item else None,item,q,price,amount,currency,
                   f"Approved from {row['source_channel']}",row['source_text'] or '',user['id']))
        c.execute("UPDATE pending_drafts SET status='approved' WHERE id=?",(draft_id,))
        _audit(c,shop_id,user['id'],'pending_draft.approved',{'id':draft_id,'transaction_id':req_id})
        return True


def get_shop_analytics(token,shop_id,days=30,path=None):
    """Safe aggregate analytics for CFO agent and executive summaries."""
    if not isinstance(days, int) or isinstance(days, bool) or days < 1:
        raise ValueError('Analytics window must be a positive whole number of days.')
    with connection(path) as c:
        _access(c,token,shop_id,'read')
        shop=dict(c.execute('SELECT * FROM shops WHERE id=?',(shop_id,)).fetchone())
        products=[dict(r) for r in c.execute('SELECT * FROM products WHERE shop_id=? ORDER BY name',(shop_id,))]
        tx_rows=[dict(r) for r in c.execute('''
            SELECT tx.* FROM transactions tx
            WHERE tx.shop_id=?
              AND NOT EXISTS (
                SELECT 1 FROM transactions reversal
                WHERE reversal.shop_id=tx.shop_id
                  AND reversal.type='void'
                  AND substr(reversal.note,1,length('Void of ' || tx.id))='Void of ' || tx.id
                  AND substr(reversal.note,length('Void of ' || tx.id)+1,1)=' '
              )
            ORDER BY tx.created_at DESC
        ''',(shop_id,))]
        recent_sales=c.execute('''SELECT sale.item_name,sale.quantity FROM transactions sale
                                  WHERE sale.shop_id=? AND sale.type='sale'
                                    AND julianday(sale.created_at)>=julianday('now',?)
                                    AND julianday(sale.created_at)<=julianday('now')
                                    AND NOT EXISTS (
                                      SELECT 1 FROM transactions reversal
                                      WHERE reversal.shop_id=sale.shop_id AND reversal.type='void'
                                        AND substr(reversal.note,1,length('Void of ' || sale.id))='Void of ' || sale.id
                                        AND substr(reversal.note,length('Void of ' || sale.id)+1,1)=' '
                                    )''',
                               (shop_id,f'-{days} days')).fetchall()
        
        sales_total=sum(r['amount_minor'] or 0 for r in tx_rows if r['type']=='sale')
        expense_total=sum(r['amount_minor'] or 0 for r in tx_rows if r['type']=='expense')
        net_cash=sales_total-expense_total
        sales_count=sum(1 for r in tx_rows if r['type']=='sale')
        
        by_product={}
        for r in tx_rows:
            if r['type']=='sale' and r['item_name']:
                pname=r['item_name']
                if pname not in by_product:
                    by_product[pname]={'units_sold':0,'revenue_minor':0}
                by_product[pname]['units_sold']+=r['quantity'] or 0
                by_product[pname]['revenue_minor']+=r['amount_minor'] or 0

        recent_units_by_product={}
        for sale in recent_sales:
            if sale['item_name']:
                item_name=sale['item_name']
                recent_units_by_product[item_name]=recent_units_by_product.get(item_name,0)+(sale['quantity'] or 0)
        
        top_products=sorted([{'name':k,**v} for k,v in by_product.items()],key=lambda x:x['units_sold'],reverse=True)[:5]
        low_stock=[p for p in products if p['quantity']<p['threshold'] or p['quantity']==0]
        
        dir_estimates=[]
        restock_recommendations=[]
        for p in products:
            sold_count=recent_units_by_product.get(p['name'],0)
            daily_velocity=sold_count/days
            days_left=round(p['quantity']/daily_velocity,1) if daily_velocity>0 else None
            dir_estimates.append({
                'name': p['name'],
                'current_stock': p['quantity'],
                'threshold': p['threshold'],
                'daily_velocity': round(daily_velocity,2),
                'days_left': days_left,
                'urgent': p['quantity']<=p['threshold'] or (days_left is not None and days_left<=3)
            })
            if daily_velocity <= 0:
                if p['quantity'] <= p['threshold']:
                    restock_recommendations.append({
                        'name': p['name'],
                        'current_stock': p['quantity'],
                        'threshold': p['threshold'],
                        'daily_velocity': 0,
                        'recent_units_sold': 0,
                        'sales_window_days': days,
                        'days_left': None,
                        'target_coverage_days': RESTOCK_COVERAGE_DAYS,
                        'target_stock': None,
                        'suggested_quantity': None,
                        'reason': 'insufficient_sales_history',
                    })
                continue
            target_stock=max(p['threshold'],math.ceil(daily_velocity*RESTOCK_COVERAGE_DAYS))
            suggested_quantity=max(0,target_stock-p['quantity'])
            if suggested_quantity:
                restock_recommendations.append({
                    'name': p['name'],
                    'current_stock': p['quantity'],
                    'threshold': p['threshold'],
                    'daily_velocity': round(daily_velocity,4),
                    'recent_units_sold': sold_count,
                    'sales_window_days': days,
                    'days_left': days_left,
                    'target_coverage_days': RESTOCK_COVERAGE_DAYS,
                    'target_stock': target_stock,
                    'suggested_quantity': suggested_quantity,
                    'reason': 'recent_sales_coverage',
                })
            
        return {
            'shop': shop,
            'currency': shop['currency'],
            'sales_total_minor': sales_total,
            'expense_total_minor': expense_total,
            'net_cash_minor': net_cash,
            'sales_count': sales_count,
            'products_count': len(products),
            'low_stock': low_stock,
            'top_products': top_products,
            'inventory_runway': dir_estimates,
            'restock_recommendations': restock_recommendations,
            'recent_transactions': tx_rows[:10]
        }


def snapshot_ledger(token, shop_id, trigger_action='manual_snapshot', trigger_reason='', path=None):
    """Create a point-in-time audit snapshot of a shop's ledger and inventory."""
    trigger_reason = _text(trigger_reason, 'Trigger reason', 500, empty=True)
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        user, _ = _access(c, token, shop_id, 'audit')
        shop = dict(c.execute('SELECT * FROM shops WHERE id=?', (shop_id,)).fetchone())
        products = [dict(r) for r in c.execute('SELECT * FROM products WHERE shop_id=? ORDER BY name', (shop_id,))]
        transactions = [dict(r) for r in c.execute('SELECT * FROM transactions WHERE shop_id=? ORDER BY created_at DESC', (shop_id,))]
        
        state_dump = {
            'shop': shop,
            'products': products,
            'transactions': transactions,
            'timestamp': time.time(),
            'total_transactions': len(transactions),
            'total_products': len(products),
        }
        snap_id = f"snap-{int(time.time())}-{secrets.token_hex(4)}"
        c.execute('''INSERT INTO ledger_snapshots(id, shop_id, trigger_action, trigger_reason, state_json, created_by)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (snap_id, shop_id, trigger_action[:50], trigger_reason, json.dumps(state_dump), user['id']))
        _audit(c, shop_id, user['id'], 'ledger.snapshot', {'snapshot_id': snap_id, 'action': trigger_action})
        return snap_id


def list_snapshots(token, shop_id, limit=30, path=None):
    """Retrieve historical ledger snapshots for a shop."""
    with connection(path) as c:
        _access(c, token, shop_id, 'read')
        rows = c.execute('''SELECT s.id, s.shop_id, s.created_at, s.trigger_action, s.trigger_reason, s.created_by, u.name as user_name
                            FROM ledger_snapshots s
                            LEFT JOIN users u ON u.id = s.created_by
                            WHERE s.shop_id=? ORDER BY s.created_at DESC LIMIT ?''',
                         (shop_id, max(1, min(100, int(limit))))).fetchall()
        return [dict(r) for r in rows]


def get_snapshot(token, shop_id, snapshot_id, path=None):
    """Retrieve full details and state JSON of a specific snapshot."""
    with connection(path) as c:
        _access(c, token, shop_id, 'read')
        row = c.execute('SELECT * FROM ledger_snapshots WHERE id=? AND shop_id=?', (snapshot_id, shop_id)).fetchone()
        if not row:
            raise ValueError('Snapshot not found in this shop.')
        d = dict(row)
        try:
            d['state'] = json.loads(d['state_json'])
        except Exception:
            d['state'] = {}
        return d


def void_transaction(token, shop_id, transaction_id, reason, path=None):
    """Void a transaction with automatic pre-mutation snapshot, stock compensation, and audit trail."""
    reason = _text(reason, 'Void reason', 500, empty=False)
    with connection(path) as c:
        c.execute('BEGIN IMMEDIATE')
        user, role = _access(c, token, shop_id, 'void')
        shop = dict(c.execute('SELECT * FROM shops WHERE id=?', (shop_id,)).fetchone())
        tx = c.execute('SELECT * FROM transactions WHERE id=? AND shop_id=?', (transaction_id, shop_id)).fetchone()
        if not tx:
            raise ValueError('Transaction not found in this shop.')
        
        tx_dict = dict(tx)
        kind = tx_dict['type']
        
        # Check if already voided or is a void record
        if kind == 'void':
            raise ValueError('Cannot void an existing void transaction.')
        reversal = c.execute(
            "SELECT 1 FROM transactions WHERE shop_id=? AND type='void' AND substr(note,1,length(?))=? LIMIT 1",
            (shop_id, f'Void of {transaction_id} · Reason:', f'Void of {transaction_id} · Reason:'),
        ).fetchone()
        if reversal:
            raise ValueError('This transaction has already been voided.')
        note_str = tx_dict.get('note') or ''
        if 'Voided:' in note_str or '(Voided)' in note_str:
            raise ValueError('This transaction has already been voided.')
        
        # 1. Automatic Pre-Mutation Snapshot
        products_before = [dict(r) for r in c.execute('SELECT * FROM products WHERE shop_id=? ORDER BY name', (shop_id,))]
        txs_before = [dict(r) for r in c.execute('SELECT * FROM transactions WHERE shop_id=? ORDER BY created_at DESC', (shop_id,))]
        pre_state = {
            'shop': shop,
            'products': products_before,
            'transactions': txs_before,
            'target_transaction': tx_dict,
            'timestamp': time.time()
        }
        snap_id = f"snap-void-{int(time.time())}-{secrets.token_hex(4)}"
        c.execute('''INSERT INTO ledger_snapshots(id, shop_id, trigger_action, trigger_reason, state_json, created_by)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (snap_id, shop_id, f"void_tx:{transaction_id[:40]}", reason, json.dumps(pre_state), user['id']))
        
        # 2. Reverse inventory stock change
        pid = tx_dict.get('product_id')
        qty = tx_dict.get('quantity') or 0
        if pid and qty > 0 and kind in ('sale', 'restock'):
            p = c.execute('SELECT * FROM products WHERE id=? AND shop_id=?', (pid, shop_id)).fetchone()
            if p:
                # Voiding a sale returns items back to shelf (+qty)
                # Voiding a restock removes items from shelf (-qty)
                adjustment = qty if kind == 'sale' else -qty
                next_qty = p['quantity'] + adjustment
                if next_qty < 0:
                    raise ValueError(f"Cannot void restock: only {p['quantity']} units left on shelf, voiding requires removing {qty}.")
                if next_qty > 100000000:
                    raise ValueError('Resulting stock cannot exceed 100,000,000 units.')
                c.execute('UPDATE products SET quantity=? WHERE id=? AND shop_id=?', (next_qty, pid, shop_id))
        
        # 3. Create compensating reversal transaction
        void_tx_id = f"void-{transaction_id[:16]}-{secrets.token_hex(3)}"
        c.execute('''INSERT INTO transactions(id, shop_id, type, product_id, item_name, quantity, unit_price_minor, amount_minor, currency, note, source_text, created_by)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (void_tx_id, shop_id, 'void', pid, tx_dict.get('item_name'), qty,
                   tx_dict.get('unit_price_minor'), tx_dict.get('amount_minor'), tx_dict['currency'],
                   f"Void of {transaction_id} · Reason: {reason}",
                   f"Pre-mutation snapshot: {snap_id}", user['id']))
        
        # 4. Mark original transaction note as voided
        orig_note = tx_dict.get('note') or ''
        updated_note = f"{orig_note} (Voided: {reason})".strip()[:500]
        c.execute('UPDATE transactions SET note=? WHERE id=? AND shop_id=?', (updated_note, transaction_id, shop_id))
        
        # 5. Invalidate stale generations & log audit
        new_gen = str(uuid.uuid4())
        c.execute('UPDATE shops SET generation=? WHERE id=?', (new_gen, shop_id))
        _audit(c, shop_id, user['id'], 'transaction.voided', {
            'target_id': transaction_id,
            'void_tx_id': void_tx_id,
            'snapshot_id': snap_id,
            'reason': reason
        })
        return {'snapshot_id': snap_id, 'void_tx_id': void_tx_id}
