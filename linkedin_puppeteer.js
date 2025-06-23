const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const { google } = require('googleapis');
const fetch = require('node-fetch');
const fs = require('fs');
const os = require('os');
const path = require('path');
require('dotenv').config();

puppeteer.use(StealthPlugin());

const EMAIL = process.env.LINKEDIN_EMAIL;
const PASSWORD = process.env.LINKEDIN_PASSWORD;
const SHEET_ID = process.env.SHEET_ID;
const SHEET_NAME = process.env.SHEET_NAME || 'Sheet1';
const RANGE_NAME = `${SHEET_NAME}!A1:Z1000`;
const GOOGLE_CREDENTIALS_JSON = process.env.GOOGLE_CREDENTIALS_JSON;
const POST_SLOT = process.env.POST_SLOT;
const IMAGES_DIR = path.join(__dirname, 'images');
const COOKIES_PATH = path.join(__dirname, 'linkedin_cookies.json');

const COLUMN_MAP = {
  morning: ['Morning (1 PM)', 'Morning Image'],
  afternoon: ['Afternoon (5 PM)', 'Afternoon Image'],
  evening: ['Evening (8 PM)', 'Evening Image'],
};

function getTimeSlot() {
  if (POST_SLOT) return POST_SLOT.toLowerCase();
  const now = new Date();
  const hour = now.getHours();
  if (hour === 13) return 'morning';
  if (hour === 17) return 'afternoon';
  if (hour === 20) return 'evening';
  return 'morning'; // default for testing
}

async function getSheetData() {
  if (!GOOGLE_CREDENTIALS_JSON) throw new Error('Missing GOOGLE_CREDENTIALS_JSON');
  const creds = JSON.parse(GOOGLE_CREDENTIALS_JSON);
  const scopes = ['https://www.googleapis.com/auth/spreadsheets.readonly'];
  const auth = new google.auth.GoogleAuth({
    credentials: creds,
    scopes,
  });
  const sheets = google.sheets({ version: 'v4', auth });
  const res = await sheets.spreadsheets.values.get({
    spreadsheetId: SHEET_ID,
    range: RANGE_NAME,
  });
  return res.data.values;
}

async function getImagePath(imageCell) {
  if (!imageCell) return null;
  imageCell = imageCell.trim();
  if (imageCell.startsWith('http://') || imageCell.startsWith('https://')) {
    // Download image to temp file
    try {
      const resp = await fetch(imageCell);
      if (!resp.ok) throw new Error('Failed to download image');
      const ext = path.extname(imageCell) || '.jpg';
      const tmpPath = path.join(os.tmpdir(), `linkedin_img_${Date.now()}${ext}`);
      const fileStream = fs.createWriteStream(tmpPath);
      await new Promise((resolve, reject) => {
        resp.body.pipe(fileStream);
        resp.body.on('error', reject);
        fileStream.on('finish', resolve);
      });
      return tmpPath;
    } catch (e) {
      console.error('Failed to download image:', e);
      return null;
    }
  }
  // Local file
  const localPath = path.join(IMAGES_DIR, imageCell);
  if (fs.existsSync(localPath)) return localPath;
  console.warn(`Image file '${localPath}' not found in images/. Posting text only.`);
  return null;
}

async function getPostFromSheet() {
  const data = await getSheetData();
  if (!data || data.length < 2) throw new Error('Sheet is empty or missing data rows.');
  const headers = data[0];
  const todayStr = new Date().toISOString().slice(0, 10);
  let todayRow = null;
  for (const row of data.slice(1)) {
    if (row[0] === todayStr) {
      todayRow = row;
      break;
    }
  }
  if (!todayRow) throw new Error(`No row found for today's date (${todayStr}). Nothing to post.`);
  const slot = getTimeSlot();
  const [textCol, imgCol] = COLUMN_MAP[slot];
  const textIdx = headers.indexOf(textCol);
  const imgIdx = headers.indexOf(imgCol);
  const postText = textIdx !== -1 && todayRow.length > textIdx ? todayRow[textIdx] : '';
  let imagePath = null;
  if (imgIdx !== -1 && todayRow.length > imgIdx && todayRow[imgIdx].trim()) {
    imagePath = await getImagePath(todayRow[imgIdx].trim());
  }
  return { postText, imagePath };
}

async function useCookiesIfAvailable(page) {
  if (fs.existsSync(COOKIES_PATH)) {
    try {
      const cookies = JSON.parse(fs.readFileSync(COOKIES_PATH, 'utf8'));
      await page.setCookie(...cookies);
      console.log('Loaded cookies from linkedin_cookies.json');
      await page.goto('https://www.linkedin.com/feed', { waitUntil: 'networkidle2', timeout: 60000 });
      // Check if logged in by looking for the feed
      if ((await page.url()).includes('/feed')) {
        console.log('Logged in with cookies!');
        return true;
      } else {
        console.error('Cookies did not work. Your LinkedIn cookies are expired or invalid. Please refresh your cookies and try again.');
        process.exit(1);
      }
    } catch (e) {
      console.error('Failed to use cookies:', e);
      console.error('Your LinkedIn cookies are expired or invalid. Please refresh your cookies and try again.');
      process.exit(1);
    }
  }
  return false;
}

async function run() {
  if (!EMAIL || !PASSWORD) {
    console.error('Missing LINKEDIN_EMAIL or LINKEDIN_PASSWORD in environment.');
    process.exit(1);
  }
  let postText, imagePath;
  try {
    ({ postText, imagePath } = await getPostFromSheet());
    console.log('Posting text:', postText);
    if (imagePath) console.log('With image:', imagePath);
    else console.log('No image for this post.');
  } catch (err) {
    console.error('Error fetching post from Google Sheets:', err);
    process.exit(1);
  }
  const browser = await puppeteer.launch({ headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage();
  try {
    // Try cookie-based login first
    const cookiesWorked = await useCookiesIfAvailable(page);
    if (!cookiesWorked) {
      // Only try email/password login if cookies file does not exist
      if (!fs.existsSync(COOKIES_PATH)) {
        console.log('No linkedin_cookies.json found. Proceeding with email/password login...');
        // Fallback: normal login
        console.log('Navigating to LinkedIn login...');
        await page.goto('https://www.linkedin.com/login', { waitUntil: 'domcontentloaded', timeout: 60000 });
        await page.waitForSelector('input[name="session_key"]', { visible: true, timeout: 30000 });
        await page.type('input[name="session_key"]', EMAIL, { delay: 120 });
        await page.type('input[name="session_password"]', PASSWORD, { delay: 120 });
        await page.waitForTimeout(800);
        await page.click('button[type="submit"]');
        console.log('Waiting for login to complete...');
        await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 60000 });
        const url = page.url();
        if (url.includes('checkpoint') || url.includes('captcha') || url.includes('challenge')) {
          console.error('LinkedIn triggered a security checkpoint or CAPTCHA.');
          await page.screenshot({ path: 'error_screenshot.png' });
          process.exit(1);
        }
        if (!url.includes('/feed')) {
          console.error('Login failed, not redirected to feed.');
          await page.screenshot({ path: 'error_screenshot.png' });
          process.exit(1);
        }
        console.log('Login successful! Navigating to post...');
      } else {
        // Should never reach here, but just in case
        process.exit(1);
      }
    }
    await page.waitForSelector('button[aria-label="Start a post"]', { visible: true, timeout: 30000 });
    await page.click('button[aria-label="Start a post"]');
    await page.waitForSelector('div[role="textbox"]', { visible: true, timeout: 30000 });
    await page.type('div[role="textbox"]', postText, { delay: 80 });
    await page.waitForTimeout(1000);
    if (imagePath) {
      const photoBtn = await page.$('button[aria-label="Add a photo"]');
      if (photoBtn) {
        await photoBtn.click();
        await page.waitForSelector('input[type="file"]', { visible: true, timeout: 30000 });
        const inputFile = await page.$('input[type="file"]');
        await inputFile.uploadFile(imagePath);
        console.log('Image uploaded, waiting for preview...');
        await page.waitForTimeout(4000);
        // Click 'Done' if it appears
        const doneBtn = await page.$('button[aria-label="Done"]');
        if (doneBtn) await doneBtn.click();
        await page.waitForTimeout(1000);
      } else {
        console.warn('Could not find Add a photo button. Posting text only.');
      }
    }
    const postBtn = await page.$('button[data-control-name="share.post"]');
    if (!postBtn) {
      console.error('Could not find post button.');
      await page.screenshot({ path: 'error_screenshot.png' });
      process.exit(1);
    }
    await postBtn.click();
    console.log('Post submitted! Waiting for confirmation...');
    await page.waitForTimeout(8000);
    console.log('Post should be live on your feed!');
  } catch (err) {
    console.error('Error during automation:', err);
    await page.screenshot({ path: 'error_screenshot.png' });
    process.exit(1);
  } finally {
    await browser.close();
    if (imagePath && imagePath.startsWith(os.tmpdir())) {
      try { fs.unlinkSync(imagePath); } catch (e) {}
    }
  }
}

run(); 