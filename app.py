import os
import uuid
import json
import urllib.parse
import base64
import requests
from pathlib import Path
from datetime import datetime, timedelta

from flask import (
    Flask, render_template, request, redirect, url_for,
    send_from_directory, session, flash, jsonify, abort, Response
)
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

from generators.ai_text import generate_listing_text
from generators.pdf_gen import build_pdf
from generators.ig_image import build_ig_post
from generators import upload_post as up
from generators.upload_post import publish_photo
from db import init_db, Session, Listing, Agent, make_slug, make_api_key
from datetime import datetime as _dt
from bulk import parse_file, template_csv_bytes
from auth import (
    register_agent, authenticate, login_session, logout_session,
    current_agent, require_login, require_admin, require_api_key, auth_via_api_key,
)

load_dotenv()

BASE = Path(__file__).parent
UPLOADS = BASE / "static" / "uploads"
OUTPUT = BASE / "static" / "output"
LOGOS = BASE / "static" / "logos"
UPLOADS.mkdir(parents=True, exist_ok=True)
OUTPUT.mkdir(parents=True, exist_ok=True)
LOGOS.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "dev-secret-change-me")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
app.permanent_session_lifetime = timedelta(days=30)

init_db()


def _product():
    return {
        "name": os.getenv("PRODUCT_NAME", "ListingPilot"),
        "domain": os.getenv("PRODUCT_DOMAIN", "listingpilot.app"),
    }


def _public_base():
    return os.getenv("PUBLIC_BASE_URL", request.url_root.rstrip("/"))


def _agency_for(agent: Agent | None):
    if agent:
        return agent.public_branding()
    return {
        "agency": os.getenv("AGENCY_NAME", "Real Estate"),
        "name": os.getenv("AGENT_NAME", "Agent"),
        "phone": os.getenv("AGENT_PHONE", ""),
        "email": os.getenv("AGENT_EMAIL", ""),
        "logo_path": "",
        "primary_color": "#079992",
        "license_number": "",
    }


def _contact_url(branding, prop, listing_url=None):
    phone = (branding.get("phone") or "").replace("+", "").replace(" ", "").replace("-", "")
    msg = f"Hi, I'm interested in the property at {prop['address']}, {prop['city']}"
    if listing_url:
        msg += f" — {listing_url}"
    if phone:
        return f"https://wa.me/{phone}?text={urllib.parse.quote(msg)}"
    return f"mailto:{branding.get('email','')}?subject=Inquiry&body={urllib.parse.quote(msg)}"


def _save_photo_from_payload(item, prefix):
    if isinstance(item, str):
        if item.startswith("http://") or item.startswith("https://"):
            r = requests.get(item, timeout=30)
            r.raise_for_status()
            ext = ".jpg"
            ct = r.headers.get("content-type", "")
            if "png" in ct: ext = ".png"
            elif "webp" in ct: ext = ".webp"
            name = f"{prefix}_{uuid.uuid4().hex[:8]}{ext}"
            p = UPLOADS / name
            p.write_bytes(r.content)
            return str(p)
        if item.startswith("data:"):
            header, b64 = item.split(",", 1)
            ext = ".jpg"
            if "png" in header: ext = ".png"
            data = base64.b64decode(b64)
            name = f"{prefix}_{uuid.uuid4().hex[:8]}{ext}"
            p = UPLOADS / name
            p.write_bytes(data)
            return str(p)
    return None


def _build_listing(prop, photos, *, agent: Agent, publish=False):
    listing_id = uuid.uuid4().hex[:12]

    with Session() as s:
        agent_db = s.query(Agent).filter_by(id=agent.id).first()
        if agent_db.credits_remaining <= 0:
            raise RuntimeError("No credits remaining")

        slug = make_slug(prop, s)
        listing = Listing(id=listing_id, slug=slug, agent_id=agent_db.id)
        listing.property_type = prop["property_type"]; listing.operation = prop["operation"]
        listing.address = prop["address"]; listing.city = prop["city"]
        listing.state = prop["state"]; listing.zip_code = prop["zip_code"]
        listing.price = int(prop["price"]); listing.currency = prop.get("currency", "USD")
        listing.bedrooms = str(prop["bedrooms"]); listing.bathrooms = str(prop["bathrooms"])
        listing.living_area_sqft = int(prop["living_area_sqft"])
        listing.lot_size_sqft = int(prop.get("lot_size_sqft") or 0) or None
        listing.garage_spaces = str(prop.get("garage_spaces", "None"))
        listing.year_built = str(prop.get("year_built", "-"))
        listing.hoa_fee = float(prop.get("hoa_fee") or 0)
        listing.features = prop.get("features", [])
        listing.photos = photos

        text = generate_listing_text(prop)
        listing.description = text["description"]
        listing.instagram_caption = text["instagram_caption"]
        listing.headline = text["headline"]

        job_dir = OUTPUT / listing_id
        job_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = job_dir / "flyer.pdf"
        ig_path = job_dir / "ig_post.jpg"
        public_url = f"{_public_base()}/l/{slug}"
        branding = agent_db.public_branding()
        build_pdf(prop, text, photos, str(pdf_path), branding)
        build_ig_post(photos[0], prop, text["headline"], branding, str(ig_path), _contact_url(branding, prop, public_url))
        listing.pdf_path = str(pdf_path)
        listing.ig_image_path = str(ig_path)

        if publish:
            platforms = agent_db.connected_platforms
            if not platforms or not agent_db.upload_post_username:
                listing.publish_results = {"ok": False, "error": "Connect your social accounts in Settings before auto-publishing."}
            else:
                caption_with_link = f"{text['instagram_caption']}\n\nFull details: {public_url}"
                res = publish_photo(str(ig_path), caption_with_link, platforms, username=agent_db.upload_post_username)
                listing.publish_results = res
                listing.is_published = bool(res.get("ok"))

        agent_db.credits_remaining -= 1

        s.add(listing)
        s.commit()

        return {
            "id": listing.id,
            "slug": listing.slug,
            "public_url": public_url,
            "pdf_url": f"{_public_base()}/files/{listing.id}/flyer.pdf",
            "ig_image_url": f"{_public_base()}/files/{listing.id}/ig_post.jpg",
            "headline": listing.headline,
            "description": listing.description,
            "instagram_caption": listing.instagram_caption,
            "publish_results": listing.publish_results if publish else None,
            "credits_remaining": agent_db.credits_remaining,
        }


def _publish_listing_for_agent(listing, agent: Agent) -> dict:
    """Publish a listing to the agent's connected social platforms."""
    if not agent or not agent.upload_post_username:
        return {"ok": False, "error": "Agent has no social profile. Go to Settings → Connect social accounts."}
    platforms = agent.connected_platforms
    if not platforms:
        return {"ok": False, "error": "No social accounts connected. Go to Settings → Connect social accounts."}
    public_url = f"{_public_base()}/l/{listing.slug}"
    caption = f"{listing.instagram_caption}\n\nFull details: {public_url}"
    return publish_photo(listing.ig_image_path, caption, platforms, username=agent.upload_post_username)


def _regen_assets_for_agent(listing, agent: Agent):
    job_dir = OUTPUT / listing.id
    job_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = job_dir / "flyer.pdf"
    ig_path = job_dir / "ig_post.jpg"
    public_url = f"{_public_base()}/l/{listing.slug}"
    prop = listing.to_prop_dict()
    text = listing.to_text_dict()
    branding = agent.public_branding() if agent else _agency_for(None)
    build_pdf(prop, text, listing.photos, str(pdf_path), branding)
    build_ig_post(listing.photos[0], prop, text["headline"], branding, str(ig_path), _contact_url(branding, prop, public_url))
    listing.pdf_path = str(pdf_path)
    listing.ig_image_path = str(ig_path)


# ============================================================
# AUTH
# ============================================================

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        try:
            agent = register_agent(
                email=request.form["email"],
                password=request.form["password"],
                full_name=request.form.get("full_name", ""),
                brokerage=request.form.get("brokerage", ""),
            )
            login_session(agent)
            return redirect(url_for("dashboard"))
        except ValueError as e:
            flash(str(e))
            return redirect(url_for("signup"))
    return render_template("auth_signup.html", product=_product())


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        agent = authenticate(request.form["email"], request.form["password"])
        if agent:
            login_session(agent)
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Invalid email or password.")
        return redirect(url_for("login"))
    return render_template("auth_login.html", product=_product())


@app.route("/logout")
def logout():
    logout_session()
    return redirect(url_for("login"))


# ============================================================
# DASHBOARD + SETTINGS
# ============================================================

@app.route("/dashboard")
@require_login
def dashboard():
    agent = current_agent()
    with Session() as s:
        listings = s.query(Listing).filter_by(agent_id=agent.id).order_by(Listing.created_at.desc()).all()
        stats = {
            "total": len(listings),
            "published": sum(1 for l in listings if l.is_published),
        }
    return render_template("dashboard.html", agent=agent, listings=listings, stats=stats, product=_product())


@app.route("/settings", methods=["GET", "POST"])
@require_login
def settings_page():
    agent = current_agent()
    if request.method == "POST":
        with Session() as s:
            ag = s.query(Agent).filter_by(id=agent.id).first()
            ag.full_name = request.form.get("full_name", "").strip()
            ag.brokerage = request.form.get("brokerage", "").strip()
            ag.phone = request.form.get("phone", "").strip()
            ag.license_number = request.form.get("license_number", "").strip()
            ag.primary_color = request.form.get("primary_color", "#079992")

            logo_file = request.files.get("logo")
            if logo_file and logo_file.filename:
                ext = Path(logo_file.filename).suffix.lower()
                if ext not in {".png", ".jpg", ".jpeg"}:
                    flash("Logo must be PNG or JPG.")
                    return redirect(url_for("settings_page"))
                logo_name = f"{ag.id}_logo{ext}"
                logo_path = LOGOS / logo_name
                logo_file.save(logo_path)
                ag.logo_path = str(logo_path)

            s.commit()
        flash("Settings saved.")
        return redirect(url_for("settings_page"))

    logo_rel = ""
    if agent.logo_path:
        try:
            logo_rel = os.path.relpath(agent.logo_path, BASE / "static").replace("\\", "/")
        except Exception:
            logo_rel = ""
    return render_template("settings.html", agent=agent, product=_product(), logo_rel=logo_rel)


@app.route("/bulk", methods=["GET", "POST"])
@require_login
def bulk_import():
    agent = current_agent()
    if request.method == "GET":
        return render_template("bulk.html", agent=agent, product=_product())

    f = request.files.get("file")
    if not f or not f.filename:
        flash("Choose a CSV or Excel file.")
        return redirect(url_for("bulk_import"))

    auto_publish = request.form.get("auto_publish") == "on"

    try:
        rows = parse_file(f.filename, f.stream)
    except Exception as e:
        flash(f"Could not read file: {e}")
        return redirect(url_for("bulk_import"))

    results = []
    errors = []
    created = 0

    for prop, photos_or_err in rows:
        if prop is None:
            errors.append(photos_or_err[0] if photos_or_err else "unknown error")
            continue
        if not photos_or_err:
            errors.append(f"{prop.get('address','?')}: at least one photo URL required")
            continue

        with Session() as s:
            ag = s.query(Agent).filter_by(id=agent.id).first()
            if ag.credits_remaining <= 0:
                errors.append(f"{prop.get('address','?')}: out of credits")
                break

        downloaded = []
        try:
            for i, url in enumerate(photos_or_err):
                saved = _save_photo_from_payload(url, f"bulk_{uuid.uuid4().hex[:6]}_{i}")
                if saved:
                    downloaded.append(saved)
            if not downloaded:
                errors.append(f"{prop.get('address','?')}: could not download any photos")
                continue

            res = _build_listing(prop, downloaded, agent=agent, publish=auto_publish)
            results.append({
                "address": f"{prop['address']}, {prop['city']}, {prop['state']}",
                "url": res["public_url"],
            })
            created += 1
        except Exception as e:
            errors.append(f"{prop.get('address','?')}: {e}")

    return render_template("bulk_result.html", results=results, errors=errors, created=created, agent=agent, product=_product())


@app.route("/bulk/template.csv")
@require_login
def bulk_template():
    return Response(
        template_csv_bytes(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=listingpilot_template.csv"},
    )


@app.route("/api-docs")
@require_login
def api_docs():
    agent = current_agent()
    platforms = os.getenv("SOCIAL_PLATFORMS", "facebook")
    return render_template("api_docs.html", agent=agent, product=_product(), public_base=_public_base(), social_platforms=platforms)


@app.route("/dashboard/publish/<listing_id>", methods=["POST"])
@require_login
def dashboard_publish(listing_id):
    agent = current_agent()
    with Session() as s:
        listing = s.query(Listing).filter_by(id=listing_id).first()
        if not listing:
            return jsonify({"error": "not found"}), 404
        if listing.agent_id != agent.id and not agent.is_admin:
            return jsonify({"error": "forbidden"}), 403
        owner = s.query(Agent).filter_by(id=listing.agent_id).first()
        res = _publish_listing_for_agent(listing, owner)
        listing.publish_results = res
        listing.is_published = bool(res.get("ok"))
        s.commit()
        return jsonify(res)


@app.route("/settings/connect-social", methods=["POST"])
@require_login
def connect_social():
    agent = current_agent()
    if not agent.upload_post_username:
        with Session() as s:
            ag = s.query(Agent).filter_by(id=agent.id).first()
            from auth import _safe_username
            ag.upload_post_username = _safe_username(ag.email)
            s.commit()
            agent = ag

    create_res = up.create_user(agent.upload_post_username)

    redirect_url = f"{_public_base()}/settings/connections-callback"
    res = up.generate_jwt(
        username=agent.upload_post_username,
        redirect_url=redirect_url,
        title=f"Connect your social accounts to {_product()['name']}",
    )
    if not res.get("ok"):
        return jsonify({
            "error": "Could not generate connection link",
            "details": res.get("body"),
            "create_user_result": create_res,
            "username": agent.upload_post_username,
        }), 500

    body = res.get("body") or {}
    url = body.get("access_url") or body.get("url") or body.get("jwt_url")
    if not url:
        return jsonify({"error": "No URL returned", "details": body}), 500

    return jsonify({"ok": True, "url": url})


@app.route("/settings/connections-callback")
@require_login
def connections_callback():
    agent = current_agent()
    if agent.upload_post_username:
        platforms = up.get_connected_platforms(agent.upload_post_username)
        with Session() as s:
            ag = s.query(Agent).filter_by(id=agent.id).first()
            ag.connected_platforms = platforms
            ag.last_connection_check = _dt.utcnow()
            s.commit()
    flash("Social accounts updated.")
    return redirect(url_for("settings_page"))


@app.route("/settings/refresh-connections", methods=["POST"])
@require_login
def refresh_connections():
    agent = current_agent()
    if not agent.upload_post_username:
        return jsonify({"error": "no profile"}), 400
    platforms = up.get_connected_platforms(agent.upload_post_username)
    with Session() as s:
        ag = s.query(Agent).filter_by(id=agent.id).first()
        ag.connected_platforms = platforms
        ag.last_connection_check = _dt.utcnow()
        s.commit()
    return jsonify({"ok": True, "connected_platforms": platforms})


@app.route("/settings/regen-api-key", methods=["POST"])
@require_login
def regen_api_key():
    agent = current_agent()
    with Session() as s:
        ag = s.query(Agent).filter_by(id=agent.id).first()
        ag.api_key = make_api_key()
        s.commit()
    flash("New API key generated. Old key disabled.")
    return redirect(url_for("settings_page") + "#api")


# ============================================================
# LISTING CREATE/EDIT (UI - requires login)
# ============================================================

@app.route("/")
def home():
    if current_agent():
        return render_template("form.html", product=_product(), agency=_agency_for(current_agent()))
    return redirect(url_for("login"))


@app.route("/generate", methods=["POST"])
@require_login
def generate():
    agent = current_agent()
    if agent.credits_remaining <= 0:
        flash("No credits remaining. Upgrade your plan.")
        return redirect(url_for("dashboard"))

    features = request.form.getlist("features")
    prop = {
        "property_type": request.form["property_type"],
        "operation": request.form["operation"],
        "address": request.form["address"],
        "city": request.form["city"],
        "state": request.form["state"],
        "zip_code": request.form["zip_code"],
        "currency": "USD",
        "price": int(request.form["price"]),
        "bedrooms": request.form["bedrooms"],
        "bathrooms": request.form["bathrooms"],
        "living_area_sqft": int(request.form["living_area_sqft"]),
        "lot_size_sqft": int(request.form.get("lot_size_sqft") or 0) or None,
        "garage_spaces": request.form.get("garage_spaces", "None"),
        "year_built": request.form.get("year_built", "-"),
        "hoa_fee": float(request.form.get("hoa_fee") or 0),
        "features": features,
    }

    photos = []
    for f in request.files.getlist("photos"):
        if f.filename:
            name = f"{uuid.uuid4().hex[:8]}_{secure_filename(f.filename)}"
            p = UPLOADS / name
            f.save(p)
            photos.append(str(p))

    if not photos:
        flash("Upload at least one photo.")
        return redirect(url_for("home"))

    publish = request.form.get("publish") == "on"
    result = _build_listing(prop, photos, agent=agent, publish=publish)
    return redirect(url_for("listing_public", slug=result["slug"]))


@app.route("/edit/<slug>", methods=["GET", "POST"])
@require_login
def edit_listing(slug):
    agent = current_agent()
    with Session() as s:
        listing = s.query(Listing).filter_by(slug=slug).first()
        if not listing:
            abort(404)
        if listing.agent_id != agent.id and not agent.is_admin:
            abort(403)

        if request.method == "GET":
            photos_rel = [os.path.relpath(p, BASE / "static").replace("\\", "/") for p in listing.photos]
            return render_template("edit.html", listing=listing, photos_rel=photos_rel, product=_product())

        listing.property_type = request.form["property_type"]
        listing.operation = request.form["operation"]
        listing.address = request.form["address"]
        listing.city = request.form["city"]
        listing.state = request.form["state"]
        listing.zip_code = request.form["zip_code"]
        listing.price = int(request.form["price"])
        listing.bedrooms = request.form["bedrooms"]
        listing.bathrooms = request.form["bathrooms"]
        listing.living_area_sqft = int(request.form["living_area_sqft"])
        listing.lot_size_sqft = int(request.form.get("lot_size_sqft") or 0) or None
        listing.garage_spaces = request.form.get("garage_spaces", "None")
        listing.year_built = request.form.get("year_built", "-")
        listing.hoa_fee = float(request.form.get("hoa_fee") or 0)
        listing.features = request.form.getlist("features")

        listing.headline = request.form.get("headline", listing.headline)
        listing.description = request.form.get("description", listing.description)
        listing.instagram_caption = request.form.get("instagram_caption", listing.instagram_caption)

        remove_idx = set(int(i) for i in request.form.getlist("remove_photos"))
        existing = listing.photos
        new_existing = [p for i, p in enumerate(existing) if i not in remove_idx]

        for f in request.files.getlist("new_photos"):
            if f.filename:
                name = f"{uuid.uuid4().hex[:8]}_{secure_filename(f.filename)}"
                p = UPLOADS / name
                f.save(p)
                new_existing.append(str(p))

        if not new_existing:
            flash("Cannot remove all photos. Keep at least one.")
            return redirect(url_for("edit_listing", slug=slug))

        listing.photos = new_existing

        if request.form.get("regenerate_text"):
            text = generate_listing_text(listing.to_prop_dict())
            listing.headline = text["headline"]
            listing.description = text["description"]
            listing.instagram_caption = text["instagram_caption"]

        if request.form.get("regenerate_assets"):
            _regen_assets_for_agent(listing, listing.agent)

        if request.form.get("republish"):
            owner = s.query(Agent).filter_by(id=listing.agent_id).first()
            res = _publish_listing_for_agent(listing, owner)
            listing.publish_results = res
            listing.is_published = bool(res.get("ok"))

        s.commit()
        return redirect(url_for("listing_public", slug=listing.slug))


# ============================================================
# PUBLIC
# ============================================================

@app.route("/l/<slug>")
def listing_public(slug):
    with Session() as s:
        listing = s.query(Listing).filter_by(slug=slug).first()
        if not listing:
            abort(404)
        photos_rel = [os.path.relpath(p, BASE / "static").replace("\\", "/") for p in listing.photos]
        ig_rel = os.path.relpath(listing.ig_image_path, BASE / "static").replace("\\", "/") if listing.ig_image_path else ""
        pdf_rel = os.path.relpath(listing.pdf_path, BASE / "static").replace("\\", "/") if listing.pdf_path else ""
        public_url = f"{_public_base()}/l/{slug}"
        agency = listing.agent.public_branding() if listing.agent else _agency_for(None)
        logo_rel = ""
        if agency.get("logo_path"):
            try:
                logo_rel = os.path.relpath(agency["logo_path"], BASE / "static").replace("\\", "/")
            except Exception:
                logo_rel = ""
        contact = _contact_url(agency, listing.to_prop_dict(), public_url)
        return render_template(
            "listing.html",
            listing=listing, agency=agency, product=_product(),
            photos_rel=photos_rel, ig_rel=ig_rel, pdf_rel=pdf_rel, logo_rel=logo_rel,
            public_url=public_url, contact_url=contact,
        )


@app.route("/files/<listing_id>/<filename>")
def listing_file(listing_id, filename):
    return send_from_directory(OUTPUT / listing_id, filename, as_attachment=False)


# ============================================================
# API (per-agent api_key)
# ============================================================

@app.route("/api/listings", methods=["POST"])
@require_api_key
def api_create_listing():
    agent = request.agent

    if request.is_json:
        data = request.get_json()
        prop = data["property"]
        photos = []
        for i, item in enumerate(data.get("photos", [])):
            saved = _save_photo_from_payload(item, f"api_{i}")
            if saved:
                photos.append(saved)
        publish = data.get("auto_publish", False)
    else:
        prop = json.loads(request.form["property"])
        photos = []
        for f in request.files.getlist("photos"):
            if f.filename:
                name = f"api_{uuid.uuid4().hex[:8]}_{secure_filename(f.filename)}"
                p = UPLOADS / name
                f.save(p)
                photos.append(str(p))
        publish = request.form.get("auto_publish", "false").lower() == "true"

    if not photos:
        return jsonify({"error": "no photos"}), 400

    try:
        result = _build_listing(prop, photos, agent=agent, publish=publish)
        return jsonify({"ok": True, **result}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/listings/<listing_id>", methods=["PATCH", "PUT"])
@require_api_key
def api_update_listing(listing_id):
    agent = request.agent
    data = request.get_json() or {}
    with Session() as s:
        listing = s.query(Listing).filter_by(id=listing_id).first()
        if not listing:
            return jsonify({"error": "not found"}), 404
        if listing.agent_id != agent.id and not agent.is_admin:
            return jsonify({"error": "forbidden"}), 403

        editable = ["property_type", "operation", "address", "city", "state", "zip_code",
                    "price", "currency", "bedrooms", "bathrooms", "living_area_sqft",
                    "lot_size_sqft", "garage_spaces", "year_built", "hoa_fee"]
        if "property" in data:
            for k, v in data["property"].items():
                if k in editable:
                    setattr(listing, k, v)
            if "features" in data["property"]:
                listing.features = data["property"]["features"]
        for k in ["headline", "description", "instagram_caption"]:
            if k in data:
                setattr(listing, k, data[k])

        if "photos_add" in data:
            new_photos = list(listing.photos)
            for i, item in enumerate(data["photos_add"]):
                saved = _save_photo_from_payload(item, f"api_edit_{i}")
                if saved:
                    new_photos.append(saved)
            listing.photos = new_photos

        if "photos_remove_indexes" in data:
            remove = set(int(i) for i in data["photos_remove_indexes"])
            listing.photos = [p for i, p in enumerate(listing.photos) if i not in remove]
            if not listing.photos:
                return jsonify({"error": "cannot remove all photos"}), 400

        if data.get("regenerate_text"):
            text = generate_listing_text(listing.to_prop_dict())
            listing.headline = text["headline"]
            listing.description = text["description"]
            listing.instagram_caption = text["instagram_caption"]

        if data.get("regenerate_assets", True):
            _regen_assets_for_agent(listing, listing.agent)

        if data.get("republish"):
            owner = s.query(Agent).filter_by(id=listing.agent_id).first()
            res = _publish_listing_for_agent(listing, owner)
            listing.publish_results = res
            listing.is_published = bool(res.get("ok"))

        s.commit()
        return jsonify({
            "ok": True,
            "id": listing.id,
            "slug": listing.slug,
            "public_url": f"{_public_base()}/l/{listing.slug}",
            "pdf_url": f"{_public_base()}/files/{listing.id}/flyer.pdf",
            "ig_image_url": f"{_public_base()}/files/{listing.id}/ig_post.jpg",
            "headline": listing.headline,
            "description": listing.description,
            "instagram_caption": listing.instagram_caption,
        })


@app.route("/api/listings/<listing_id>", methods=["DELETE"])
@require_api_key
def api_delete_listing(listing_id):
    agent = request.agent
    with Session() as s:
        listing = s.query(Listing).filter_by(id=listing_id).first()
        if not listing:
            return jsonify({"error": "not found"}), 404
        if listing.agent_id != agent.id and not agent.is_admin:
            return jsonify({"error": "forbidden"}), 403
        s.delete(listing)
        s.commit()
        return jsonify({"ok": True})


@app.route("/api/listings/<listing_id>", methods=["GET"])
@require_api_key
def api_get_listing(listing_id):
    agent = request.agent
    with Session() as s:
        listing = s.query(Listing).filter_by(id=listing_id).first()
        if not listing:
            return jsonify({"error": "not found"}), 404
        if listing.agent_id != agent.id and not agent.is_admin:
            return jsonify({"error": "forbidden"}), 403
        return jsonify({
            "id": listing.id, "slug": listing.slug,
            "public_url": f"{_public_base()}/l/{listing.slug}",
            "property": listing.to_prop_dict(),
            "headline": listing.headline,
            "description": listing.description,
            "instagram_caption": listing.instagram_caption,
            "photos_count": len(listing.photos),
            "is_published": listing.is_published,
            "created_at": listing.created_at.isoformat(),
        })


@app.route("/api/listings", methods=["GET"])
@require_api_key
def api_list_listings():
    agent = request.agent
    with Session() as s:
        listings = s.query(Listing).filter_by(agent_id=agent.id).order_by(Listing.created_at.desc()).all()
        return jsonify({
            "ok": True,
            "count": len(listings),
            "credits_remaining": agent.credits_remaining,
            "listings": [{
                "id": l.id, "slug": l.slug,
                "public_url": f"{_public_base()}/l/{l.slug}",
                "city": l.city, "state": l.state,
                "price": l.price, "is_published": l.is_published,
                "created_at": l.created_at.isoformat(),
            } for l in listings],
        })


@app.route("/api/me", methods=["GET"])
@require_api_key
def api_me():
    a = request.agent
    return jsonify({
        "ok": True,
        "id": a.id, "email": a.email, "full_name": a.full_name, "brokerage": a.brokerage,
        "plan": a.plan, "credits_remaining": a.credits_remaining,
    })


# ============================================================
# ADMIN (only admin agents)
# ============================================================

@app.route("/admin")
@require_login
@require_admin
def admin():
    with Session() as s:
        listings = s.query(Listing).order_by(Listing.created_at.desc()).all()
        agents = s.query(Agent).order_by(Agent.created_at.desc()).all()
        return render_template("admin.html", listings=listings, agents=agents, product=_product())


@app.route("/admin/<listing_id>/publish", methods=["POST"])
@require_login
@require_admin
def admin_publish(listing_id):
    with Session() as s:
        listing = s.query(Listing).filter_by(id=listing_id).first()
        if not listing:
            return jsonify({"error": "not found"}), 404
        owner = s.query(Agent).filter_by(id=listing.agent_id).first()
        res = _publish_listing_for_agent(listing, owner)
        listing.publish_results = res
        listing.is_published = bool(res.get("ok"))
        s.commit()
        return jsonify(res)


# ============================================================
# SEO
# ============================================================

@app.route("/sitemap.xml")
def sitemap():
    with Session() as s:
        listings = s.query(Listing).order_by(Listing.created_at.desc()).all()
        urls = [f"{_public_base()}/l/{l.slug}" for l in listings]
    xml_items = "".join(
        f"<url><loc>{u}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>"
        for u in urls
    )
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{xml_items}</urlset>'
    return Response(xml, mimetype="application/xml")


@app.route("/robots.txt")
def robots():
    base = _public_base()
    return Response(f"User-agent: *\nAllow: /l/\nDisallow: /admin\nDisallow: /dashboard\nDisallow: /settings\nDisallow: /edit\nSitemap: {base}/sitemap.xml\n", mimetype="text/plain")


if __name__ == "__main__":
    app.run(debug=True, port=5006, host="0.0.0.0")
