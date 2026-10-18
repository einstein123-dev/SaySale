"""Standard SMTP email service for SaySale.
Supports secure SSL and STARTTLS transports with HTML & plain text fallbacks.
"""
import os
import smtplib
import ssl
import logging
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def get_smtp_config():
    """Retrieve SMTP configuration from environment or Streamlit secrets."""
    host = os.getenv('SMTP_HOST')
    port = os.getenv('SMTP_PORT')
    username = os.getenv('SMTP_USERNAME')
    password = os.getenv('SMTP_PASSWORD')
    sender = os.getenv('SMTP_FROM_EMAIL') or os.getenv('SMTP_USERNAME')
    sender_name = os.getenv('SMTP_FROM_NAME', 'SaySale')
    use_tls = os.getenv('SMTP_USE_TLS', 'true').lower() in ('true', '1', 'yes')
    use_ssl = os.getenv('SMTP_USE_SSL', 'false').lower() in ('true', '1', 'yes')

    # Fallback to streamlit secrets if available
    if not host:
        try:
            import streamlit as st
            host = st.secrets.get('SMTP_HOST', '')
            port = st.secrets.get('SMTP_PORT', '')
            username = st.secrets.get('SMTP_USERNAME', '')
            password = st.secrets.get('SMTP_PASSWORD', '')
            sender = st.secrets.get('SMTP_FROM_EMAIL', '') or username
            sender_name = st.secrets.get('SMTP_FROM_NAME', 'SaySale')
            use_tls = str(st.secrets.get('SMTP_USE_TLS', 'true')).lower() in ('true', '1', 'yes')
            use_ssl = str(st.secrets.get('SMTP_USE_SSL', 'false')).lower() in ('true', '1', 'yes')
        except Exception:
            pass

    return {
        'host': (host or '').strip(),
        'port': int(port) if str(port or '').strip().isdigit() else (465 if use_ssl else 587),
        'username': (username or '').strip(),
        'password': (password or '').strip(),
        'sender': (sender or '').strip(),
        'sender_name': (sender_name or '').strip(),
        'use_tls': use_tls,
        'use_ssl': use_ssl,
        'configured': bool((host or '').strip() and (username or '').strip())
    }


def send_email(to_email: str, subject: str, body_text: str, body_html: str | None = None, config: dict | None = None, sender_name: str | None = None) -> bool:
    """Send an email using standard SMTP. Returns True on success, raises or returns False on failure."""
    cfg = config or get_smtp_config()
    if not cfg['configured']:
        logger.info("SMTP not configured. Skipping automated email delivery.")
        return False

    msg = EmailMessage()
    msg['Subject'] = subject
    from_name = (sender_name or cfg['sender_name']).strip()
    msg['From'] = f"{from_name} <{cfg['sender']}>" if from_name else cfg['sender']
    msg['To'] = to_email
    msg.set_content(body_text)

    if body_html:
        msg.add_alternative(body_html, subtype='html')

    context = ssl.create_default_context()

    if cfg['use_ssl']:
        with smtplib.SMTP_SSL(cfg['host'], cfg['port'], context=context, timeout=15) as server:
            if cfg['username'] and cfg['password']:
                server.login(cfg['username'], cfg['password'])
            server.send_message(msg)
    else:
        with smtplib.SMTP(cfg['host'], cfg['port'], timeout=15) as server:
            if cfg['use_tls']:
                server.starttls(context=context)
            if cfg['username'] and cfg['password']:
                server.login(cfg['username'], cfg['password'])
            server.send_message(msg)

    logger.info("Email successfully sent to %s via SMTP (%s)", to_email, cfg['host'])
    return True


def send_invitation_email(to_email: str, shop_name: str, role: str, inviter_name: str, invite_code: str, config: dict | None = None) -> bool:
    """Send an invitation email to a prospective teammate with the single-use invite code."""
    subject = f"You're invited to join {shop_name} on SaySale"
    
    body_text = f"""Hello,

{inviter_name} has invited you to join "{shop_name}" as a {role.capitalize()} on SaySale.

Your one-time invitation code is:
{invite_code}

This invitation code is linked to your email address ({to_email}) and will expire in 48 hours.

To join:
1. Create or sign in to your SaySale account at your shop's portal using this email address ({to_email}).
2. Go to Account -> Join shop.
3. Enter your invitation code and confirm.

Welcome aboard!
— The SaySale Team
"""

    body_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f4f7f4; margin: 0; padding: 20px; color: #1c3329; }}
  .card {{ max-width: 540px; margin: 20px auto; background: #ffffff; border-radius: 16px; border: 1px solid #e0e9df; padding: 32px; box-shadow: 0 4px 14px rgba(22, 55, 41, 0.05); }}
  .brand {{ font-size: 20px; font-weight: 700; color: #153e30; margin-bottom: 24px; }}
  .title {{ font-size: 22px; font-weight: 700; margin-bottom: 12px; color: #102f29; }}
  .badge {{ display: inline-block; padding: 4px 10px; background: #e8f3e5; color: #23543b; border-radius: 20px; font-size: 13px; font-weight: 600; text-transform: uppercase; }}
  .code-box {{ background: #f0f6ee; border: 2px dashed #a4c9a0; border-radius: 12px; padding: 18px; text-align: center; font-family: monospace; font-size: 22px; font-weight: 700; letter-spacing: 2px; color: #153e30; margin: 24px 0; }}
  .steps {{ background: #fafcfa; border-radius: 10px; padding: 16px; margin: 20px 0; font-size: 14px; line-height: 1.6; color: #375346; }}
  .footer {{ font-size: 12px; color: #7f978a; margin-top: 24px; text-align: center; }}
</style>
</head>
<body>
<div class="card">
  <div class="brand">SaySale</div>
  <div class="title">Join {shop_name}</div>
  <p><strong>{inviter_name}</strong> has invited you to join the team as <span class="badge">{role}</span>.</p>
  <p>Your one-time invitation code:</p>
  <div class="code-box">{invite_code}</div>
  <div class="steps">
    <strong>How to join:</strong>
    <ol style="margin-top: 8px; padding-left: 20px;">
      <li>Sign in to SaySale with <strong>{to_email}</strong>.</li>
      <li>Navigate to <strong>Account &rarr; Join shop</strong>.</li>
      <li>Paste the code above and click <strong>Join shop</strong>.</li>
    </ol>
  </div>
  <p style="font-size: 13px; color: #6b8476;">This code is valid for <strong>48 hours</strong> and can only be used once.</p>
  <div class="footer">SaySale &middot; Multilingual Multi-Shop Retail Ledger</div>
</div>
</body>
</html>
"""
    return send_email(to_email, subject, body_text, body_html, config=config, sender_name=shop_name)
