import requests
import os
from bs4 import BeautifulSoup
from datetime import datetime
import zoneinfo # Requires Python 3.9+
import re # Import the regular expression module

# --- Configuration ---
# Secrets loaded from GitHub Actions environment
DESCO_ACCOUNT_NO = os.environ.get('DESCO_ACCOUNT_NO')
BOT_TOKEN = os.environ.get('BOT_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

YOUR_TIMEZONE = "Asia/Dhaka" # Your local timezone

### --- ACTION NEEDED: Update these based on DESCO Website Inspection (Step 3) --- ###
# 1. Replace with the actual URL of the DESCO login page
LOGIN_URL = 'https://prepaid.desco.org.bd/customer/#/customer-login' #<- REPLACE IF NEEDED

# 2. Replace with the actual URL of the page showing the balance AFTER login
BALANCE_PAGE_URL = 'https://prepaid.desco.org.bd/customer/#/customer-info' #<- REPLACE IF NEEDED (might be same as login result)

# 3. Replace 'account_no' with the actual 'name' attribute of the account number input field found in Step 3.1
ACCOUNT_NO_FIELD_NAME = 'account_no' #<- REPLACE IF NEEDED (e.g., 'meter_no', 'customer_id')

# 4. Based on Step 3.2, these should target the balance structure found in the screenshot
BALANCE_ELEMENT_TAG = 'span'     # The tag containing the balance value itself
BALANCE_ELEMENT_ID = None        # Likely None based on screenshot
BALANCE_ELEMENT_CLASS = None     # Likely None based on screenshot (using parent <p> instead)
### -------------------------------------------------------------------------------------- ###

# --- Functions ---

def send_telegram_message(raw_balance_text):
    """Sends the formatted message, adding a recharge reminder if balance is low."""
    tz = zoneinfo.ZoneInfo(YOUR_TIMEZONE)
    now = datetime.now(tz)
    timestamp = now.strftime('%d-%b-%Y %I:%M %p')
    message = f"DESCO Balance Update ({timestamp}):\n\n{raw_balance_text}"
    recharge_reminder = "\n\n⚠️ Low Balance! Please recharge soon."

    try:
        cleaned_balance = re.sub(r'[^\d.]', '', raw_balance_text)
        if cleaned_balance:
            balance_float = float(cleaned_balance)
            print(f"Numeric balance extracted: {balance_float}")
            if balance_float < 100:
                message += recharge_reminder
                print("Low balance detected, adding recharge reminder.")
        else:
            # Handle cases where balance text might be non-numeric words like "Unavailable" or "Error"
            if "Could not retrieve" in raw_balance_text or "not found" in raw_balance_text or "failed" in raw_balance_text:
                 print("Balance retrieval failed, sending raw text.")
            else:
                 print("Could not extract numeric value from balance text.")

    except ValueError:
        print(f"Could not convert cleaned balance '{cleaned_balance}' to a number.")
    except Exception as e:
        print(f"Error during balance check/conversion: {e}")

    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        response = requests.post(api_url, json={'chat_id': CHAT_ID, 'text': message})
        response.raise_for_status()
        print("Telegram message sent successfully.")
    except Exception as e:
        print(f"Error sending Telegram message: {e}")

def get_desco_balance():
    """Logs into DESCO using account number, scrapes balance, and returns the RAW text."""
    raw_balance_text = "Could not retrieve balance"
    session = requests.Session()
    try:
        print(f"Attempting to login at {LOGIN_URL}...")
        login_data = { ACCOUNT_NO_FIELD_NAME: DESCO_ACCOUNT_NO }
        login_response = session.post(LOGIN_URL, data=login_data, verify=False)
        login_response.raise_for_status()

        # Adjust login success check based on DESCO's site behavior after login
        if "dashboard" in login_response.url or "Account Summary" in login_response.text or login_response.status_code == 200: # Broad checks
            print("Login successful (probably). Parsing balance page...")
            balance_page_content = login_response.content
            # If balance is on a DIFFERENT page you have to navigate to:
            # if login_response.url != BALANCE_PAGE_URL:
            #     print(f"Navigating to {BALANCE_PAGE_URL}...")
            #     balance_page_response = session.get(BALANCE_PAGE_URL)
            #     balance_page_response.raise_for_status()
            #     balance_page_content = balance_page_response.content

            soup = BeautifulSoup(balance_page_content, 'html.parser')
            balance_element = None
            print("Searching for balance element...")

            # --- FIND BALANCE BASED ON PARENT <p> TAG ---
            possible_p_tags = soup.find_all('p') # Find all paragraph tags
            for p_tag in possible_p_tags:
                # Check if this <p> tag contains the specific text 'Remaining Balance:'
                # Using 'in' for flexibility in case of extra spaces
                if 'Remaining Balance:' in p_tag.get_text():
                    print("Found relevant <p> tag containing 'Remaining Balance:'.")
                    # Find the <span> tag *directly inside* this specific <p> tag
                    balance_element = p_tag.find('span')
                    if balance_element:
                        print("Found <span> tag inside the <p> tag.")
                        break # Stop searching once found
                    else:
                        print("Found <p> tag, but no direct <span> inside it.")
            # --- END OF FINDING LOGIC ---

            if balance_element:
                raw_balance_text = balance_element.get_text(strip=True)
                print(f"Raw balance text found: {raw_balance_text}")
            else:
                print("Balance element structure (<p> with 'Remaining Balance:' containing a <span>) not found.")
                raw_balance_text = "Balance element structure not found."
        else:
            print(f"Login failed. Status code: {login_response.status_code}. Final URL: {login_response.url}")
            raw_balance_text = "Login failed."
    except requests.exceptions.RequestException as e:
        print(f"Network or HTTP error during scraping: {e}")
        raw_balance_text = f"Network Error: {e}"
    except Exception as e:
        print(f"An unexpected error occurred during scraping: {e}")
        raw_balance_text = f"Script Error: {e}"
    finally:
        session.close()
    return raw_balance_text

# --- Main Execution ---
if __name__ == "__main__":
    if not all([DESCO_ACCOUNT_NO, BOT_TOKEN, CHAT_ID]):
        print("Error: Missing one or more secrets (DESCO_ACCOUNT_NO, BOT_TOKEN, CHAT_ID). Check GitHub Secrets.")
    else:
        print("Starting DESCO balance check...")
        current_balance_text = get_desco_balance()
        send_telegram_message(current_balance_text)
        print("Script finished.")
