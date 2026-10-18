import sqlite3
import store

print("1. Testing real database connection and table integrity...")
store.init_db()

with store.connection() as c:
    tx_sql = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='transactions'").fetchone()[0]
    print("Transactions table schema:")
    print(tx_sql)
    assert "'void'" in tx_sql, "CHECK constraint missing 'void'!"

    snap_sql = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='ledger_snapshots'").fetchone()[0]
    print("\nLedger snapshots table schema:")
    print(snap_sql)

    # Check for existing shops
    shops = c.execute("SELECT s.id, s.name, s.currency, s.generation, count(t.id) as tx_count FROM shops s LEFT JOIN transactions t ON t.shop_id = s.id GROUP BY s.id").fetchall()
    print(f"\nFound {len(shops)} shop(s) in database:")
    for s in shops:
        print(f" - Shop '{s['name']}' (ID: {s['id']}): {s['tx_count']} transaction(s), Currency: {s['currency']}")

print("\n2. Simulating end-to-end transaction creation -> snapshot -> void reversal on actual DB...")
with store.connection() as c:
    user = c.execute("SELECT id, email FROM users LIMIT 1").fetchone()
    if user:
        shop = c.execute("SELECT id FROM shops LIMIT 1").fetchone()
        if shop:
            # Generate mock token for testing
            raw_token = "live_verification_token_" + "x"*30
            c.execute("INSERT OR REPLACE INTO sessions VALUES (?, ?, ?)",
                      (store.token_hash(raw_token), user['id'], 9999999999.0))
            
            p = c.execute("SELECT id, name, quantity FROM products WHERE shop_id=? LIMIT 1", (shop['id'],)).fetchone()
            if p:
                print(f"Target product: '{p['name']}', current stock: {p['quantity']}")
                gen = c.execute("SELECT generation FROM shops WHERE id=?", (shop['id'],)).fetchone()['generation']
                curr = c.execute("SELECT currency FROM shops WHERE id=?", (shop['id'],)).fetchone()['currency']
                
                # Test sale
                tx_id = f"test-verify-{int(store.time.time())}"
                store.save_transaction(raw_token, shop['id'], tx_id, 'sale', curr,
                                       product_id=p['id'], quantity=1, unit_price=10.0,
                                       note="Verification test sale", expected_generation=gen)
                
                stock_after_sale = c.execute("SELECT quantity FROM products WHERE id=?", (p['id'],)).fetchone()['quantity']
                print(f"Stock after 1 unit sale: {stock_after_sale} (expected: {p['quantity'] - 1})")
                assert stock_after_sale == p['quantity'] - 1
                
                # Test voiding
                print("Executing void_transaction on live database...")
                void_res = store.void_transaction(raw_token, shop['id'], tx_id, reason="Live integrity check")
                print(f"Void succeeded! Snapshot ID: {void_res['snapshot_id']}, Void Tx ID: {void_res['void_tx_id']}")
                
                stock_restored = c.execute("SELECT quantity FROM products WHERE id=?", (p['id'],)).fetchone()['quantity']
                print(f"Stock restored to shelf: {stock_restored} (expected: {p['quantity']})")
                assert stock_restored == p['quantity']
                
                # Clean up session
                c.execute("DELETE FROM sessions WHERE token_hash=?", (store.token_hash(raw_token),))
                print("\nALL LIVE CHECKS PASSED PERFECTLY ON REAL DATABASE.")
            else:
                print("No product in shop to test transaction.")
    else:
        print("No users registered yet.")
