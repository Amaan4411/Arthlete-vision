const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
require('dotenv').config();
const fs = require('fs');

puppeteer.use(StealthPlugin());

const EMAIL = process.env.LINKEDIN_EMAIL;
const PASSWORD = process.env.LINKEDIN_PASSWORD;
const POST_TEXT = process.env.POST_TEXT || 'Automated post from Puppeteer Stealth!';

async function run() {
  if (!EMAIL || !PASSWORD) {
    console.error('Missing LINKEDIN_EMAIL or LINKEDIN_PASSWORD in environment.');
    process.exit(1);
  }
  const browser = await puppeteer.launch({ headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage();
  try {
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
    await page.waitForSelector('button[aria-label="Start a post"]', { visible: true, timeout: 30000 });
    await page.click('button[aria-label="Start a post"]');
    await page.waitForSelector('div[role="textbox"]', { visible: true, timeout: 30000 });
    await page.type('div[role="textbox"]', POST_TEXT, { delay: 80 });
    await page.waitForTimeout(1000);
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
  }
}

run(); 