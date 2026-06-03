import os
import re
from playwright.sync_api import sync_playwright

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        try:
            print(text.encode('ascii', errors='replace').decode('ascii'))
        except Exception:
            pass

def clean_price(price_str):
    if not price_str:
        return 0
    # Remove currency symbols and commas
    price_clean = re.sub(r'[^\d]', '', price_str)
    return int(price_clean) if price_clean else 0

def clean_rating(rating_str):
    if not rating_str:
        return 0.0
    # Find the first float value
    match = re.search(r'(\d\.\d)', rating_str)
    return float(match.group(1)) if match else 0.0

def main():
    safe_print("Launching Chromium...")
    
    # Create screenshots directory
    screenshots_dir = "c:/Work/AI_Browser_Assist/screenshots"
    os.makedirs(screenshots_dir, exist_ok=True)
    
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir="c:/Work/AI_Browser_Assist/chrome-profile",
            headless=False,
            viewport={"width": 1280, "height": 800}
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        
        # 1. FLIPKART
        safe_print("\n=== Flipkart Search ===")
        page.goto("https://www.flipkart.com/search?q=wireless%20headphones%20under%202000&otracker=search&otracker1=search&marketplace=FLIPKART&as-show=on&as=off")
        page.wait_for_timeout(5000)
        
        flipkart_candidates = []
        cards = page.query_selector_all("div[data-id]")
        safe_print(f"Found {len(cards)} elements on Flipkart.")
        
        for idx, card in enumerate(cards):
            try:
                # Text content
                text = card.inner_text()
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if not lines:
                    continue
                
                title = lines[0]
                
                # Check for price line
                price = 0
                price_text = ""
                for line in lines:
                    if "₹" in line or "?" in line:
                        match = re.search(r'[₹?]([0-9,]+)', line)
                        if match:
                            price_text = match.group(0)
                            price = clean_price(price_text)
                            break
                
                # Check for rating line
                rating = 0.0
                for line in lines:
                    # e.g., "4.1(6,987)" or "4.1"
                    match = re.search(r'(\d\.\d)(?:\b|\()', line)
                    if match:
                        rating = float(match.group(1))
                        break
                
                # Anchor link
                a_el = card.query_selector("a")
                href = a_el.get_attribute("href") if a_el else ""
                url = f"https://www.flipkart.com{href}" if href and href.startswith("/") else href
                
                if title and price > 0 and price <= 2000 and url:
                    flipkart_candidates.append({
                        "title": title,
                        "price": price,
                        "rating": rating,
                        "url": url,
                        "source": "Flipkart"
                    })
            except Exception as e:
                safe_print(f"Error parsing Flipkart card: {e}")
                
        # Slice to top 3
        flipkart_top3 = flipkart_candidates[:3]
        safe_print("\nFlipkart Top 3 Candidates (Under 2000):")
        for i, item in enumerate(flipkart_top3, 1):
            safe_print(f"{i}. {item['title'][:50]}... | Price: {item['price']} | Rating: {item['rating']}")
            
        # 2. AMAZON
        safe_print("\n=== Amazon Search ===")
        page.goto("https://www.amazon.in/s?k=wireless+headphones+under+2000")
        page.wait_for_timeout(5000)
        
        amazon_candidates = []
        cards = page.query_selector_all("div[data-component-type='s-search-result']")
        safe_print(f"Found {len(cards)} elements on Amazon.")
        
        for idx, card in enumerate(cards):
            try:
                # Skip sponsored products
                sponsored = card.query_selector("span:has-text('Sponsored')")
                if sponsored:
                    continue
                    
                text = card.inner_text()
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if not lines:
                    continue
                
                # Title
                title_el = card.query_selector("h2 a span")
                title = title_el.inner_text() if title_el else lines[0]
                
                # Price
                price_el = card.query_selector("span.a-price-whole")
                price = clean_price(price_el.inner_text()) if price_el else 0
                if price == 0:
                    # Fallback parsing from lines
                    for line in lines:
                        if "₹" in line or "?" in line:
                            match = re.search(r'[₹?]([0-9,]+)', line)
                            if match:
                                price = clean_price(match.group(1))
                                break
                
                # Rating
                rating = 0.0
                rating_el = card.query_selector("i.a-icon-star-small span")
                if not rating_el:
                    rating_el = card.query_selector("span.a-icon-alt")
                if rating_el:
                    rating = clean_rating(rating_el.inner_text())
                if rating == 0.0:
                    for line in lines:
                        if "out of 5 stars" in line:
                            rating = clean_rating(line)
                            break
                
                # Anchor
                a_el = card.query_selector("h2 a")
                if not a_el:
                    a_el = card.query_selector("a")
                href = a_el.get_attribute("href") if a_el else ""
                url = f"https://www.amazon.in{href}" if href and href.startswith("/") else href
                
                if title and price > 0 and price <= 2000 and url:
                    amazon_candidates.append({
                        "title": title,
                        "price": price,
                        "rating": rating,
                        "url": url,
                        "source": "Amazon"
                    })
            except Exception as e:
                safe_print(f"Error parsing Amazon card: {e}")
                
        # Slice to top 3
        amazon_top3 = amazon_candidates[:3]
        safe_print("\nAmazon Top 3 Candidates (Under 2000):")
        for i, item in enumerate(amazon_top3, 1):
            safe_print(f"{i}. {item['title'][:50]}... | Price: {item['price']} | Rating: {item['rating']}")
            
        # 3. COMPARE AND CHOOSE THE WINNER
        all_candidates = flipkart_top3 + amazon_top3
        if not all_candidates:
            safe_print("Error: No candidates found on either site under 2000!")
            browser.close()
            return
            
        safe_print("\n=== Comparison of Top Results ===")
        for i, item in enumerate(all_candidates, 1):
            safe_print(f"Candidate {i}: [{item['source']}] {item['title'][:40]}... | Price: Rs. {item['price']} | Rating: {item['rating']}")
            
        # Sort candidates: Primary key Rating (descending), Secondary key Price (ascending)
        sorted_candidates = sorted(all_candidates, key=lambda x: (-x['rating'], x['price']))
        winner = sorted_candidates[0]
        
        safe_print(f"\nWinning Product: [{winner['source']}] {winner['title']}")
        safe_print(f"Winning Details: Price = Rs. {winner['price']} | Rating = {winner['rating']}")
        safe_print(f"Winning URL: {winner['url']}")
        
        # 4. NAVIGATE TO WINNER AND ADD TO CART
        safe_print(f"\nNavigating to winning product details page...")
        page.goto(winner['url'])
        page.wait_for_timeout(5000)
        
        # Add to cart
        if winner['source'] == "Flipkart":
            safe_print("Adding to cart on Flipkart...")
            # Flipkart Add to Cart button selectors
            cart_selectors = [
                "button:has-text('ADD TO CART')",
                "button:has-text('Add to Cart')",
                "button:has-text('Add to cart')",
                "button._2KpZ6l._2U9uBO._3-iZgS",
                "button._2KpZ6l"
            ]
            clicked = False
            for sel in cart_selectors:
                try:
                    btn = page.query_selector(sel)
                    if btn:
                        btn.click()
                        safe_print(f"Clicked Flipkart cart button with selector: {sel}")
                        clicked = True
                        break
                except Exception:
                    pass
            if not clicked:
                safe_print("Warning: Could not click Flipkart add to cart button using standard selectors. Trying default selectors...")
                page.click("text=ADD TO CART")
                
        else:
            safe_print("Adding to cart on Amazon...")
            # Amazon Add to Cart button selectors
            cart_selectors = [
                "#add-to-cart-button",
                "input[name='submit.add-to-cart']",
                "input[value='Add to Cart']",
                "input[aria-label='Add to Cart']"
            ]
            clicked = False
            for sel in cart_selectors:
                try:
                    btn = page.query_selector(sel)
                    if btn:
                        btn.click()
                        safe_print(f"Clicked Amazon cart button with selector: {sel}")
                        clicked = True
                        break
                except Exception:
                    pass
            if not clicked:
                safe_print("Warning: Could not click Amazon add to cart button using standard selectors. Trying default selectors...")
                page.click("#add-to-cart-button")
                
        page.wait_for_timeout(5000)
        
        # Check cart status
        safe_print("Taking final cart page screenshot...")
        screenshot_path = os.path.join(screenshots_dir, "final_cart_page.png")
        page.screenshot(path=screenshot_path)
        safe_print(f"Saved final cart page screenshot to {screenshot_path}")
        
        safe_print("\nWorkflow Completed Successfully!")
        browser.close()

if __name__ == "__main__":
    main()
