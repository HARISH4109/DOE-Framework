"""
Send WhatsApp Message via Selenium (Contact Name Support)

This script launches a full Chrome browser controllable by Selenium to:
1. Open WhatsApp Web.
2. Search for a contact by NAME (not phone number).
3. Send a message.

It persists the login session to '.tmp/chrome_profile' so you only scan QR once.

Usage:
    python execution/send_whatsapp_selenium.py --name "Mom" --message "Hello"
"""

import argparse
import time
import sys
import json
from pathlib import Path

# Ensure execution directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from reviewer_agent import review_on_failure
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Constants
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = WORKSPACE_ROOT / ".tmp" / "chrome_profile"

def setup_driver():
    """Setup Chrome Driver with persistent profile."""
    options = Options()
    
    # Create profile dir if not exists
    if not PROFILE_DIR.exists():
        PROFILE_DIR.mkdir(parents=True)
    else:
        # Check and remove stale lock files
        for lock_name in ["SingletonLock", "lock"]:
            lock_path = PROFILE_DIR / lock_name
            if lock_path.exists():
                try:
                    lock_path.unlink()
                    print(f"🧹 Removed stale Chrome lock file: {lock_name}")
                except Exception as e:
                    print(f"⚠️ Warning: Could not remove {lock_name}: {e}. Ensure Chrome is fully closed.")
        
    # Use absolute path for user-data-dir
    options.add_argument(f"user-data-dir={PROFILE_DIR.absolute()}")
    
    # Other useful options
    options.add_argument("--start-maximized")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    
    # Initialize Driver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver


@review_on_failure
def send_message(names_or_payload, single_message=None):
    """
    Args:
        names_or_payload (str): Either a comma-separated list of names OR a JSON string.
        single_message (str, optional): Message to send if names_or_payload is just a list of names.
    """
    driver = setup_driver()
    
    # Parse Input
    targets = {} # Dict of {name: message}
    
    try:
        # Try parsing as JSON first
        targets = json.loads(names_or_payload)
        if not isinstance(targets, dict):
            # If valid JSON but not a dict (e.g. list), fallback
            raise ValueError("JSON must be a dictionary")
        print("📋 Loaded individual message payload.")
    except (json.JSONDecodeError, ValueError):
        # Fallback to Comma-Separated List
        if not single_message:
            print("❌ Error: You provided a list of names but no message!")
            sys.exit(1)
        
        names = [n.strip() for n in names_or_payload.split(',')]
        for name in names:
            targets[name] = single_message
        print(f"📋 Loaded bulk message payload for {len(targets)} contacts.")

    try:
        print("🌍 Opening WhatsApp Web...")
        driver.get("https://web.whatsapp.com")
        
        # 1. Wait for Login (Check for Search Box existence)
        print("⏳ Waiting for login/load (Please scan QR code if asked)...")
        wait = WebDriverWait(driver, 120) 
        
        search_box = wait.until(
            EC.presence_of_element_located((By.XPATH, (
                "//*[@id='side']//input | "
                "//input | "
                "//*[@id='side']//*[@contenteditable='true'] | "
                "//*[@contenteditable='true'][@data-tab='3'] | "
                "//*[@title='Search or start new chat'] | "
                "//div[contains(@class, 'lexical-rich-text-input')]//p"
            )))
        )
        print("✅ Logged in!")
        
        for contact_name, msg_content in targets.items():
            try:
                print(f"\n--- Processing: {contact_name} ---")
                
                # 2. Search for Contact
                print(f"🔍 Searching: {contact_name}...")
                search_box.click()
                search_box.send_keys(Keys.CONTROL + "a")
                search_box.send_keys(Keys.BACKSPACE)
                search_box.send_keys(contact_name)
                time.sleep(2) 
                search_box.send_keys(Keys.ENTER)
                
                # 3. Wait for Chat
                print("⏳ Opening chat...")
                message_box = wait.until(
                    EC.presence_of_element_located((By.XPATH, (
                        "//*[@id='main']//*[@contenteditable='true'] | "
                        "//*[@contenteditable='true'][@data-tab='10'] | "
                        "//*[@title='Type a message'] | "
                        "//footer//p[contains(@class, 'selectable-text')]"
                    )))
                )
                
                # 4. Send Message
                print(f"💬 Sending: {msg_content[:20]}...")
                message_box.click()
                
                for part in msg_content.split('\n'):
                    message_box.send_keys(part)
                    message_box.send_keys(Keys.SHIFT + Keys.ENTER)
                    
                message_box.send_keys(Keys.ENTER)
                print(f"✅ Sent to {contact_name}")
                
                time.sleep(2)
                
            except Exception as e:
                print(f"❌ Failed to send to {contact_name}: {e}")
                continue
        
        print("\n✅ All messages processed.")
        time.sleep(3)
        
    except Exception as e:
        print(f"❌ Global Error: {e}")
        driver.save_screenshot(str(WORKSPACE_ROOT / ".tmp" / "error_screenshot.png"))
        raise
    finally:
        time.sleep(2)
        try:
            driver.quit()
        except Exception:
            pass

@review_on_failure
def main():
    parser = argparse.ArgumentParser(description="Send WhatsApp via Selenium")
    parser.add_argument("--names", help="Comma-separated names OR JSON string {'Name':'Msg'}")
    parser.add_argument("--message", help="Single message (optional if using JSON)")
    # Backwards compatibility
    parser.add_argument("--name", help="Single name (deprecated)")
    
    args = parser.parse_args()
    
    # Handle arguments
    if args.names:
        send_message(args.names, args.message)
    elif args.name and args.message:
        send_message(args.name, args.message)
    else:
        print("❌ Error: Must provide --names (list/JSON) or --name + --message")
        sys.exit(1)


if __name__ == "__main__":
    main()
