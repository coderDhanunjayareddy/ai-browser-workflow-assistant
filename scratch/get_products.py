import sys
from playwright.sync_api import sync_playwright

def main():
    print("Launching Chromium...")
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir="c:/Work/AI_Browser_Assist/chrome-profile",
            headless=False,
            viewport={"width": 1280, "height": 800}
        )
        page = browser.pages[0] if browser.pages else browser.new_page()

        # Flipkart
        print("\n--- Searching Flipkart ---")
        page.goto("https://www.flipkart.com")
        page.wait_for_timeout(3000)
        
        # Close login pop-up if visible
        try:
            close_btn = page.query_selector("button:has-text('✕')")
            if close_btn:
                close_btn.click()
                print("Closed login popup.")
        except Exception:
            pass

        search_input = page.query_selector("input[title*='Search']")
        if not search_input:
            search_input = page.query_selector("input[placeholder*='Search']")
        
        if search_input:
            search_input.fill("wireless headphones under 2000")
            search_input.press("Enter")
        else:
            print("Flipkart search input not found.")
            
        page.wait_for_timeout(5000)
        
        print("Extracting top 3 Flipkart products...")
        # On Flipkart, search results are either grid or list.
        # Let's extract items: title, price, rating
        flipkart_items = []
        
        # Grid layout selector (e.g. div[data-id])
        cards = page.query_selector_all("div[data-id]")
        if not cards:
            # Try list layout
            cards = page.query_selector_all("div._757964c4") # Flipkart search product cards
        if not cards:
            cards = page.query_selector_all("div._1AtVb2")
            
        print(f"Found {len(cards)} card elements on Flipkart.")
        
        # Let's extract titles, prices and ratings
        # Flipkart often has title inside a title attribute or anchor tag
        for i, card in enumerate(cards):
            if len(flipkart_items) >= 3:
                break
            try:
                # Find title
                title_el = card.query_selector("a.wjcEIp") # grid title
                if not title_el:
                    title_el = card.query_selector("a.IRpwTa")
                if not title_el:
                    title_el = card.query_selector("a.s1Q9rs")
                if not title_el:
                    title_el = card.query_selector("div._4rR01T") # list title
                if not title_el:
                    title_el = card.query_selector("a.wjcEIp")
                
                title = title_el.inner_text() if title_el else ""
                
                # Find price
                price_el = card.query_selector("div._30jeq3")
                if not price_el:
                    price_el = card.query_selector("div.Nx9w7A")
                if not price_el:
                    price_el = card.query_selector("div._10Ermr")
                price_text = price_el.inner_text() if price_el else ""
                
                # Find rating
                rating_el = card.query_selector("div._3LWZlK")
                if not rating_el:
                    rating_el = card.query_selector("span._2_R_DZ")
                if not rating_el:
                    rating_el = card.query_selector("div.XQD0XM")
                rating = rating_el.inner_text() if rating_el else "0.0"
                
                if title and price_text:
                    flipkart_items.append({
                        "title": title,
                        "price_text": price_text,
                        "rating": rating,
                        "card_index": i
                    })
            except Exception as e:
                print(f"Error parsing Flipkart card: {e}")
                
        print("Flipkart Results:")
        for idx, item in enumerate(flipkart_items, 1):
            print(f"{idx}. {item['title']} | Price: {item['price_text']} | Rating: {item['rating']}")

        # Amazon
        print("\n--- Searching Amazon ---")
        page.goto("https://www.amazon.in")
        page.wait_for_timeout(3000)
        
        search_input = page.query_selector("#twotabsearchtextbox")
        if search_input:
            search_input.fill("wireless headphones under 2000")
            search_input.press("Enter")
        else:
            print("Amazon search input not found.")
            
        page.wait_for_timeout(5000)
        
        print("Extracting top 3 Amazon products...")
        amazon_items = []
        
        # Amazon search items are in divs with data-component-type="s-search-result"
        cards = page.query_selector_all("div[data-component-type='s-search-result']")
        print(f"Found {len(cards)} card elements on Amazon.")
        
        for i, card in enumerate(cards):
            if len(amazon_items) >= 3:
                break
            try:
                # Skip sponsored products if visible
                sponsored = card.query_selector("span:has-text('Sponsored')")
                if sponsored:
                    continue
                    
                # Find title
                title_el = card.query_selector("h2 a span")
                title = title_el.inner_text() if title_el else ""
                
                # Find price
                price_el = card.query_selector("span.a-price-whole")
                price_text = price_el.inner_text() if price_el else ""
                
                # Find rating
                rating_el = card.query_selector("i.a-icon-star-small span")
                if not rating_el:
                    rating_el = card.query_selector("span.a-icon-alt")
                rating = rating_el.inner_text() if rating_el else "0.0"
                if "out of" in rating:
                    rating = rating.split("out of")[0].strip()
                    
                if title and price_text:
                    amazon_items.append({
                        "title": title,
                        "price_text": f"Rs. {price_text}",
                        "rating": rating,
                        "card_index": i
                    })
            except Exception as e:
                print(f"Error parsing Amazon card: {e}")
                
        print("Amazon Results:")
        for idx, item in enumerate(amazon_items, 1):
            print(f"{idx}. {item['title']} | Price: {item['price_text']} | Rating: {item['rating']}")
            
        browser.close()

if __name__ == "__main__":
    main()
