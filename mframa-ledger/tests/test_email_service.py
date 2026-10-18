import os
from types import SimpleNamespace
import pytest
import email_service


def test_smtp_config_unconfigured_default(monkeypatch):
    for k in ['SMTP_HOST', 'SMTP_PORT', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'SMTP_FROM_EMAIL']:
        monkeypatch.delenv(k, raising=False)
    import streamlit as st
    monkeypatch.setattr(st, 'secrets', {})
    cfg = email_service.get_smtp_config()
    assert cfg['configured'] is False
    assert cfg['host'] == ''


def test_smtp_config_populated_from_env(monkeypatch):
    monkeypatch.setenv('SMTP_HOST', 'smtp.example.com')
    monkeypatch.setenv('SMTP_PORT', '587')
    monkeypatch.setenv('SMTP_USERNAME', 'bot@example.com')
    monkeypatch.setenv('SMTP_PASSWORD', 'secret123')
    monkeypatch.setenv('SMTP_FROM_EMAIL', 'invites@example.com')
    monkeypatch.setenv('SMTP_FROM_NAME', 'Shop Bot')
    monkeypatch.setenv('SMTP_USE_TLS', 'true')
    
    cfg = email_service.get_smtp_config()
    assert cfg['configured'] is True
    assert cfg['host'] == 'smtp.example.com'
    assert cfg['port'] == 587
    assert cfg['username'] == 'bot@example.com'
    assert cfg['sender'] == 'invites@example.com'
    assert cfg['sender_name'] == 'Shop Bot'
    assert cfg['use_tls'] is True


def test_send_invitation_email_mocked(monkeypatch):
    sent_messages = []
    
    class MockSMTP:
        def __init__(self, host, port, timeout=None):
            self.host = host
            self.port = port
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def starttls(self, context=None):
            pass
        def login(self, username, password):
            pass
        def send_message(self, msg):
            sent_messages.append(msg)

    monkeypatch.setattr(email_service.smtplib, 'SMTP', MockSMTP)
    
    config = {
        'host': 'smtp.mailtrap.io',
        'port': 2525,
        'username': 'user',
        'password': 'pass',
        'sender': 'noreply@mframa.global',
        'sender_name': 'SaySale',
        'use_tls': True,
        'use_ssl': False,
        'configured': True
    }
    
    ok = email_service.send_invitation_email(
        to_email='clerk@example.com',
        shop_name='Downtown Mart',
        role='clerk',
        inviter_name='Alice Owner',
        invite_code='secure-code-xyz',
        config=config
    )
    
    assert ok is True
    assert len(sent_messages) == 1
    msg = sent_messages[0]
    assert msg['To'] == 'clerk@example.com'
    assert 'Downtown Mart' in msg['Subject']
    payload = msg.get_body(preferencelist=('plain',)).get_content()
    assert 'secure-code-xyz' in payload
    assert 'Downtown Mart' in payload
    assert 'Alice Owner' in payload


def test_send_email_skips_when_not_configured(monkeypatch):
    for k in ['SMTP_HOST', 'SMTP_PORT', 'SMTP_USERNAME', 'SMTP_PASSWORD']:
        monkeypatch.delenv(k, raising=False)
    import streamlit as st
    monkeypatch.setattr(st, 'secrets', {})
    ok = email_service.send_email('nobody@example.com', 'Subj', 'Body')
    assert ok is False
