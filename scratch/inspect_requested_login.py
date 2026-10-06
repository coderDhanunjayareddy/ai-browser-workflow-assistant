import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--disable-quic'])
    page = browser.new_page()
    page.goto('https://www.spectropy.com/', wait_until='domcontentloaded')
    page.get_by_role('button', name='Login', exact=True).click()
    page.get_by_role('button', name=re.compile('Spectropy OS', re.I)).click()
    target = page
    target.wait_for_load_state('domcontentloaded')
    target.locator('input').first.wait_for()
    print(json.dumps({'url': target.url, 'text': target.locator('body').inner_text(),
                      'inputs': target.locator('input').evaluate_all('(els) => els.map(e => ({type:e.type, placeholder:e.placeholder, id:e.id, name:e.name}))')}, indent=2))
    browser.close()
