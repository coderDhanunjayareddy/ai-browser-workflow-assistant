import re
from urllib.parse import quote, urljoin

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


SEARCH_URL = "https://www.flipkart.com/search?q=" + quote("realme buds under 2000")


def close_popups(page) -> None:
    for text in ("✕", "Login", "Not Now"):
        try:
            locator = page.get_by_text(text, exact=True)
            if locator.count() == 1 and locator.is_visible(timeout=1000):
                locator.click(timeout=2000)
                page.wait_for_timeout(1000)
        except Exception:
            pass


def extract_first_candidate(page):
    return page.evaluate(
        """
        () => {
          const rupee = /₹\\s*([0-9,]+)/;
          const anchors = Array.from(document.querySelectorAll('a[href*="/p/"]'));
          for (const anchor of anchors) {
            const container = anchor.closest('div[data-id]') || anchor.parentElement;
            const text = (container?.innerText || anchor.innerText || '').replace(/\\s+/g, ' ').trim();
            const match = text.match(rupee);
            if (!match) continue;
            const price = Number(match[1].replace(/,/g, ''));
            const title = text.split('₹')[0].trim();
            const haystack = `${title} ${text}`.toLowerCase();
            if (price <= 2000 && haystack.includes('realme') && haystack.includes('bud')) {
              return {
                title,
                price,
                href: new URL(anchor.getAttribute('href'), location.href).href,
                text
              };
            }
          }
          return null;
        }
        """
    )


def click_add_to_cart(page) -> str:
    candidates = [
        page.get_by_role("button", name="Add to cart", exact=False),
        page.get_by_text("Add to cart", exact=False),
        page.get_by_text("ADD TO CART", exact=False),
    ]
    for locator in candidates:
        try:
            count = locator.count()
            if count > 0:
                locator.nth(0).click(timeout=8000)
                page.wait_for_timeout(4000)
                return "clicked"
        except Exception:
            continue
    return "not_found"


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir="c:/Work/AI_Browser_Assist/chrome-profile",
            headless=False,
            viewport={"width": 1280, "height": 800},
            no_viewport=False,
        )
        page = browser.pages[0] if browser.pages else browser.new_page()

        print(f"Opening: {SEARCH_URL}")
        page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(5000)
        close_popups(page)

        candidate = extract_first_candidate(page)
        if not candidate:
            print("FAILED: Could not find a visible Realme buds item under Rs. 2000.")
            print(f"Current URL: {page.url}")
            browser.close()
            return 1

        print(f"Selected first matching item: {candidate['title']}")
        print(f"Price: Rs. {candidate['price']}")
        print(f"Opening product: {candidate['href']}")

        page.goto(candidate["href"], wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(5000)
        close_popups(page)

        result = click_add_to_cart(page)
        if result != "clicked":
            print("FAILED: Add to Cart button was not found or could not be clicked.")
            print(f"Current URL: {page.url}")
            browser.close()
            return 1

        lowered = page.url.lower()
        visible_text = re.sub(r"\\s+", " ", page.locator("body").inner_text(timeout=5000))
        if "viewcart" in lowered or "cart" in lowered or "my cart" in visible_text.lower():
            print("SUCCESS: Item appears to be added to cart.")
        else:
            print("PARTIAL: Add to Cart was clicked, but cart confirmation was not clearly visible.")
        print(f"Final URL: {page.url}")

        browser.close()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
