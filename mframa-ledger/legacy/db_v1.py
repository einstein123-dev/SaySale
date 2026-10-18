"""Atomic ledger operations; money is stored as integer pesewas."""
import sqlite3
from contextlib import contextmanager
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

DB_PATH = Path(__file__).parent / 'ledger.sqlite3'


@contextmanager
def connect(path=None):
    c = sqlite3.connect(path or DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    try:
        with c:
            yield c
    finally:
        c.close()


def init_db(path=None):
    with connect(path) as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT OR IGNORE INTO metadata(key,value) VALUES ('generation','initial');
        CREATE TABLE IF NOT EXISTS products (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
          quantity_on_hand INTEGER NOT NULL CHECK(quantity_on_hand>=0),
          low_stock_threshold INTEGER NOT NULL CHECK(low_stock_threshold>=0));
        CREATE TABLE IF NOT EXISTS transactions (
          id TEXT PRIMARY KEY, created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
          type TEXT NOT NULL CHECK(type IN ('sale','expense','restock')),
          product_id INTEGER REFERENCES products(id), item_name TEXT,
          quantity INTEGER, unit_price_pesewas INTEGER, amount_pesewas INTEGER NOT NULL,
          note TEXT NOT NULL, source_text TEXT NOT NULL);
        ''')


def money(value):
    try:
        d = Decimal(str(value))
        if not d.is_finite() or d < 0 or d > 100000000 or d.as_tuple().exponent < -2:
            raise ValueError('Amounts must be nonnegative, at most 100,000,000, with at most two decimal places.')
        return int(d * 100)
    except (InvalidOperation, TypeError):
        raise ValueError('Enter a valid monetary amount.')


def whole(value, label, minimum=1):
    try:
        d = Decimal(str(value))
        if not d.is_finite() or d != d.to_integral_value() or not minimum <= d <= 100000000:
            raise ValueError()
        return int(d)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f'{label} must be a whole number between {minimum} and 100,000,000.')


def products(path=None):
    with connect(path) as c:
        return [dict(r) for r in c.execute('SELECT * FROM products ORDER BY name')]


def ledger(path=None):
    with connect(path) as c:
        return [dict(r) for r in c.execute('SELECT * FROM transactions ORDER BY created_at DESC, rowid DESC')]


def add_product(name, opening, threshold, path=None):
    if not isinstance(name, str):
        raise ValueError('Product name must be text.')
    name = name.strip()
    if not name or len(name) > 120:
        raise ValueError('Product name must have 1–120 characters.')
    with connect(path) as c:
        c.execute('INSERT INTO products(name,quantity_on_hand,low_stock_threshold) VALUES (?,?,?)',
                  (name, whole(opening, 'Opening stock', 0), whole(threshold, 'Threshold', 0)))


def set_threshold(product_id, threshold, path=None):
    with connect(path) as c:
        updated = c.execute('UPDATE products SET low_stock_threshold=? WHERE id=?', (whole(threshold, 'Threshold', 0), product_id))
        if updated.rowcount != 1:
            raise ValueError('Product no longer exists. Refresh inventory.')


def save_transaction(token, kind, product_id=None, quantity=None, unit_price=None,
                     expense_amount=None, note='', source_text='', path=None, expected_generation=None):
    if kind not in ('sale', 'expense', 'restock'):
        raise ValueError('Invalid transaction type.')
    if not isinstance(token, str) or not 1 <= len(token) <= 100:
        raise ValueError('Invalid confirmation identifier.')
    if not isinstance(note, str) or not isinstance(source_text, str):
        raise ValueError('Note and source must be text.')
    if len(note) > 500 or len(source_text) > 2000:
        raise ValueError('Note or source text is too long.')
    q = whole(quantity, 'Quantity') if kind != 'expense' else None
    price = money(unit_price) if kind != 'expense' and unit_price is not None else None
    if kind == 'sale' and price is None:
        raise ValueError('A sale requires a unit price.')
    amount = money(expense_amount) if kind == 'expense' else q * (price or 0)
    if amount > 10_000_000_000:
        raise ValueError('Transaction total exceeds GH₵100,000,000.')
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        if expected_generation is not None and c.execute(
                "SELECT value FROM metadata WHERE key='generation'").fetchone()[0] != expected_generation:
            raise ValueError('The demo was reset after this draft was created. Discard it and create a new draft.')
        if c.execute('SELECT 1 FROM transactions WHERE id=?', (token,)).fetchone():
            return False
        item = None
        if kind != 'expense':
            p = c.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
            if p is None:
                raise ValueError('Select an existing inventory product.')
            item = p['name']
            if kind == 'restock' and p['quantity_on_hand'] + q > 100000000:
                raise ValueError('Stock cannot exceed 100,000,000 units.')
            if kind == 'sale' and p['quantity_on_hand'] < q:
                raise ValueError(f"Insufficient stock: only {p['quantity_on_hand']} available.")
            c.execute('UPDATE products SET quantity_on_hand=quantity_on_hand+? WHERE id=?',
                      (-q if kind == 'sale' else q, product_id))
        c.execute('''INSERT INTO transactions
            (id,type,product_id,item_name,quantity,unit_price_pesewas,amount_pesewas,note,source_text)
            VALUES (?,?,?,?,?,?,?,?,?)''', (token, kind, product_id if item else None, item, q, price, amount, note, source_text))
    return True


def reset_demo(path=None):
    with connect(path) as c:
        c.execute("UPDATE metadata SET value=? WHERE key='generation'", (str(uuid.uuid4()),))
        c.execute('DELETE FROM transactions')
        c.execute('DELETE FROM products')
        c.executemany('INSERT INTO products(name,quantity_on_hand,low_stock_threshold) VALUES (?,?,?)',
                      [('Bottles of oil', 10, 5), ('Bags of rice', 20, 5), ('Bars of soap', 30, 8)])


def generation(path=None):
    with connect(path) as c:
        return c.execute("SELECT value FROM metadata WHERE key='generation'").fetchone()[0]
