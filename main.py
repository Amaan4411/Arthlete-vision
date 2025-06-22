import os
import smtplib
import json
import sys
from datetime import datetime
from email.mime.text import MIMEText
from google.oauth2 import service_account
from googleapiclient.discovery import build

try:
    from linkedin_api import Linkedin
except ImportError:
    Linkedin = None

# --- CONFIGURATION (loaded securely from GitHub Secrets) ---
SHEET_ID = os.environ.get('SHEET_ID')
RANGE_NAME = 'Sheet1!A1:Z1000'
EMAIL_FROM = os.environ.get('EMAIL_FROM')
EMAIL_TO = os.environ.get('EMAIL_TO')
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD')
GOOGLE_CREDENTIALS_JSON_STR = os.environ.get('GOOGLE_CREDENTIALS_JSON')
LINKEDIN_LI_AT = os.environ.get('LINKEDIN_LI_AT')
LINKEDIN_JSESSIONID = os.environ.get('LINKEDIN_JSESSIONID')
POST_SLOT = os.environ.get('POST_SLOT')  # For testing: 'morning', 'afternoon', 'evening'

# --- COLUMN MAPPING ---
COLUMN_MAP = {
    'morning': 'Morning (1 PM)',
    'afternoon': 'Afternoon (5 PM)',
    'evening': 'Evening (8 PM)'
}

# --- SETUP FUNCTIONS ---
def get_google_creds(scopes):
    if not GOOGLE_CREDENTIALS_JSON_STR:
        raise ValueError("Google credentials JSON not found in environment variables.")
    return service_account.Credentials.from_service_account_info(
        json.loads(GOOGLE_CREDENTIALS_JSON_STR),
        scopes=scopes
    )

def get_sheet_data(creds):
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SHEET_ID, range=RANGE_NAME).execute()
    return result.get('values', [])

def send_email_notification():
    if not EMAIL_FROM or not EMAIL_TO or not GMAIL_APP_PASSWORD:
        print("Missing email configuration. Cannot send notification.")
        return
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

def get_time_slot():
    if POST_SLOT:
        return POST_SLOT.lower()
    now = datetime.now().time()
    if now.hour == 13:
        return 'morning'
    elif now.hour == 17:
        return 'afternoon'
    elif now.hour == 20:
        return 'evening'
    else:
        # For testing, default to morning if not at a scheduled time
        return 'morning'

def post_to_linkedin_and_update_sheet(post_content, sheet_creds):
    if not LINKEDIN_LI_AT or not LINKEDIN_JSESSIONID:
        print("Missing LinkedIn cookies. Cannot post to LinkedIn.")
        return
    if Linkedin is None:
        print("linkedin-api package is not installed.")
        return
    try:
        print("Authenticating with LinkedIn...")
        cookies = {"li_at": LINKEDIN_LI_AT, "JSESSIONID": LINKEDIN_JSESSIONID}
        linkedin = Linkedin("", "", cookies=cookies)
        print("Attempting to post to LinkedIn...")
        if not hasattr(linkedin, "create_post"):
            print("ERROR: The 'linkedin-api' library does NOT support posting anymore. Please use another method or library for posting to LinkedIn.")
            return
        linkedin.create_post(post_content)
        print("Successfully posted to LinkedIn.")
        # Not clearing the row for now, so you can test multiple times
    except Exception as e:
        print(f"An error occurred during the LinkedIn post: {e}")

def main():
    print("--- Checking for all required secrets ---")
    required_secrets = [
        'SHEET_ID', 'EMAIL_FROM', 'EMAIL_TO', 'GMAIL_APP_PASSWORD',
        'GOOGLE_CREDENTIALS_JSON', 'LINKEDIN_LI_AT', 'LINKEDIN_JSESSIONID'
    ]
    all_secrets_found = True
    for secret in required_secrets:
        if os.environ.get(secret):
            print(f"✅ Found secret: {secret}")
        else:
            print(f"❌ MISSING secret: {secret}")
            all_secrets_found = False
    if not all_secrets_found:
        print("\nError: One or more required secrets are not set in the GitHub repository.")
        sys.exit(1)
    print("\n--- All secrets found. Proceeding with workflow. ---\n")
    print("Fetching data from Google Sheet...")
    readonly_creds = get_google_creds(scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
    data = get_sheet_data(readonly_creds)
    if not data or len(data) < 2:
        print("Sheet is empty or missing data rows. Sending notification...")
        send_email_notification()
        return
    headers = data[0]
    today_str = datetime.now().strftime('%Y-%m-%d')
    # Find the row for today
    today_row = None
    for row in data[1:]:
        if len(row) > 0 and row[0] == today_str:
            today_row = row
            break
    if not today_row:
        print(f"No row found for today's date ({today_str}). Nothing to post.")
        return
    slot = get_time_slot()
    print(f"Selected time slot: {slot}")
    if COLUMN_MAP[slot] not in headers:
        print(f"Column '{COLUMN_MAP[slot]}' not found in headers. Check your sheet structure.")
        return
    col_idx = headers.index(COLUMN_MAP[slot])
    if len(today_row) <= col_idx or not today_row[col_idx].strip():
        print(f"No content to post for {slot} slot today.")
        return
    content_to_post = today_row[col_idx]
    print(f"Posting content: {content_to_post}")
    write_creds = get_google_creds(scopes=['https://www.googleapis.com/auth/spreadsheets'])
    post_to_linkedin_and_update_sheet(content_to_post, write_creds)

if __name__ == '__main__':
    main() 