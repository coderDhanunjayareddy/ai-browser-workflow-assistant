import os
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
    screenshots_dir = "c:/Work/AI_Browser_Assist/screenshots"
    os.makedirs(screenshots_dir, exist_ok=True)
    
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir="c:/Work/AI_Browser_Assist/chrome-profile",
            headless=False,
            viewport={"width": 1280, "height": 800}
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        
        # Check Flipkart Cart
        safe_print("Checking Flipkart Cart...")
        page.goto("https://www.flipkart.com/viewcart")
        page.wait_for_timeout(5000)
        
        fk_text = page.inner_text("body")
        safe_print("--- Flipkart Cart Content Snippet ---")
        lines = [line.strip() for line in fk_text.split("\n") if line.strip()][:15]
        for line in lines:
            safe_print(line)
            
        screenshot_fk = os.path.join(screenshots_dir, "fk_cart_status.png")
        page.screenshot(path=screenshot_fk)
        safe_print(f"Saved Flipkart cart screenshot to {screenshot_fk}")
        
        # Check Amazon Cart
        safe_print("\nChecking Amazon Cart...")
        page.goto("https://www.amazon.in/gp/cart/view.html")
        page.wait_for_timeout(5000)
        
        am_text = page.inner_text("body")
        safe_print("--- Amazon Cart Content Snippet ---")
        lines = [line.strip() for line in am_text.split("\n") if line.strip()][:15]
        for line in lines:
            safe_print(line)
            
        screenshot_am = os.path.join(screenshots_dir, "am_cart_status.png")
        page.screenshot(path=screenshot_am)
        safe_print(f"Saved Amazon cart screenshot to {screenshot_am}")
        
        browser.close()

if __name__ == "__main__":
    main()
