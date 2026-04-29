import os
from PIL import Image, ImageDraw, ImageFont
import qrcode

W, H = 1080, 1080
DEFAULT_ACCENT = (7, 153, 146)
WHITE = (255, 255, 255)


def _hex_to_rgb(h: str):
    h = (h or "").lstrip("#")
    if len(h) == 6:
        try:
            return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    return DEFAULT_ACCENT


def _font(size, bold=False):
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def _gradient_overlay(img: Image.Image) -> Image.Image:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for y in range(img.size[1]):
        alpha = int(220 * (y / img.size[1]) ** 1.4)
        d.line([(0, y), (img.size[0], y)], fill=(0, 0, 0, alpha))
    return Image.alpha_composite(img.convert("RGBA"), overlay)


def build_ig_post(cover_photo: str, prop: dict, headline: str, agency: dict, out_path: str, contact_url: str) -> str:
    accent = _hex_to_rgb(agency.get("primary_color", "#079992"))
    logo_path = agency.get("logo_path", "")

    base = Image.open(cover_photo).convert("RGBA")
    base = base.resize((W, H), Image.LANCZOS)
    base = _gradient_overlay(base)

    d = ImageDraw.Draw(base)

    badge_text = f"FOR {prop['operation'].upper()}" if prop['operation'].lower() in ('sale', 'rent') else prop['operation'].upper()
    f_badge = _font(28, bold=True)
    bbox = d.textbbox((0, 0), badge_text, font=f_badge)
    pad_x, pad_y = 18, 10
    bw = bbox[2] - bbox[0] + pad_x * 2
    bh = bbox[3] - bbox[1] + pad_y * 2
    d.rounded_rectangle([(40, 40), (40 + bw, 40 + bh)], radius=6, fill=accent)
    d.text((40 + pad_x, 40 + pad_y - 2), badge_text, fill=WHITE, font=f_badge)

    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((150, 150), Image.LANCZOS)
            base.paste(logo, (W - logo.width - 40, 40), logo)
        except Exception:
            pass

    f_brand = _font(22, bold=True)
    d.text((40, 110), agency['agency'], fill=WHITE, font=f_brand)

    f_price = _font(78, bold=True)
    price_str = f"${prop['price']:,}"
    d.text((40, H - 380), price_str, fill=WHITE, font=f_price)

    f_loc = _font(36)
    d.text((40, H - 280), f"{prop['city']}, {prop['state']}", fill=WHITE, font=f_loc)

    f_head = _font(28)
    d.text((40, H - 225), headline, fill=(220, 230, 240), font=f_head)

    f_specs = _font(32, bold=True)
    specs = f"{prop['bedrooms']} bd  •  {prop['bathrooms']} ba  •  {prop['living_area_sqft']:,} sqft"
    if prop.get('garage_spaces') and str(prop['garage_spaces']) not in ('0', 'No', 'None'):
        specs += f"  •  Garage: {prop['garage_spaces']}"
    d.text((40, H - 140), specs, fill=WHITE, font=f_specs)

    qr = qrcode.QRCode(box_size=4, border=1)
    qr.add_data(contact_url)
    qr.make()
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
    qr_img = qr_img.resize((140, 140), Image.NEAREST)
    base.paste(qr_img, (W - 180, H - 180), qr_img)

    base.convert("RGB").save(out_path, "JPEG", quality=92)
    return out_path
