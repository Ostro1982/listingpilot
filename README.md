# Inmo CABA — Generador de contenido

Sistema local que toma datos de propiedad CABA y genera:
- Ficha técnica PDF profesional
- Imagen cuadrada IG con QR a WhatsApp
- Caption + descripción AI
- Publicación directa a IG via Upload Post

Stack: Flask + OpenAI + Pillow + ReportLab + qrcode + Upload Post API.

## Setup

```bash
cd D:\temp\inmo_caba
pip install -r requirements.txt
cp .env.example .env
```

Editar `.env`:

```
OPENAI_API_KEY=sk-...                    # https://platform.openai.com (cargar mín $5)
UPLOAD_POST_API_KEY=                      # https://upload-post.com (gratis)
UPLOAD_POST_USER=                         # nombre usuario que conectaste a IG
AGENCY_NAME=Tu Inmobiliaria
AGENT_NAME=Diego
AGENT_PHONE=+5491100000000
AGENT_EMAIL=diego@example.com
```

## Correr

```bash
python app.py
```

Abrir http://localhost:5006

## Flujo

1. Llenar form (tipo, barrio, precio, ambientes, fotos)
2. Submit → Genera PDF + IG image (~10-20s con OpenAI)
3. Pantalla resultado: descargar PDF, ver IG image, copiar caption
4. Botón "Publicar a Instagram" → publica via Upload Post

## Costos

- OpenAI gpt-4o-mini: ~$0.001 por propiedad (descripción + caption)
- Upload Post: plan free incluye 25 publicaciones/mes
- Resto: $0 (corre local)

## Estructura

```
app.py                  # Flask routes
generators/
  openai_text.py        # GPT-4o-mini → JSON {descripcion, caption, headline}
  pdf_gen.py            # ReportLab ficha técnica A4
  ig_image.py           # Pillow 1080x1080 con QR + gradient overlay
  upload_post.py        # POST /api/upload_photos a Upload Post
templates/
  form.html             # Formulario carga datos + fotos
  result.html           # Preview + botones descarga/publish
static/
  uploads/              # Fotos subidas
  output/<job_id>/      # PDF + IG image generados
```

## Próximos pasos (v2)

- [ ] Carrusel IG (5-8 imágenes)
- [ ] Story IG vertical
- [ ] Email HTML para clientes
- [ ] Reel video con Remotion (requiere Node)
- [ ] Logo personalizable agencia
- [ ] Subir Argenprop/Zonaprop via API si existe

## Pitch B2B (oferta inmobiliarias)

- Setup inicial: $X (instalación + branding agencia)
- Mensual: $Y (mantenimiento + fixes + nuevas features)
- O: pago único + soporte por hora
- Ahorra ~3-5 hs por propiedad publicada
