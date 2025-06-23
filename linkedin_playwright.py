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
SHEET_NAME = os.environ.get('SHEET_NAME', 'Sheet1')  # Allow sheet name override
RANGE_NAME = f'{SHEET_NAME}!A1:Z1000'
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
    print(f"Fetching data from Google Sheet: {SHEET_ID}, Range: {RANGE_NAME}")
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SHEET_ID, range=RANGE_NAME).execute()
    return result.get('values', [])

def get_time_slot():
    if POST_SLOT:
        print(f"POST_SLOT override detected: {POST_SLOT}")
        return POST_SLOT.lower()
    now = datetime.now().time()
    if now.hour == 13:
        return 'morning'
    elif now.hour == 17:
        return 'afternoon'
    elif now.hour == 20:
        return 'evening'
    else:
        print("Not a scheduled slot hour, defaulting to 'morning' for testing.")
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
        print(f"Found local image: {local_path}")
        return local_path
    print(f"Image file '{local_path}' not found in images/. Posting text only.")
    return None

def post_to_linkedin(text, image_path=None):
    if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
        print("ERROR: LINKEDIN_EMAIL and LINKEDIN_PASSWORD must be set in environment variables.")
        sys.exit(1)
    with sync_playwright() as p:
        try:
            # Use Firefox instead of Chrome as it's less likely to trigger security checks
            browser = p.firefox.launch(
                headless=True,
                args=[
                    '--width=1920',
                    '--height=1080'
                ]
            )
            
            # Set up a persistent context to maintain cookies
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
                locale='en-US',
                timezone_id='America/New_York',
                geolocation={'latitude': 40.7128, 'longitude': -74.0060},
                permissions=['geolocation'],
                accept_downloads=True
            )
            
            # Enable more verbose logging
            context.set_default_timeout(120000)
            context.set_default_navigation_timeout(120000)
            
            page = context.new_page()
            print("Navigating to LinkedIn homepage first...")
            
            # Start with the homepage, then go to login
            page.goto("https://www.linkedin.com", wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=30000)
            
            print("Going to login page...")
            page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=30000)
            
            # Login with explicit waits and null checks
            print("Filling login credentials...")
            email_input = page.wait_for_selector('input[name="session_key"]', state="visible", timeout=30000)
            if not email_input:
                raise Exception("Could not find email input field")
            
            password_input = page.wait_for_selector('input[name="session_password"]', state="visible", timeout=30000)
            if not password_input:
                raise Exception("Could not find password input field")
            
            # Type slowly like a human
            print("Entering email...")
            email_input.type(LINKEDIN_EMAIL, delay=100)
            page.wait_for_timeout(1000)
            
            print("Entering password...")
            password_input.type(LINKEDIN_PASSWORD, delay=100)
            page.wait_for_timeout(1000)
            
            print("Clicking sign in...")
            submit_button = page.wait_for_selector('button[type="submit"]', state="visible", timeout=30000)
            if not submit_button:
                raise Exception("Could not find submit button")
            submit_button.click()
            
            # Wait for navigation with explicit success criteria
            print("Waiting for successful login...")
            try:
                page.wait_for_url("https://www.linkedin.com/feed/", timeout=60000)
            except Exception as e:
                current_url = page.url
                print(f"Navigation failed. Current URL: {current_url}")
                if "checkpoint" in current_url or "challenge" in current_url:
                    raise Exception("LinkedIn security check detected. Please try logging in manually first.")
                raise e
            
            page.wait_for_load_state("networkidle", timeout=30000)
            print("Successfully logged in!")
            
            # Small delay before starting the post
            page.wait_for_timeout(3000)
            
            print("Looking for post button...")
            start_post_button = page.wait_for_selector('button[aria-label="Start a post"]', state="visible", timeout=30000)
            if not start_post_button:
                raise Exception("Could not find 'Start a post' button")
            start_post_button.click()
            
            print("Waiting for post dialog...")
            textbox = page.wait_for_selector('div[role="textbox"]', state="visible", timeout=30000)
            if not textbox:
                raise Exception("Could not find post text box")
            
            # Type the text slowly like a human
            print("Typing post content...")
            textbox.type(text, delay=50)
            
            if image_path and os.path.exists(image_path):
                print(f"Attaching image: {image_path}")
                photo_button = page.wait_for_selector('button[aria-label="Add a photo"]', state="visible", timeout=30000)
                if not photo_button:
                    raise Exception("Could not find 'Add a photo' button")
                photo_button.click()
                
                input_file = page.wait_for_selector('input[type="file"]', state="visible", timeout=30000)
                if not input_file:
                    raise Exception("Could not find file input element")
                input_file.set_input_files(image_path)
                
                # Wait for image upload with progress indicator
                print("Waiting for image upload...")
                upload_complete = page.wait_for_selector('img[alt="Post image"]', state="visible", timeout=60000)
                if not upload_complete:
                    raise Exception("Image upload failed - could not verify image presence")
            else:
                print("No image to attach")
            
            # Wait before posting
            page.wait_for_timeout(2000)
            
            # Look for the post button and click
            print("Looking for post button...")
            post_button = page.wait_for_selector('button[data-control-name="share.post"]', state="visible", timeout=30000)
            if not post_button:
                raise Exception("Could not find post button")
            
            print("Clicking post button...")
            post_button.click()
            
            # Wait for post confirmation
            print("Waiting for post to complete...")
            page.wait_for_timeout(10000)
            print("Posted successfully to LinkedIn!")
            
        except Exception as e:
            print(f"ERROR during LinkedIn automation: {str(e)}")
            if 'page' in locals():
                print("Current URL:", page.url)
                try:
                    print("Saving error screenshot...")
                    page.screenshot(path="error_screenshot.png")
                    print("Error screenshot saved as error_screenshot.png")
                except Exception as screenshot_error:
                    print(f"Failed to save screenshot: {screenshot_error}")
            raise e
        finally:
            if 'browser' in locals():
                browser.close()
            # Clean up temp file if it was a download
            if image_path and image_path.startswith(tempfile.gettempdir()):
                try:
                    os.remove(image_path)
                except Exception:
                    pass

def main():
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
    else:
        print("No image for this post.")
    post_to_linkedin(post_text, image_path)

if __name__ == '__main__':
    main() 