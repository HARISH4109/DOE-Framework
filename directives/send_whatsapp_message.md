# Send WhatsApp Message

> Send WhatsApp messages to contacts by name using a Selenium-controlled browser.

## Goal
Automate sending WhatsApp messages to one or multiple contacts identified by their name (as saved in your phone). This uses a real Chrome browser instance to interact with WhatsApp Web.

## Inputs
- **Contact Names**: 
  - A single name (e.g., "Mom")
  - A comma-separated list (e.g., "Mom, Dad, Boss")
  - Or a JSON string mapping names to specific messages (e.g., `{"Mom": "Hi", "Dad": "Hello"}`)
- **Message**: The text content to send (required if using a list of names).

## Tools/Scripts
- `execution/send_whatsapp_selenium.py`

## Steps
1. **Identify Contacts**: Determine which contact(s) to message. Note: Names must match EXACTLY how they appear in your WhatsApp contact list.
2. **Formulate Message**: Create the message text.
3. **Execute Script**:
   - **Single/Bulk (Same Message)**:
     ```bash
     python execution/send_whatsapp_selenium.py --names "Contact1, Contact2" --message "Hello there"
     ```
   - **Custom Messages (JSON)**:
     ```bash
     python execution/send_whatsapp_selenium.py --names '{"Contact1": "Specific msg", "Contact2": "Other msg"}'
     ```

## Edge Cases
- **First Run / Logged Out**: The script will open Chrome. You MUST scan the QR code with your phone to log in. The session maps to `.tmp/chrome_profile` and will persist for future runs.
- **Contact Not Found**: If the name doesn't match exactly, the script will log an error for that contact and proceed to the next one.
- **Browser Conflict**: Ensure no other Selenium instances are locking the `.tmp/chrome_profile` directory.

## Learnings
- WhatsApp Web requires a real browser environment; headless mode often triggers anti-bot detections.
- The `--names` argument is flexible and supports both simple lists and complex JSON payloads.
