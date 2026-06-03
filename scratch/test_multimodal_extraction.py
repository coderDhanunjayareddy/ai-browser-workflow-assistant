import json
import httpx

def main():
    print("Testing local FastAPI backend /analyze with Product Intelligence Extraction Agent task...")
    
    url = "http://localhost:8000/analyze"
    
    task = """ROLE

You are a Product Intelligence Extraction Agent.

Your job is NOT to summarize the page.

Your job is to collect every piece of information required to generate a professional product marketing video, advertisement, commercial, landing page, social media campaign, and AI-generated promotional content.

==================================================
INPUT
=====

A product page URL.

==================================================
OBJECTIVE
=========

Extract ALL available product information.

Do not skip any useful data.

Prefer structured data over summaries.

==================================================
SECTION 10
OUTPUT FORMAT
=============

Return structured JSON.

Include:

product_details
features
benefits
marketing_copy
specifications
image_urls
branding_analysis
customer_analysis
review_analysis
usp_analysis
video_marketing_intelligence

Do NOT summarize.

Return complete structured data suitable for AI video generation."""

    payload = {
        "session_id": "test-multimodal-session-1234",
        "task": task,
        "page_context": {
            "url": "https://www.sony.co.in/electronics/headband-headphones/wh-1000xm5",
            "title": "WH-1000XM5 Wireless Industry Leading Noise Cancelling Headphones | Sony IN",
            "metadata": {
                "site_name": "Sony India",
                "canonical_url": "https://www.sony.co.in/electronics/headband-headphones/wh-1000xm5"
            },
            "headings": [
                "Sony WH-1000XM5 Noise Cancelling Headphones",
                "Product Features",
                "Specifications",
                "Customer Reviews"
            ],
            "interactive_elements": [],
            "content_blocks": [
                {
                    "selector": ".hero-desc",
                    "text": "Sony WH-1000XM5 wireless noise cancelling headphones with Auto NC Optimizer, 30 hours battery life, touch controls, and crystal clear call quality. Premium design in silver and black colors."
                },
                {
                    "selector": ".price-box",
                    "text": "Special Price: Rs. 29,990. Regular Price: Rs. 34,990. Inclusive of all taxes. Free shipping."
                },
                {
                    "selector": ".features-list",
                    "text": "Key Highlights: - Two processors control 8 microphones for unprecedented noise cancellation. - Integrated Processor V1 unlocks the full potential of our HD Noise Cancelling Processor QN1. - Ultra-comfortable, lightweight design in 'Soft fit leather'. - Hands-free calling with 4 beamforming microphones."
                },
                {
                    "selector": ".reviews-summary",
                    "text": "Overall Rating: 4.7 out of 5 stars based on 850 reviews. Customer Sentiment: Love the sound stage and absolute silence from active noise cancelling. A few users mentioned they wished the headband could fold smaller."
                }
            ],
            "selected_text": "",
            "visible_text": "Sony WH-1000XM5 Industry Leading Noise Cancelling Headphones. Price is Rs. 29,990. 30 hour battery life, Soft fit leather ear pads. 4.7 star rating.",
            "images": [
                "https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png",
                "https://images-api.nasa.gov/img/nasa-logo.png"
            ]
        },
        "prior_steps": [],
        "supplemental_context": ""
    }

    try:
        response = httpx.post(url, json=payload, timeout=30.0)
        print(f"HTTP Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("\nBackend Response Analysis field content:")
            print("==================================================")
            print(result.get("analysis"))
            print("==================================================")
            print(f"\nNumber of suggested actions: {len(result.get('suggested_actions', []))}")
        else:
            print(f"Error detail: {response.text}")
            
    except Exception as e:
        print(f"Connection or execution failed: {e}")

if __name__ == "__main__":
    main()
