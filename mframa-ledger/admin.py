"""Local-server operator recovery only. Never expose this command through the web UI."""
import argparse
import getpass
from auth import email_key, password_hash
import store


def main():
    parser=argparse.ArgumentParser(description='Local SaySale operator utility. Requires direct access to the database file.')
    parser.add_argument('action',choices=['reset-password'])
    parser.add_argument('email')
    args=parser.parse_args()
    print('Verify the account holder through a trusted, out-of-band process before resetting.')
    password=getpass.getpass('New password (12–128 characters): ')
    if password!=getpass.getpass('Repeat new password: '):
        raise SystemExit('Passwords do not match. No change made.')
    hashed=password_hash(password)
    store.init_db()
    with store.connection() as c:
        c.execute('BEGIN IMMEDIATE')
        user=c.execute('SELECT id FROM users WHERE email=?',(email_key(args.email),)).fetchone()
        if not user: raise SystemExit('Account not found. No change made.')
        c.execute('UPDATE users SET password_hash=? WHERE id=?',(hashed,user['id']))
        c.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
    print('Password reset. All sessions for this account have been revoked.')


if __name__=='__main__':
    main()
