"""Password helpers. Sessions, throttling and permissions live in store.py."""
import hashlib
import secrets
import hmac
import re


def email_key(email):
    if not isinstance(email,str):
        raise ValueError('Ent=er an email address.')
    email=email.strip().lower()
    if len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
        raise ValueError('Enter a valid email address.')
    return email


def password_hash(password):
    if not isinstance(password,str) or not 12<=len(password)<=128:
        raise ValueError('Use a password with 12–128 characters.')
    salt=secrets.token_bytes(16)
    digest=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1,maxmem=64*1024*1024)
    return f'scrypt$16384$8$1${salt.hex()}${digest.hex()}'


def password_matches(password,encoded):
    if not isinstance(password,str) or len(password)>128:
        return False
    try:
        _,n,r,p,salt,digest=encoded.split('$')
        candidate=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=int(n),r=int(r),p=int(p),maxmem=64*1024*1024)
        return hmac.compare_digest(candidate.hex(),digest)
    except (ValueError,TypeError):
        return False


def token_hash(token):
    if not isinstance(token,str) or not 20<=len(token)<=200:
        raise PermissionError('Please sign in again.')
    return hashlib.sha256(token.encode()).hexdigest()
