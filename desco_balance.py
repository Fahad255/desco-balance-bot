import requests
import os
from datetime import datetime
import zoneinfo # Requires Python 3.9+
import re # Import the regular expression module

# --- Configuration ---
# Secrets loaded from GitHub Actions environment
DESCO_ACCOUNT_NO = os.environ.get('DESCO_ACCOUNT_NO')
BOT_TOKEN = os.environ.get('BOT_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

YOUR_TIMEZONE = "Asia/Dhaka" # Your local timezone

# --- ACTION NEEDED: Confirm the base API URL if necessary ---
# This is the URL we found in the Network tab, up to the '?'
# It includes '/api/tkdes/customer' which looks correct
API_BASE_URL = "https://prepaid.desco.org.bd/api/tkdes/customer/getBalance"
# We might still need the login page URL just to initialize a session cookie
INITIAL_PAGE_URL = 'https://prepaid.desco.org.bd/customer/#/customer-login' # URL of the page you first visit
# --- End Configuration ---

# --- Functions ---

def send_telegram_message(balance_value):
    """Sends the formatted message, adding a recharge reminder if balance is low."""
    tz = zoneinfo.ZoneInfo(YOUR_TIMEZONE)
    now = datetime.now(tz)
    timestamp = now.strftime('%d-%b-%Y %I:%M %p')

    # Format the balance nicely
    balance_text = f"{balance_value:.2f} BDT" # Show 2 decimal places and currency
    message = f"DESCO Balance Update ({timestamp}):\n\n{balance_text}"
    recharge_reminder = "\n\n⚠️ Low Balance! Please recharge soon."

    try:
        # Check if balance is low (now using the direct numeric value)
        if balance_value < 100:
            message += recharge_reminder
            print("Low balance detected, adding recharge reminder.")

    except Exception as e:
        print(f"Error during balance check/conversion: {e}")
        # If conversion fails, send the raw value as fallback if needed (though it should be a number now)
        message = f"DESCO Balance Update ({timestamp}):\n\nCould not process balance value: {balance_value}"


    # Send the final message via Telegram API
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        response = requests.post(api_url, json={'chat_id': CHAT_ID, 'text': message}, timeout=10)
        response.raise_for_status()
        print("Telegram message sent successfully.")
    except Exception as e:
        print(f"Error sending Telegram message: {e}")

def get_desco_balance_api():
    """Fetches DESCO balance directly via API."""
    balance = None # Use None to indicate failure, will convert to text later
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})

    try:
        # Step 1: Visit the initial page to potentially get necessary cookies/session established
        print(f"Visiting initial page: {INITIAL_PAGE_URL}...")
        session.get(INITIAL_PAGE_URL, verify=False, timeout=15) # We don't care about the response, just need cookies potentially
        print("Initial page visited.")

        # Step 2: Construct the API URL with the account number
        api_url = f"{API_BASE_URL}?accountNo={DESCO_ACCOUNT_NO}&meterNo=" # Added empty meterNo param
        print(f"Fetching balance from API: {api_url}...")

        # Step 3: Make the GET request to the API endpoint using the same session
        api_response = session.get(api_url, verify=False, timeout=15)
        api_response.raise_for_status() # Check for HTTP errors (like 4xx, 5xx)

        # Step 4: Parse the JSON response
        json_data = api_response.json()
        print(f"API Response JSON: {json_data}")

        # Step 5: Extract the balance
        if json_data.get("code") == 200 and "data" in json_data and "balance" in json_data["data"]:
            balance = json_data["data"]["balance"]
            # Ensure balance is a number (float)
            try:
                balance = float(balance)
                print(f"Balance extracted successfully: {balance}")
            except (ValueError, TypeError):
                print(f"API returned balance, but it wasn't a number: {balance}")
                balance = f"API Error: Unexpected balance format ({balance})"

        else:
            # Handle cases where the API call succeeded but didn't return expected data
            print(f"API call successful, but response format unexpected or indicates error.")
            error_desc = json_data.get("desc", "Unknown API response format")
            balance = f"API Error: {error_desc}"


    except requests.exceptions.Timeout:
        print("Error: Request timed out.")
        balance = "Error: Request timed out."
    except requests.exceptions.RequestException as e:
        print(f"Network or HTTP error during API call: {e}")
        balance = f"Network Error: {e}"
    except ValueError: # JSONDecodeError inherits from ValueError
         print("Error: Could not decode JSON response from API.")
         balance = "API Error: Invalid JSON response."
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        balance = f"Script Error: {e}"
    finally:
        session.close()

    # Return the numeric balance or an error string
    return balance

# --- Main Execution ---
if __name__ == "__main__":
    if not all([DESCO_ACCOUNT_NO, BOT_TOKEN, CHAT_ID]):
        print("Error: Missing one or more secrets (DESCO_ACCOUNT_NO, BOT_TOKEN, CHAT_ID). Check GitHub Secrets.")
    else:
        print("Starting DESCO balance check via API...")
        current_balance = get_desco_balance_api()

        # Check if we got a number or an error string
        if isinstance(current_balance, (int, float)):
            send_telegram_message(current_balance) # Pass the number directly
        else:
            # If it's an error string, send it as is
            tz = zoneinfo.ZoneInfo(YOUR_TIMEZONE)
            now = datetime.now(tz)
            timestamp = now.strftime('%d-%b-%Y %I:%M %p')
            error_message = f"DESCO Balance Update ({timestamp}):\n\nFailed to retrieve balance.\nError: {current_balance}"
            # Need to call the Telegram send function directly for errors
            api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            try:
                requests.post(api_url, json={'chat_id': CHAT_ID, 'text': error_message}, timeout=10)
                print("Error message sent to Telegram.")
            except Exception as e_send:
                print(f"Failed to send error message to Telegram: {e_send}")

        print("Script finished.")
