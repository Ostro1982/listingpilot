"""End-to-end test US: sample US property, generates flyer + IG image + AI text."""
import os
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

BASE = Path(__file__).parent
load_dotenv(BASE / ".env")
sys.path.insert(0, str(BASE))

from generators.ai_text import generate_listing_text
from generators.pdf_gen import build_pdf
from generators.ig_image import build_ig_post


def make_sample_photo(path, label, color):
    img = Image.new("RGB", (1600, 1200), color)
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 80)
    except Exception:
        f = ImageFont.load_default()
    d.text((50, 50), label, fill=(255, 255, 255), font=f)
    img.save(path, "JPEG", quality=85)
    return str(path)


def main():
    out_dir = BASE / "static" / "output" / "test_us"
    out_dir.mkdir(parents=True, exist_ok=True)
    photos_dir = BASE / "static" / "uploads"
    photos_dir.mkdir(parents=True, exist_ok=True)

    print("[1/5] Sample photos...")
    photos = [
        make_sample_photo(photos_dir / "us_exterior.jpg", "EXTERIOR", (60, 90, 130)),
        make_sample_photo(photos_dir / "us_living.jpg", "LIVING", (140, 100, 80)),
        make_sample_photo(photos_dir / "us_kitchen.jpg", "KITCHEN", (90, 130, 100)),
        make_sample_photo(photos_dir / "us_bedroom.jpg", "MASTER BED", (130, 80, 110)),
    ]

    prop = {
        "property_type": "Single Family",
        "operation": "Sale",
        "address": "1245 Maple Ave",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78704",
        "currency": "USD",
        "price": 495000,
        "bedrooms": "3",
        "bathrooms": "2",
        "living_area_sqft": 1850,
        "lot_size_sqft": 6500,
        "garage_spaces": "2",
        "year_built": "2018",
        "hoa_fee": 0,
        "features": ["Hardwood floors", "Granite countertops", "Stainless appliances", "Updated kitchen", "Backyard", "Central A/C", "EV charger"],
    }

    agency = {
        "agency": os.getenv("AGENCY_NAME", "Ostrovich Enterprises"),
        "name": os.getenv("AGENT_NAME", "Agent"),
        "phone": os.getenv("AGENT_PHONE", ""),
        "email": os.getenv("AGENT_EMAIL", ""),
    }

    print("[2/5] Calling Gemini...")
    text = generate_listing_text(prop)
    print(f"  headline: {text['headline']}")
    print(f"  desc ({len(text['description'])} chars): {text['description'][:140]}...")
    print(f"  caption: {text['instagram_caption'][:140]}...")

    print("[3/5] PDF flyer...")
    pdf_path = out_dir / "flyer.pdf"
    build_pdf(prop, text, photos, str(pdf_path), agency)
    print(f"  -> {pdf_path} ({pdf_path.stat().st_size / 1024:.1f} KB)")

    print("[4/5] IG image...")
    ig_path = out_dir / "ig_post.jpg"
    contact = f"https://wa.me/{agency['phone'].replace('+','').replace(' ','').replace('-','')}"
    build_ig_post(photos[0], prop, text["headline"], agency, str(ig_path), contact)
    print(f"  -> {ig_path} ({ig_path.stat().st_size / 1024:.1f} KB)")

    print("[5/5] DONE.")


if __name__ == "__main__":
    main()
