import os
from openai import OpenAI

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


def generate_listing_text(prop: dict) -> dict:
    prompt = f"""Generá copy profesional en español rioplatense (Argentina) para esta propiedad.

Datos:
- Tipo: {prop['tipo']}
- Operación: {prop['operacion']}
- Barrio: {prop['barrio']}, CABA
- Dirección: {prop['direccion']}
- Precio: {prop['moneda']} {prop['precio']}
- Ambientes: {prop['ambientes']}
- Baños: {prop['banos']}
- Superficie: {prop['superficie_total']}m² ({prop['superficie_cubierta']}m² cubiertos)
- Cochera: {prop['cochera']}
- Amenidades: {', '.join(prop.get('amenidades', []))}

Devolvé JSON exacto con tres campos:
- "descripcion": 80-120 palabras, profesional, sin clichés ("oasis", "santuario", "soñado").
- "instagram_caption": 30-60 palabras + 5-8 hashtags relevantes CABA.
- "headline": frase corta 6-10 palabras para gráficas.

Tono: directo, factual, sin drama. Nada de bold statements ni "no te lo podés perder".
Respondé solo el JSON, sin markdown."""

    resp = _get_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.7,
    )
    import json
    return json.loads(resp.choices[0].message.content)
