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

### --- ACTION NEEDED: Ensure these are correct based on DESCO Website Inspection --- ###
LOGIN_URL = 'https://prepaid.desco.org.bd/customer/#/customer-login' #<- REPLACE IF NEEDED
BALANCE_PAGE_URL = 'https://prepaid.desco.org.bd/customer/#/customer-info' #<- REPLACE IF NEEDED
ACCOUNT_NO_FIELD_NAME = 'account_no' #<- REPLACE IF NEEDED
BALANCE_ELEMENT_TAG = 'span'     # Should be correct based on screenshot
BALANCE_ELEMENT_ID = None        # Should be correct based on screenshot
BALANCE_ELEMENT_CLASS = None     # Should be correct based on screenshot
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
        response = requests.post(api_url, json={'chat_id': CHAT_ID, 'text': message}, timeout=10) # Added timeout
        response.raise_for_status()
        print("Telegram message sent successfully.")
    except Exception as e:
        print(f"Error sending Telegram message: {e}")

def get_desco_balance():
    """Logs into DESCO using account number (handles potential CSRF), scrapes balance."""
    raw_balance_text = "Could not retrieve balance"
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})

    try:
        print(f"Fetching login page to find tokens: {LOGIN_URL}...")
        # 1. Get the login page first
        get_response = session.get(LOGIN_URL, verify=False, timeout=15)
        get_response.raise_for_status()
        soup_login = BeautifulSoup(get_response.content, 'html.parser')

        # 2. Find potential hidden tokens (common names, adjust if needed)
        login_data = { ACCOUNT_NO_FIELD_NAME: DESCO_ACCOUNT_NO }
        possible_token_names = ['csrf_token', '_token', 'authenticity_token', '__VIEWSTATE', '__EVENTVALIDATION']
        found_token = False
        for token_name in possible_token_names:
            token_element = soup_login.find('input', {'name': token_name})
            if token_element and token_element.get('value'):
                login_data[token_name] = token_element['value']
                print(f"Found hidden token: {token_name}")
                found_token = True
                # break # Uncomment if you're sure there's only one token needed

        if not found_token:
            print("No common CSRF/hidden tokens found on login page. Proceeding without them.")

        # --- Determine the actual POST URL (might be different from LOGIN_URL) ---
        # Inspect the <form> tag on the login page to find the 'action' attribute
        form_tag = soup_login.find('form') # Find the first form, adjust if multiple
        post_url = LOGIN_URL # Default to the page URL
        if form_tag and form_tag.get('action'):
            action_url = form_tag['action']
            # Handle relative URLs if necessary
            if action_url.startswith('/'):
                 # Combine base URL with relative path (needs urlparse)
                 from urllib.parse import urljoin
                 post_url = urljoin(LOGIN_URL, action_url)
            elif action_url: # If it's a full URL or different path
                 post_url = action_url
            print(f"Form action URL found: {post_url}")
        else:
             print("No <form action=...> found, using LOGIN_URL for POST.")
        # --- End of POST URL determination ---


        print(f"Attempting to POST login data to {post_url}...")
        # 3. Perform login POST request with account number and any found tokens
        login_response = session.post(post_url, data=login_data, verify=False, timeout=15)
        login_response.raise_for_status()

        # 4. Check if login was successful (adjust checks as needed)
        # Look for indicators like redirection URL, specific text ("Welcome", "Logout"), lack of "Login" button
        logged_in_url = login_response.url.strip('/')
        expected_dashboard_url = BALANCE_PAGE_URL.strip('/')
        if logged_in_url == expected_dashboard_url or "Logout" in login_response.text or "Account Summary" in login_response.text:
            print("Login successful (probably). Parsing balance page...")
            balance_page_content = login_response.content

            # If balance is definitely on a DIFFERENT page, uncomment and modify GET request
            # if logged_in_url != expected_dashboard_url:
            #     print(f"Navigating to expected balance page {BALANCE_PAGE_URL}...")
            #     balance_page_response = session.get(BALANCE_PAGE_URL, verify=False, timeout=15)
            #     balance_page_response.raise_for_status()
            #     balance_page_content = balance_page_response.content

            soup_balance = BeautifulSoup(balance_page_content, 'html.parser')
            balance_element = None
            print("Searching for balance element...")
            # Find balance using the parent <p> tag method
            possible_p_tags = soup_balance.find_all('p')
            for p_tag in possible_p_tags:
                if 'Remaining Balance:' in p_tag.get_text():
                    print("Found relevant <p> tag.")
                    balance_element = p_tag.find('span')
                    if balance_element:
                        print("Found <span> tag inside.")
                        break
                    else:
                        print("No <span> inside relevant <p>.")
            # --- End balance finding ---

            if balance_element:
                raw_balance_text = balance_element.get_text(strip=True)
                print(f"Raw balance text found: {raw_balance_text}")
            else:
                print("Balance element structure not found on dashboard page.")
                print("--- DASHBOARD HTML START (DEBUG) ---")
                print(soup_balance.prettify()[:2000]) # Print first 2000 chars of dashboard HTML
                print("--- DASHBOARD HTML END (DEBUG) ---")
                raw_balance_text = "Balance element structure not found."
        else:
            # Login failed - print details
            print(f"Login failed. Status code: {login_response.status_code}. Final URL: {login_response.url}")
            print("--- LOGIN FAILED - PAGE CONTENT START ---")
            print(login_response.text[:1000]) # Print first 1000 chars of response
            print("--- LOGIN FAILED - PAGE CONTENT END ---")
            raw_balance_text = "Login failed. Check credentials, tokens, or website changes."

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
