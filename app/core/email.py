# app/core/email.py
#
# Wraps fastapi-mail. Import send_invitation_email() wherever needed.
# In tests, EMAIL_ENABLED=false skips sending entirely.

from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from app.core.config import settings

import os

# Allow disabling email in tests via env var
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "true").lower() == "true"

_mail_config = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_FROM_NAME=settings.MAIL_FROM_NAME,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
)

_mailer = FastMail(_mail_config)


async def send_invitation_email(
    *,
    to_email: str,
    tenant_name: str,
    inviter_email: str,
    role_name: str,
    accept_url: str,
    expires_hours: int = 48,
) -> None:
    """Send an invitation email. Silently skips if EMAIL_ENABLED=false."""

    if not EMAIL_ENABLED:
        return

    html = _render_invitation_html(
        tenant_name=tenant_name,
        inviter_email=inviter_email,
        role_name=role_name,
        accept_url=accept_url,
        expires_hours=expires_hours,
    )

    message = MessageSchema(
        subject=f"You've been invited to join {tenant_name}",
        recipients=[to_email],
        body=html,
        subtype=MessageType.html,
    )

    await _mailer.send_message(message)


def _render_invitation_html(
    *,
    tenant_name: str,
    inviter_email: str,
    role_name: str,
    accept_url: str,
    expires_hours: int,
) -> str:
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>You've been invited</title>
  <style>
    body {{
      margin: 0; padding: 0;
      background-color: #f4f4f7;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      color: #333333;
    }}
    .wrapper {{
      max-width: 600px;
      margin: 40px auto;
      background: #ffffff;
      border-radius: 8px;
      overflow: hidden;
      box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }}
    .header {{
      background-color: #4f46e5;
      padding: 32px 40px;
      text-align: center;
    }}
    .header h1 {{
      margin: 0;
      color: #ffffff;
      font-size: 24px;
      font-weight: 700;
      letter-spacing: -0.5px;
    }}
    .body {{
      padding: 40px;
    }}
    .body p {{
      font-size: 16px;
      line-height: 1.6;
      margin: 0 0 16px;
      color: #555555;
    }}
    .role-badge {{
      display: inline-block;
      background-color: #ede9fe;
      color: #4f46e5;
      font-weight: 600;
      font-size: 14px;
      padding: 4px 12px;
      border-radius: 20px;
      margin: 0 4px;
      text-transform: capitalize;
    }}
    .cta-container {{
      text-align: center;
      margin: 32px 0;
    }}
    .cta-button {{
      display: inline-block;
      background-color: #4f46e5;
      color: #ffffff !important;
      text-decoration: none;
      font-size: 16px;
      font-weight: 600;
      padding: 14px 36px;
      border-radius: 6px;
      letter-spacing: 0.3px;
    }}
    .expiry-note {{
      font-size: 13px;
      color: #999999;
      text-align: center;
      margin-top: 8px;
    }}
    .divider {{
      border: none;
      border-top: 1px solid #eeeeee;
      margin: 32px 0;
    }}
    .footer {{
      padding: 24px 40px;
      text-align: center;
      font-size: 12px;
      color: #aaaaaa;
      background-color: #fafafa;
    }}
    .footer a {{
      color: #4f46e5;
      text-decoration: none;
    }}
    .url-fallback {{
      font-size: 12px;
      color: #aaaaaa;
      word-break: break-all;
      text-align: center;
    }}
  </style>
</head>
<body>
  <div class="wrapper">

    <div class="header">
      <h1>You're invited to {tenant_name}</h1>
    </div>

    <div class="body">
      <p>Hi there,</p>

      <p>
        <strong>{inviter_email}</strong> has invited you to join
        <strong>{tenant_name}</strong> as a
        <span class="role-badge">{role_name}</span>.
      </p>

      <p>
        Click the button below to accept your invitation and set up your account.
        This link will expire in <strong>{expires_hours} hours</strong>.
      </p>

      <div class="cta-container">
        <a href="{accept_url}" class="cta-button">Accept Invitation</a>
        <p class="expiry-note">Expires in {expires_hours} hours</p>
      </div>

      <hr class="divider" />

      <p>If the button doesn't work, copy and paste this link into your browser:</p>
      <p class="url-fallback">{accept_url}</p>

      <hr class="divider" />

      <p>
        If you didn't expect this invitation or believe it was sent in error,
        you can safely ignore this email.
      </p>
    </div>

    <div class="footer">
      <p>
        This email was sent by {tenant_name} via
        <a href="#">SaaS Platform</a>.
      </p>
      <p>
        &copy; 2026 SaaS Platform. All rights reserved.
      </p>
    </div>

  </div>
</body>
</html>
"""