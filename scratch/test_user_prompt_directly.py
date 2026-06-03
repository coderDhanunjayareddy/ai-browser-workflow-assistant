import sys
import os
import time

sys.path.insert(0, "c:/Work/AI_Browser_Assist/backend")

# Set up environment variables from .env
try:
    with open("backend/.env", "r") as f:
        for line in f:
            if line.startswith("GEMINI_API_KEY="):
                os.environ["GEMINI_API_KEY"] = line.split("=")[1].strip()
            if line.startswith("GEMINI_MODEL="):
                os.environ["GEMINI_MODEL"] = line.split("=")[1].strip()
except Exception as e:
    print("Error reading .env:", e)

from app.schemas.request import PageContext
from app.services import ai_service
from app.core.config import settings

def main():
    print(f"GEMINI_API_KEY configured: {bool(settings.gemini_api_key)}")
    print(f"GEMINI_MODEL configured: {settings.gemini_model}")
    
    task = """OUTPUT PRIORITY RULE

The final objective is to generate a high-converting commercial advertisement.

Whenever information is incomplete:

1. Use verified product data first.
2. Use product images second.
3. Use customer reviews third.
4. Make reasonable marketing inferences only when necessary.

Prioritize:
- Product accuracy
- Branding consistency
- Conversion potential
- Storytelling quality


IMPORTANT:

This extraction is NOT intended for data storage.

This extraction is intended to power:

- AI Video Generation
- Commercial Creation
- Marketing Campaigns
- Product Advertisements
- Social Media Promotions

Whenever multiple interpretations are possible, prioritize the information most useful for generating high-converting product marketing videos.

ROLE

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

Extract information from:

* Product title
* Product images
* Product gallery
* Product description
* Product highlights
* Product specifications
* Product attributes
* Product variants
* Product reviews
* Product ratings
* Product Q&A
* Product packaging
* Brand information
* Marketing copy
* Visible text
* Embedded metadata

==================================================
SECTION 1
PRODUCT IDENTIFICATION
======================

Extract:

* Product Name
* Brand Name
* Category
* Sub Category
* Product Type
* Flavor
* Variant
* Model Number
* SKU
* Quantity
* Pack Size
* Weight
* Volume
* Manufacturing Information

==================================================
SECTION 2
PRODUCT FEATURES
================

Extract:

* Key Features
* Product Highlights
* Specifications
* Ingredients
* Materials
* Technical Details
* Functional Benefits
* Claimed Benefits

Return as bullet points.

==================================================
SECTION 3
PRODUCT MARKETING COPY
======================

Extract ALL visible marketing language exactly.

Capture:

* Headlines
* Taglines
* Product Claims
* Promotional Text
* Benefit Statements
* Brand Messaging

Do not rewrite.

Store exact wording.

==================================================
SECTION 4
PRODUCT IMAGES
==============

Download ALL product images.

For every image return:

* Image URL
* Image Type

Classify:

* Front View
* Back View
* Side View
* Packaging View
* Lifestyle Image
* Ingredient Image
* Infographic
* Promotional Banner
* Product Detail Image
* Comparison Image

==================================================
SECTION 5
VISUAL BRANDING ANALYSIS
========================

Analyze ALL product images.

Extract:

* Primary Colors
* Secondary Colors
* Accent Colors

Determine:

* Packaging Style
* Design Language
* Typography Style
* Branding Style
* Product Shape
* Material Appearance
* Finish Type

Classify Brand Personality:

* Premium
* Luxury
* Minimalist
* Youthful
* Energetic
* Modern
* Traditional
* Health Focused
* Fitness Focused
* Lifestyle Focused
* Budget Friendly

Provide confidence score.

==================================================
SECTION 6
CUSTOMER ANALYSIS
=================

Determine likely:

* Target Audience
* Customer Persona
* Age Group
* Gender Targeting
* Lifestyle Type
* Purchase Motivation

Identify:

* Problems solved
* Emotional benefits
* Functional benefits

==================================================
SECTION 7
SOCIAL PROOF
============

Extract:

* Rating
* Rating Count
* Review Count

Extract top positive review themes.

Extract top negative review themes.

Extract repeated customer mentions.

==================================================
SECTION 8
MARKETING INTELLIGENCE
======================

Determine:

* Core USP
* Main Selling Point
* Emotional Trigger
* Functional Trigger
* Trust Trigger
* Purchase Trigger

Identify:

* Why customers buy it
* Why customers recommend it
* Why customers choose it over alternatives

==================================================
SECTION 9
VIDEO AD INTELLIGENCE
=====================

Generate marketing insights:

* Best Story Angle
* Best Hook
* Best Emotional Narrative
* Best Video Theme
* Best Customer Journey
* Best Conversion Angle

Suggest:

* Problem → Solution Angle
* Lifestyle Angle
* Aspirational Angle
* Trend-Based Angle
* Emotional Angle

Rank them.

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

SECTION 11
PRODUCT VIDEO GENERATION ASSETS

Identify:

1. Hero Product Image
2. Best Thumbnail Image
3. Best Product Reveal Image
4. Best Closeup Image

Perform OCR on all images.

Extract:

- Logo
- Branding Text
- Flavor Name
- Claims
- Marketing Text

Generate:

- Recommended Product Reveal Scene
- Recommended Hero Shot
- Recommended Product Rotation Shot
- Recommended Closeup Shot
- Recommended Slow Motion Shot
- Recommended Product Showcase Sequence

If beverage:

Generate:

- Ice Scene
- Chilled Can Scene
- Condensation Scene
- Opening Scene
- Pouring Scene
- Splash Scene
- Final Hero Scene

==================================================
SECTION 12
VERIFIED PRODUCT ASSET VALIDATION
==================================================

Before storing any image:

Verify whether the image belongs to the current product.

Create two collections:

verified_product_images
rejected_images

For every rejected image provide:

- Image URL
- Product Name Detected
- Rejection Reason

Reject:

- Similar Products
- Sponsored Products
- Recommended Products
- Cross Sell Products
- Related Products
- Competitor Products

Only verified product images may be used for:

- Hero Shots
- Product Reveal
- Product Showcase
- Product Branding Analysis
- Video Generation

Determine:

- Primary Hero Image
- Primary Product Reveal Image
- Primary Thumbnail Image
- Best Branding Image
- Best Closeup Image
- Best Packaging Image

Assign confidence score to each.

==================================================
SECTION 13
USP PRIORITIZATION ENGINE
==================================================

Identify ALL product USPs.

Rank them.

Return:

Primary USP
Secondary USP
Tertiary USP

For each USP provide:

- Importance Score
- Marketing Impact Score
- Purchase Influence Score

Determine:

What should appear first in advertising.

Determine:

Top 3 reasons customers buy this product.

Determine:

Top 3 reasons customers choose this over competitors.

Generate:

Advertising Priority Stack

Example:

1. Primary USP
2. Secondary USP
3. Supporting USP
4. Trust Builder
5. Conversion Trigger

==================================================
SECTION 14
TELUGU MARKET INTELLIGENCE
==================================================

Analyze product suitability for Telugu audience.

Determine:

- Best Telugu Audience Segment
- Best Age Group
- Best Lifestyle Segment

Generate:

Telugu Audience Personas

Identify:

- Cultural Triggers
- Emotional Triggers
- Lifestyle Triggers

Generate:

Best Telugu Story Scenarios

Examples:

- College Friends
- Summer Heat
- Gym Lifestyle
- Office Break
- Family Gathering
- Road Trip
- Movie Night
- Festival Mood
- Weekend Chill
- Late Night Cravings

Rank all scenarios.

Determine:

Most effective Telugu advertising angle.

==================================================
SECTION 15
CONVERSION INTELLIGENCE
==================================================

Determine:

Most Likely Buyer Objections

Examples:

- Too expensive
- Taste concern
- Trust concern
- Health concern
- Ingredient concern

For every objection provide:

- Objection
- Why customer thinks this
- Best response
- Best marketing answer

Determine:

Reason To Buy

Reason To Buy Now

Reason To Switch From Competitors

Trust Factors

Urgency Factors

Conversion Triggers

Generate:

Customer Decision Framework

Explain:

Why a customer would purchase this product immediately.

==================================================
SECTION 16
AI VIDEO GENERATION BRIEF
==================================================

Generate a complete AI-ready creative brief.

Return:

Recommended Story Type

Recommended Marketing Angle

Recommended Hero Character

Recommended Audience

Recommended Emotional Trigger

Recommended Problem

Recommended Solution

Recommended Transformation

Recommended CTA

Generate:

Opening Scene

Hook Scene

Problem Scene

Product Discovery Scene

Solution Scene

Transformation Scene

Hero Product Scene

CTA Scene

Determine:

Visual Mood

Color Palette

Lighting Style

Camera Style

Editing Style

Music Style

Voiceover Style

Generate:

Video Theme

Video Tagline

Video Slogan

Video Narrative

Generate:

Complete Creative Direction suitable for:

- AI Video Generation
- Commercial Production
- Social Media Marketing
- Product Advertisement

# ==================================================
# SECTION 17
# VISUAL SCENE BLUEPRINT
# ==================================================

Determine the optimal visual storytelling structure for a high-converting commercial advertisement.

Generate a complete visual scene blueprint based on:

- Product Features
- Product Benefits
- Product Branding
- Product Packaging
- Customer Psychology
- Marketing Intelligence
- USP Analysis
- Conversion Intelligence
- Target Audience
- Emotional Triggers

Create visual recommendations for every stage of the commercial.

Return:

{
  "visual_scene_blueprint": {

    "hook_visuals": [
      {
        "scene": "",
        "purpose": "",
        "emotion": "",
        "camera_style": ""
      }
    ],

    "problem_visuals": [
      {
        "scene": "",
        "purpose": "",
        "emotion": "",
        "camera_style": ""
      }
    ],

    "pain_amplification_visuals": [
      {
        "scene": "",
        "purpose": "",
        "emotion": "",
        "camera_style": ""
      }
    ],

    "product_discovery_visuals": [
      {
        "scene": "",
        "purpose": "",
        "emotion": "",
        "camera_style": ""
      }
    ],

    "product_reveal_visuals": [
      {
        "scene": "",
        "purpose": "",
        "emotion": "",
        "camera_style": ""
      }
    ],

    "benefit_visuals": [
      {
        "scene": "",
        "purpose": "",
        "usp_highlighted": "",
        "camera_style": ""
      }
    ],

    "transformation_visuals": [
      {
        "scene": "",
        "purpose": "",
        "emotion": "",
        "camera_style": ""
      }
    ],

    "trust_builder_visuals": [
      {
        "scene": "",
        "purpose": "",
        "message": ""
      }
    ],

    "social_proof_visuals": [
      {
        "scene": "",
        "purpose": "",
        "message": ""
      }
    ],

    "cta_visuals": [
      {
        "scene": "",
        "purpose": "",
        "cta_message": ""
      }
    ]
  }
}

Additionally generate:

- Best Hook Visual
- Best Product Reveal Visual
- Best Transformation Visual
- Best CTA Visual

Generate:

- Hero Product Scene
- Product Showcase Scene
- Product Rotation Scene
- Product Closeup Scene
- Product Packaging Scene

If beverage:

Generate:

- Chilled Can Scene
- Ice Scene
- Condensation Scene
- Opening Scene
- Pouring Scene
- Splash Scene
- Flavor Visualization Scene
- Refreshment Visualization Scene

For every recommended scene provide:

- Objective
- Emotional Trigger
- Camera Movement
- Shot Type
- Lighting Style
- Visual Priority Score

The purpose of this section is to create AI-video-ready visual storytelling assets.

# ==================================================
# SECTION 18
# AI VIDEO GENERATION PROMPT
# ==================================================

Generate a COMPLETE AI VIDEO GENERATION PROMPT.

The prompt must be immediately usable inside:

- Veo
- Runway
- Kling
- Sora
- Pika
- Hailuo
- LTX Studio
- Any AI Video Generator

The prompt should be based on:

- Product Analysis
- Visual Branding Analysis
- USP Analysis
- Customer Analysis
- Marketing Intelligence
- Conversion Intelligence
- Telugu Market Intelligence
- Visual Scene Blueprint

Generate a professional commercial prompt.

Return:

{
  "video_generation_prompt": {
    "video_title": "",
    "video_theme": "",
    "story_type": "",
    "duration": "",
    "language": "",
    "target_audience": "",
    "marketing_angle": "",
    "emotional_trigger": "",
    "visual_style": "",
    "camera_style": "",
    "editing_style": "",
    "music_style": "",
    "voiceover_style": "",
    "color_palette": "",
    "story_summary": "",
    "full_prompt": ""
  }
}

The generated prompt must include:

1. Product Information
2. Brand Information
3. Story Structure
4. Hook
5. Problem
6. Pain Escalation
7. Product Discovery
8. Product Reveal
9. Product Demonstration
10. USP Highlights
11. Transformation
12. Trust Building
13. CTA

Include:

- Exact Product Name
- Exact Branding
- Exact Packaging Description
- Exact Product Colors
- Exact Product Shape
- Exact Product Appearance

Do NOT allow the AI video generator to redesign the product.

Include instructions:

- Use actual product appearance
- Maintain branding consistency
- Maintain packaging consistency
- Maintain typography consistency

Include:

- Hero Shots
- Product Rotation Shots
- Product Closeups
- Product Showcase Shots

If beverage:

Include:

- Chilled Beverage Scene
- Ice Scene
- Can Opening Scene
- Pouring Scene
- Splash Scene
- Condensation Scene
- Refreshment Scene

Generate:

- Telugu Voiceover Direction
- Telugu Emotional Tone
- Telugu Audience Connection Strategy

Generate:

- Scene Flow
- Visual Flow
- Camera Flow
- Emotional Flow

Generate:

- Final Tagline
- Final Slogan
- Final CTA

The final prompt must be production-ready and suitable for generating a professional client-grade marketing video without requiring additional manual editing.

# ==================================================
# SECTION 19
# MASTER CREATIVE DIRECTOR OUTPUT
# ==================================================

Act as a Senior Creative Director, Marketing Strategist, Brand Consultant, Commercial Director, Consumer Psychologist, and Video Advertising Expert.

Using ALL previously generated sections:

- Product Analysis
- Visual Branding Analysis
- Customer Analysis
- USP Analysis
- Review Analysis
- Marketing Intelligence
- Telugu Market Intelligence
- Conversion Intelligence
- Visual Scene Blueprint
- Video Generation Prompt

Generate a FINAL EXECUTION PACKAGE.

This package should be the single source of truth for:

- AI Video Generation
- Commercial Production
- Marketing Campaign Creation
- Social Media Advertising
- Product Promotions

==================================================
OUTPUT FORMAT
==================================================

Return:

{
  "master_creative_director_output": {

    "executive_summary": {},

    "marketing_brief": {},

    "customer_psychology": {},

    "usp_hierarchy": {},

    "visual_branding_guide": {},

    "visual_scene_blueprint": {},

    "creative_direction": {},

    "storyboard": {},

    "video_generation_prompt": {},
    
    "final_video_generation_prompt": "",

    "telugu_voiceover_strategy": {},

    "final_campaign_assets": {}
  }
}

==================================================
EXECUTIVE SUMMARY
==================================================

Generate:

- Product Summary
- Brand Summary
- Core Marketing Message
- Core Emotional Trigger
- Core Conversion Trigger
- Campaign Objective
- Recommended Campaign Type

==================================================
MARKETING BRIEF
==================================================

Generate:

- Campaign Name
- Campaign Theme
- Campaign Tagline
- Campaign Slogan
- Campaign Positioning

Generate:

- Why This Product Wins
- Why Customers Buy
- Why Customers Switch
- Why Customers Trust

==================================================
CUSTOMER PSYCHOLOGY
==================================================

Generate:

- Customer Pain Points
- Customer Desires
- Customer Motivations
- Customer Fears
- Customer Objections

Generate:

- Emotional Triggers
- Rational Triggers
- Trust Triggers
- Urgency Triggers

==================================================
USP HIERARCHY
==================================================

Generate:

- Primary USP
- Secondary USP
- Tertiary USP

Generate:

- Advertising Priority Order
- Purchase Influence Ranking
- Conversion Influence Ranking

==================================================
VISUAL BRANDING GUIDE
==================================================

Generate:

- Product Identity
- Brand Personality
- Color Palette
- Typography Style
- Packaging Style

Generate:

- Product Appearance Rules
- Product Consistency Rules
- Product Branding Rules

Important:

The final commercial MUST preserve:

- Product Packaging
- Product Colors
- Product Shape
- Product Branding
- Product Typography

Do NOT redesign the product.

==================================================
VISUAL SCENE BLUEPRINT
==================================================

Generate:

- Hook Visuals
- Problem Visuals
- Pain Escalation Visuals
- Discovery Visuals
- Product Reveal Visuals
- Benefit Visuals
- Transformation Visuals
- Trust Builder Visuals
- CTA Visuals

For every scene provide:

- Objective
- Emotional Trigger
- Camera Style
- Camera Movement
- Shot Type
- Lighting Style

==================================================
CREATIVE DIRECTION
==================================================

Generate:

- Recommended Story Type
- Recommended Marketing Angle
- Recommended Hero Character
- Recommended Supporting Characters

Generate:

- Visual Mood
- Visual Theme
- Emotional Theme
- Storytelling Style

Generate:

- Editing Style
- Music Style
- Camera Style
- Color Grading Style

==================================================
STORYBOARD
==================================================

Generate:

1. Hook
2. Problem
3. Pain Escalation
4. Product Discovery
5. Product Reveal
6. Product Demonstration
7. USP Showcase
8. Transformation
9. Trust Building
10. CTA

For every stage provide:

- Scene Description
- Visual Direction
- Emotional Objective
- Conversion Objective

==================================================
VIDEO GENERATION PROMPT
==================================================

Generate a COMPLETE production-ready AI video prompt.

The prompt must work with:

- Veo
- Runway
- Kling
- Sora
- Hailuo
- Pika
- LTX Studio

Include:

- Exact Product Details
- Exact Branding Details
- Exact Packaging Details
- Exact Product Appearance

Include:

- Story Structure
- Scene Flow
- Camera Flow
- Visual Flow
- Emotional Flow

Include:

- Product Hero Shots
- Product Rotation Shots
- Product Closeups
- Product Showcase Scenes

If Beverage:

Include:

- Chilled Can Scene
- Ice Scene
- Opening Scene
- Pouring Scene
- Splash Scene
- Condensation Scene
- Refreshment Scene

==================================================
TELUGU VOICEOVER STRATEGY
==================================================

Generate:

- Telugu Voice Tone
- Telugu Narration Style
- Telugu Emotional Tone

Generate:

- Recommended Telugu Vocabulary Style

Choose:

- Youthful Telugu
- Premium Telugu
- Family Telugu
- Mass Telugu

Based on target audience.

Generate:

- Hook Dialogue Direction
- Problem Dialogue Direction
- Solution Dialogue Direction
- CTA Dialogue Direction

==================================================
FINAL CAMPAIGN ASSETS
==================================================

Generate:

- Final Campaign Name
- Final Campaign Theme
- Final Campaign Tagline
- Final Campaign Slogan
- Final CTA

Generate:

- Instagram Ad Angle
- Facebook Ad Angle
- YouTube Shorts Angle
- WhatsApp Marketing Angle

Generate:

- Thumbnail Concept
- Hero Product Concept
- Viral Hook Concept

==================================================
FINAL RULE
==================================================

This output must be treated as the FINAL CREATIVE BLUEPRINT.

The generated output should require minimal human intervention and be immediately usable for:

- AI Video Generation
- Commercial Production
- Product Marketing
- Social Media Advertising
- Client Deliverables

Prioritize:

1. Conversion Potential
2. Emotional Engagement
3. Brand Consistency
4. Product Accuracy
5. Storytelling Quality
6. Telugu Audience Connection

Do NOT summarize.

Return complete structured data suitable for AI video generation.
"""

    ctx_data = {
        "url": "https://www.flipkart.com/bloodybubbly-bloody-zero-vanilla-float-can/p/itmfe828de7d79cf?pid=ARDHNHBZHGHG8AZQ&lid=LSTARDHNHBZHGHG8AZQMBMR5T&marketplace=FLIPKART&q=cool+drink&store=eat&srno=s_1_1&otracker=search&otracker1=search&fm=Search&iid=368f10ff-2103-4dfa-9d81-aa693e043590.ARDHNHBZHGHG8AZQ.SEARCH&ppt=sp&ppn=sp&ssid=f8lrwklr3k0000001780379812835&qH=cc940c0852575fff&ov_redirect=true&ov_redirect=true",
        "title": "BLOODYBUBBLY Bloody Zero Vanilla Float Can (4 x 250 ml) Price in India - Buy BLOODYBUBBLY Bloody Zero Vanilla Float Can (4 x 250 ml) online at Flipkart.com",
        "metadata": {
            "site_name": "Flipkart",
            "canonical_url": "https://www.flipkart.com/bloodybubbly-bloody-zero-vanilla-float-can/p/itmfe828de7d79cf"
        },
        "headings": [
            "BLOODYBUBBLY Bloody Zero Vanilla Float Can (4 x 250 ml)",
            "Product Details",
            "Specifications",
            "Ratings & Reviews"
        ],
        "interactive_elements": [],
        "content_blocks": [
            {
                "selector": ".title-box",
                "text": "BLOODYBUBBLY Bloody Zero Vanilla Float Can (4 x 250 ml). Special price: ₹266 (original ₹299). Save 11%."
            },
            {
                "selector": ".desc-box",
                "text": "Product Description: Bloody Zero Vanilla Float is a zero sugar, zero calorie carbonated soft drink. Naturally sweetened with monkfruit extract and allulose. Caffeine-free, no artificial flavors, colors or sweeteners. Expiry date: 23 Aug 2027. Fulfilled by Elxrbeverages."
            }
        ],
        "selected_text": "",
        "visible_text": "BLOODYBUBBLY Bloody Zero Vanilla Float Can (4 x 250 ml). Zero Sugar, Zero Calories, Naturally Sweetened with Monkfruit. Expiry 2027.",
        "images": [
            "https://rukminim1.flixcart.com/image/480/640/xif0q/aerated-drink/i/y/q/1000-bloody-zero-vanilla-float-can-4-bloody-bubbly-original-imahnhbzcner9gvh.jpeg?q=80"
        ]
    }
    
    ctx = PageContext(**ctx_data)
    
    print("\nCalling ai_service.analyze directly...")
    start_time = time.time()
    try:
        response = ai_service.analyze(
            session_id="direct-user-test-session",
            task=task,
            page_context=ctx,
            prior_steps=[],
            supplemental_context=""
        )
        duration = time.time() - start_time
        print(f"\nCompleted in {duration:.2f} seconds.")
        # Print safely in case of windows terminal encoding issues
        print(response.analysis.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding))
    except Exception as e:
        print("\nFailed with exception:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
