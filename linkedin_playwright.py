import os
import sys
import json
import tempfile
import requests
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
SHEET_ID = os.environ.get('SHEET_ID')
RANGE_NAME = 'Sheet1!A1:Z1000'
LINKEDIN_EMAIL = os.environ.get('LINKEDIN_EMAIL')
LINKEDIN_PASSWORD = os.environ.get('LINKEDIN_PASSWORD')
POST_SLOT = os.environ.get('POST_SLOT')  # For testing: 'morning', 'afternoon', 'evening'
IMAGES_DIR = os.path.join(os.path.dirname(__file__), 'images')
GOOGLE_CREDENTIALS_JSON_STR = os.environ.get('GOOGLE_CREDENTIALS_JSON')

COLUMN_MAP = {
    'morning': ('Morning (1 PM)', 'Morning Image'),
    'afternoon': ('Afternoon (5 PM)', 'Afternoon Image'),
    'evening': ('Evening (8 PM)', 'Evening Image')
}

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
        return 'morning'  # Default for testing

def get_image_path(image_cell):
    if not image_cell:
        return None
    image_cell = image_cell.strip()
    # If it's a URL, download it to a temp file
    if image_cell.startswith('http://') or image_cell.startswith('https://'):
        try:
            response = requests.get(image_cell, timeout=10)
            response.raise_for_status()
            suffix = os.path.splitext(image_cell)[-1] or '.jpg'
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(response.content)
                print(f"Downloaded image from URL to {tmp.name}")
                return tmp.name
        except Exception as e:
            print(f"Failed to download image from URL: {e}")
            return None
    # Otherwise, treat as local filename
    local_path = os.path.join(IMAGES_DIR, image_cell)
    if os.path.exists(local_path):
        return local_path
    print(f"Image file '{local_path}' not found. Posting text only.")
    return None

def post_to_linkedin(text, image_path=None):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.linkedin.com/login")
        page.fill('input[name="session_key"]', LINKEDIN_EMAIL)
        page.fill('input[name="session_password"]', LINKEDIN_PASSWORD)
        page.click('button[type="submit"]')
        page.wait_for_url("https://www.linkedin.com/feed/")
        page.click('button[aria-label="Start a post"]')
        page.fill('div[role="textbox"]', text)
        if image_path and os.path.exists(image_path):
            page.click('button[aria-label="Add a photo"]')
            page.set_input_files('input[type="file"]', image_path)
        page.click('button[data-control-name="share.post"]')
        print("Posted to LinkedIn!")
        browser.close()
        # Clean up temp file if it was a download
        if image_path and image_path.startswith(tempfile.gettempdir()):
            try:
                os.remove(image_path)
            except Exception:
                pass

def main():
    print("Fetching data from Google Sheet...")
    creds = get_google_creds(scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
    data = get_sheet_data(creds)
    if not data or len(data) < 2:
        print("Sheet is empty or missing data rows.")
        sys.exit(1)
    headers = data[0]
    today_str = datetime.now().strftime('%Y-%m-%d')
    today_row = None
    for row in data[1:]:
        if len(row) > 0 and row[0] == today_str:
            today_row = row
            break
    if not today_row:
        print(f"No row found for today's date ({today_str}). Nothing to post.")
        sys.exit(0)
    slot = get_time_slot()
    print(f"Selected time slot: {slot}")
    text_col, img_col = COLUMN_MAP[slot]
    if text_col not in headers:
        print(f"Column '{text_col}' not found in headers. Check your sheet structure.")
        sys.exit(1)
    text_idx = headers.index(text_col)
    img_idx = headers.index(img_col) if img_col in headers else None
    post_text = today_row[text_idx] if len(today_row) > text_idx else ''
    image_path = None
    if img_idx is not None and len(today_row) > img_idx and today_row[img_idx].strip():
        image_path = get_image_path(today_row[img_idx].strip())
    print(f"Posting text: {post_text}")
    if image_path:
        print(f"With image: {image_path}")
    post_to_linkedin(post_text, image_path)

if __name__ == '__main__':
    main() 