"""Listing copy generation via Gemini (free) or OpenAI (fallback). JSON output, US English, Fair Housing compliant."""
import json
import os
import re

_gem_model = None


def _get_gemini():
    global _gem_model
    if _gem_model is None:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        _gem_model = genai.GenerativeModel(
            "gemini-2.5-flash",
            generation_config={"response_mime_type": "application/json", "temperature": 0.7},
        )
    return _gem_model


def _build_prompt(prop: dict) -> str:
    features_str = ", ".join(prop.get("features", [])) or "none specified"
    hoa = f"${prop['hoa_fee']}/mo HOA" if prop.get("hoa_fee") else "no HOA mentioned"

    return f"""You are writing real estate marketing copy for a listing in the United States. Output natural, professional US English.

Property data:
- Type: {prop['property_type']}
- Operation: {prop['operation']} (e.g. For Sale / For Rent)
- Address: {prop['address']}, {prop['city']}, {prop['state']} {prop['zip_code']}
- Price: ${prop['price']:,} {prop['currency']}
- Bedrooms: {prop['bedrooms']} | Bathrooms: {prop['bathrooms']}
- Living area: {prop['living_area_sqft']} sqft
- Lot size: {prop.get('lot_size_sqft', 'N/A')} sqft
- Garage: {prop.get('garage_spaces', 'N/A')}
- Year built: {prop.get('year_built', 'N/A')}
- HOA: {hoa}
- Features / amenities: {features_str}

CRITICAL RULES — Fair Housing Act compliance:
- DO NOT mention or imply any preference based on race, color, religion, national origin, sex, familial status, or disability.
- DO NOT use phrases like "perfect for families", "great for kids", "quiet neighborhood for retirees", "near church/synagogue", "no children", "ideal for single professional", or similar.
- Focus on the PROPERTY itself: features, layout, finishes, location amenities (schools/shops/transit are OK as factual info but do NOT say "great schools for your kids").
- DO NOT use real estate clichés: "dream home", "must-see", "won't last long", "luxury oasis", "hidden gem", "rare opportunity", "hurry".
- DO NOT use AI clichés: "nestled", "boasting", "stunning", "exquisite", "meticulously".

Return ONLY valid JSON with three fields:
- "description": 100-150 words, professional, factual, US English, MLS-style. Lead with the property type and key specs. Mention layout, finishes, notable features, location facts. Close with the price.
- "instagram_caption": 40-70 words for an Instagram post + 6-10 relevant hashtags (mix of city/state/property type). Engaging but not hypey.
- "headline": short 6-10 words for graphics overlay (e.g. "3-Bed Condo in Austin with Pool Access").

Output the JSON object only, no markdown fences."""


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def generate_listing_text(prop: dict) -> dict:
    if os.getenv("GEMINI_API_KEY"):
        resp = _get_gemini().generate_content(_build_prompt(prop))
        return _parse_json(resp.text)

    if os.getenv("OPENAI_API_KEY"):
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": _build_prompt(prop)}],
            response_format={"type": "json_object"},
            temperature=0.7,
        )
        return json.loads(resp.choices[0].message.content)

    raise RuntimeError("Set GEMINI_API_KEY or OPENAI_API_KEY in .env")
