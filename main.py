import os
import smtplib
import json
from email.mime.text import MIMEText
from google.oauth2 import service_account
from googleapiclient.discovery import build
from linkedin_api import Linkedin

# --- CONFIGURATION (loaded securely from GitHub Secrets) ---
SHEET_ID = os.environ.get('SHEET_ID')
RANGE_NAME = 'Sheet1!A1:Z1000'  # You can make this a secret too if you want
EMAIL_FROM = os.environ.get('EMAIL_FROM')
EMAIL_TO = os.environ.get('EMAIL_TO')
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD')
GOOGLE_CREDENTIALS_JSON_STR = os.environ.get('GOOGLE_CREDENTIALS_JSON')
LINKEDIN_LI_AT = os.environ.get('LINKEDIN_LI_AT') # The 'li_at' cookie for authentication

# --- SETUP FUNCTIONS ---

def get_google_creds(scopes):
    """Loads Google credentials from the environment variable for the given scopes."""
    if not GOOGLE_CREDENTIALS_JSON_STR:
        raise ValueError("Google credentials JSON not found in environment variables.")
    return service_account.Credentials.from_service_account_info(
        json.loads(GOOGLE_CREDENTIALS_JSON_STR),
        scopes=scopes
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

def post_to_linkedin_and_update_sheet(post_content, sheet_creds):
    """
    Posts content to LinkedIn and clears the row in the Google Sheet upon success.
    """
    try:
        print("Authenticating with LinkedIn...")
        linkedin = Linkedin(EMAIL_FROM, GMAIL_APP_PASSWORD, cookies=LINKEDIN_LI_AT) # Using Gmail creds just as placeholders, cookie is the real auth
        
        print("Posting to LinkedIn...")
        linkedin.create_post(post_content)
        print("Successfully posted to LinkedIn.")

        print("Clearing the row from Google Sheet...")
        service = build('sheets', 'v4', credentials=sheet_creds)
        body = {} # An empty body clears the values
        service.spreadsheets().values().clear(
            spreadsheetId=SHEET_ID,
            range='Sheet1!A1:Z1' # Assumes the post is always in the first row
        ).execute()
        print("Successfully cleared the row from the sheet.")

    except Exception as e:
        print(f"An error occurred during the LinkedIn post or sheet update: {e}")

# --- MAIN WORKFLOW ---

def main():
    """
    Main function executed by GitHub Actions.
    - Checks for all required secrets.
    - Fetches data from Google Sheets.
    - If the sheet is empty, sends an email notification.
    - If it has data, proceeds with the posting logic.
    """
    required_secrets = ['SHEET_ID', 'EMAIL_FROM', 'EMAIL_TO', 'GMAIL_APP_PASSWORD', 'GOOGLE_CREDENTIALS_JSON', 'LINKEDIN_LI_AT']
    if any(not os.environ.get(secret) for secret in required_secrets):
        print("Error: One or more required secrets are not set in the GitHub repository.")
        print("Please ensure SHEET_ID, EMAIL_FROM, EMAIL_TO, GMAIL_APP_PASSWORD, GOOGLE_CREDENTIALS_JSON, and LINKEDIN_LI_AT are set.")
        return

    print("Fetching data from Google Sheet...")
    # Read-only scope for the initial check
    readonly_creds = get_google_creds(scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
    data = get_sheet_data(readonly_creds)

    # Check if the sheet is effectively empty
    if not data or all(not any(cell for cell in row) for row in data):
        print("Sheet is empty. Sending notification...")
        send_email_notification()
    else:
        print("Sheet contains data. Proceeding to post.")
        # The content to post is assumed to be in the first cell of the first row
        content_to_post = data[0][0] 
        
        # We need credentials with write access to clear the row
        write_creds = get_google_creds(scopes=['https://www.googleapis.com/auth/spreadsheets'])
        post_to_linkedin_and_update_sheet(content_to_post, write_creds)

if __name__ == '__main__':
    main() 