"""Test PDF + IG image sin OpenAI (texto hardcoded)."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from generators.pdf_gen import build_pdf
from generators.ig_image import build_ig_post


def make_sample(path, label, color):
    img = Image.new("RGB", (1600, 1200), color)
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 80)
    except Exception:
        f = ImageFont.load_default()
    d.text((50, 50), label, fill=(255, 255, 255), font=f)
    img.save(path, "JPEG", quality=85)
    return str(path)


out = BASE / "static" / "output" / "no_ai"
out.mkdir(parents=True, exist_ok=True)
ph = BASE / "static" / "uploads"
ph.mkdir(parents=True, exist_ok=True)

photos = [
    make_sample(ph / "noai_fachada.jpg", "FACHADA", (60, 90, 130)),
    make_sample(ph / "noai_living.jpg", "LIVING", (140, 100, 80)),
    make_sample(ph / "noai_cocina.jpg", "COCINA", (90, 130, 100)),
]

prop = {
    "tipo": "Departamento", "operacion": "Venta", "barrio": "Palermo",
    "direccion": "Gorriti 5400", "moneda": "USD", "precio": 245000,
    "ambientes": "3", "banos": "2", "superficie_total": 85,
    "superficie_cubierta": 75, "cochera": "1", "antiguedad": "A estrenar",
    "amenidades": ["Pileta", "Gimnasio", "SUM", "Seguridad 24h", "Parrilla"],
}

text = {
    "descripcion": "Departamento de tres ambientes en Palermo, ubicado sobre Gorriti al 5400. Edificio a estrenar con pileta, gimnasio, SUM y seguridad las 24 horas. Superficie total de 85m² con 75m² cubiertos. Cuenta con dos baños y una cochera. Apto crédito hipotecario. Excelente conectividad con transporte público y a metros de zona gastronómica.",
    "instagram_caption": "3 ambientes a estrenar en Palermo. 85m² totales, cochera incluida, edificio con amenities completos. USD 245.000. Consultá por DM. #Palermo #DeptoVenta #Inmobiliaria #CABA #BuenosAires",
    "headline": "Departamento 3 amb. en Palermo",
}

agency = {"agency": "Inmo Demo", "name": "Diego", "phone": "+5491100000000", "email": "diego@example.com"}

build_pdf(prop, text, photos, str(out / "ficha.pdf"), agency)
build_ig_post(photos[0], prop, text["headline"], agency, str(out / "ig_post.jpg"), "https://wa.me/5491100000000")

print(f"PDF: {out / 'ficha.pdf'}")
print(f"IMG: {out / 'ig_post.jpg'}")
