"""
Send Onboarding Email via Gmail SMTP

This script sends a welcome email to new clients using Gmail SMTP with App Password.
Much simpler than OAuth - just requires a Gmail App Password.

Setup:
    1. Enable 2-Step Verification on your Google Account
    2. Generate an App Password at https://myaccount.google.com/apppasswords
    3. Add to .env file:
       GMAIL_ADDRESS=your-email@gmail.com
       GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

Usage:
    python send_onboarding_email.py --to "client@example.com" --subject "Welcome!" --body "Email content here"
"""

import argparse
import os
import smtplib
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

# Ensure execution directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from reviewer_agent import review_on_failure

# Load environment variables from .env
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = WORKSPACE_ROOT / ".env"


def load_env():
    """Load environment variables from .env file."""
    env_vars = {}
    if ENV_FILE.exists():
        with open(ENV_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
                    os.environ[key.strip()] = value.strip()
    return env_vars


def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email via Gmail SMTP."""
    
    # Load credentials
    load_env()
    gmail_address = os.environ.get("GMAIL_ADDRESS")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    
    if not gmail_address or not gmail_password:
        return {
            "success": False,
            "error": "Missing GMAIL_ADDRESS or GMAIL_APP_PASSWORD in .env file",
            "to": to,
            "subject": subject
        }
    
    # Remove spaces from app password (Google shows it with spaces)
    gmail_password = gmail_password.replace(" ", "")
    
    # Create message
    message = MIMEMultipart("alternative")
    message["From"] = gmail_address
    message["To"] = to
    message["Subject"] = subject
    
    # Plain text version
    text_part = MIMEText(body, "plain")
    message.attach(text_part)
    
    # HTML version (converts newlines to <br> for better formatting)
    html_body = body.replace("\n", "<br>")
    html_part = MIMEText(f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        {html_body}
    </body>
    </html>
    """, "html")
    message.attach(html_part)
    
    try:
        # Connect to Gmail SMTP with timeout
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(gmail_address, gmail_password)
            server.sendmail(gmail_address, to, message.as_string())
        
        return {
            "success": True,
            "to": to,
            "subject": subject,
            "from": gmail_address
        }
    
    except smtplib.SMTPAuthenticationError:
        return {
            "success": False,
            "error": "Authentication failed. Check your App Password and ensure 2-Step Verification is enabled.",
            "to": to,
            "subject": subject
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "to": to,
            "subject": subject
        }


@review_on_failure
def main():
    parser = argparse.ArgumentParser(
        description="Send onboarding email via Gmail SMTP"
    )
    parser.add_argument(
        "--to",
        required=True,
        help="Recipient email address"
    )
    parser.add_argument(
        "--subject",
        required=True,
        help="Email subject line"
    )
    parser.add_argument(
        "--body",
        required=True,
        help="Email body content"
    )

    args = parser.parse_args()

    print(f"Sending email to: {args.to}", flush=True)
    print(f"Subject: {args.subject}", flush=True)
    print("-" * 40, flush=True)

    result = send_email(args.to, args.subject, args.body)

    if result["success"]:
        print("Email sent successfully!")
        print(f"From: {result['from']}")
        print(f"To: {result['to']}")
    else:
        print("Failed to send email")
        print(f"Error: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
