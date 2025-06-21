import os
import smtplib
import json
from email.mime.text import MIMEText
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- CONFIGURATION (loaded securely from GitHub Secrets) ---
SHEET_ID = os.environ.get('SHEET_ID')
RANGE_NAME = 'Sheet1!A1:Z1000'  # You can make this a secret too if you want
EMAIL_FROM = os.environ.get('EMAIL_FROM')
EMAIL_TO = os.environ.get('EMAIL_TO')
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD')
GOOGLE_CREDENTIALS_JSON_STR = os.environ.get('GOOGLE_CREDENTIALS_JSON')

# --- SETUP FUNCTIONS ---

def get_google_creds():
    """Loads Google credentials from the environment variable."""
    if not GOOGLE_CREDENTIALS_JSON_STR:
        raise ValueError("Google credentials JSON not found in environment variables.")
    return service_account.Credentials.from_service_account_info(
        json.loads(GOOGLE_CREDENTIALS_JSON_STR),
        scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
    )

def get_sheet_data(creds):
    """Connects to Google Sheets API and fetches data."""
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SHEET_ID, range=RANGE_NAME).execute()
    return result.get('values', [])

def send_email_notification():
    """Sends an email using Gmail SMTP if the sheet is empty."""
    msg = MIMEText('Your Google Sheet is empty. Please add new content to continue automated posting.')
    msg['Subject'] = 'Action Required: Your Content Sheet is Empty'
    msg['From'] = EMAIL_FROM
    msg['To'] = EMAIL_TO

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_FROM, GMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print("Email notification sent successfully.")
    except Exception as e:
        print(f"Failed to send email: {e}")

# --- MAIN WORKFLOW ---

def main():
    """
    Main function executed by GitHub Actions.
    - Checks for all required secrets.
    - Fetches data from Google Sheets.
    - If the sheet is empty, sends an email notification.
    - If it has data, proceeds with the posting logic.
    """
    required_secrets = ['SHEET_ID', 'EMAIL_FROM', 'EMAIL_TO', 'GMAIL_APP_PASSWORD', 'GOOGLE_CREDENTIALS_JSON']
    if any(not os.environ.get(secret) for secret in required_secrets):
        print("Error: One or more required secrets are not set in the GitHub repository.")
        return

    print("Fetching data from Google Sheet...")
    creds = get_google_creds()
    data = get_sheet_data(creds)

    # Check if the sheet is effectively empty
    if not data or all(not any(cell for cell in row) for row in data):
        print("Sheet is empty. Sending notification...")
        send_email_notification()
    else:
        print("Sheet contains data. Ready to post.")
        #
        # <<< YOUR AUTOMATED POSTING LOGIC GOES HERE >>>
        #
        # Example:
        # post_content = data[0][0] # Get content from the first cell
        # post_to_linkedin(post_content)
        # update_sheet_to_mark_as_posted(row_index=0)
        #
        print("Posting logic is not yet implemented.")

if __name__ == '__main__':
    main() 