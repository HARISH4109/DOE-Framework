# Onboard Client

> Send a personalized welcome email to a new client introducing them to the company and inviting them to a kickoff call.

## Goal
When instructed to "onboard client [email]", send a professional welcome email that introduces the company and includes a calendar booking link for a kickoff meeting.

## Inputs
- **Client Email**: The email address of the new client (required)
- **Client Name**: The client's name for personalization (optional, extract from email if not provided)
- **Company Bullets**: A brief list of bullet points about the company/services (provided at runtime)

## Tools/Scripts
- `execution/send_onboarding_email.py` - Sends the welcome email via Gmail API

## Steps
1. Parse the client email from the user's request
2. Ask for company bullet points if not provided
3. Generate the welcome email content with:
   - Warm greeting
   - Company introduction (from bullet points)
   - Value proposition
   - Kickoff call invitation with calendar link
   - Professional sign-off
4. Run the execution script: `python execution/send_onboarding_email.py --to [email] --subject "[Subject]" --body "[Body]"`
5. Confirm success to user

## Email Template Structure
```
Subject: Welcome to [Company Name] — Let's Get Started! 🚀

Hi [Name],

Welcome aboard! We're absolutely thrilled to have you join us as a client.

A bit about what we do:

[Company bullet points - one per line]

We can't wait to dive into your project and make it a success!

Next Step: Let's Schedule Your Kickoff Call

To get the ball rolling, I'd love to set up a quick 30-minute kickoff call where we can:

- Learn more about your goals and vision
- Walk you through our process
- Answer any questions you have

📅 Book your kickoff call here: [CALENDAR_LINK]

Looking forward to working with you!

Best regards,
Harish
```

## Outputs
- Confirmation that email was sent successfully
- Email subject and recipient logged

## Configuration
- **Sender Email**: harish14may05@gmail.com
- **Calendar Link**: https://calendly.com/your-company/kickoff (placeholder - update when ready)

## Edge Cases
- If email fails: Check credentials.json and token.json exist and are valid
- If OAuth token expired: Delete token.json and re-run to refresh
- If client email looks invalid: Ask user to confirm before sending

## Setup Requirements
Before first use, set up Gmail App Password:
1. Enable 2-Step Verification at https://myaccount.google.com/security
2. Generate App Password at https://myaccount.google.com/apppasswords
   - Select app: "Mail", device: "Windows Computer"
   - Copy the 16-character password
3. Add to `.env` file:
   ```
   GMAIL_ADDRESS=harish14may05@gmail.com
   GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
   ```

## Learnings
- On Windows PowerShell with a `cp1252` console, emoji status output can raise `UnicodeEncodeError` before SMTP is attempted. Keep `execution/send_onboarding_email.py` status prints ASCII-only unless stdout encoding is explicitly configured.
