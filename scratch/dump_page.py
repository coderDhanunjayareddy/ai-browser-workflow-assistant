import sys
from playwright.sync_api import sync_playwright

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        try:
            print(text.encode('ascii', errors='replace').decode('ascii'))
        except Exception:
            pass

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir="c:/Work/AI_Browser_Assist/chrome-profile",
            headless=False,
            viewport={"width": 1280, "height": 800}
        )
        page = browser.pages[0] if browser.pages else browser.new_page()

        # Flipkart
        page.goto("https://www.flipkart.com/search?q=wireless%20headphones%20under%202000")
        page.wait_for_timeout(5000)
        
        cards = page.query_selector_all("div[data-id]")
        safe_print(f"Flipkart: Found {len(cards)} div[data-id] elements.")
        if cards:
            safe_print("First card inner text:")
            safe_print(cards[0].inner_text())
            safe_print("First card inner HTML:")
            html = page.evaluate("el => el.innerHTML", cards[0])
            safe_print(html[:2000])

        # Amazon
        page.goto("https://www.amazon.in/s?k=wireless+headphones+under+2000")
        page.wait_for_timeout(5000)
        
        cards = page.query_selector_all("div[data-component-type='s-search-result']")
        safe_print(f"\nAmazon: Found {len(cards)} search result elements.")
        if cards:
            safe_print("First card inner text:")
            safe_print(cards[0].inner_text())
            safe_print("First card inner HTML:")
            html = page.evaluate("el => el.innerHTML", cards[0])
            safe_print(html[:2000])
            
        browser.close()

if __name__ == "__main__":
    main()
