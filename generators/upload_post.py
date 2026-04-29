import os
import requests

API_BASE = "https://api.upload-post.com/api"


def _headers():
    api_key = os.getenv("UPLOAD_POST_API_KEY")
    if not api_key:
        raise RuntimeError("UPLOAD_POST_API_KEY not set")
    return {"Authorization": f"Apikey {api_key}"}


def create_user(username: str) -> dict:
    """Create a new Upload Post profile."""
    r = requests.post(f"{API_BASE}/uploadposts/users",
                      headers=_headers(),
                      json={"username": username},
                      timeout=30)
    try:
        body = r.json()
    except Exception:
        body = r.text
    return {"ok": r.ok, "status": r.status_code, "body": body}


def list_users() -> dict:
    r = requests.get(f"{API_BASE}/uploadposts/users", headers=_headers(), timeout=30)
    try:
        return r.json()
    except Exception:
        return {"success": False, "error": r.text}


def get_user(username: str) -> dict:
    r = requests.get(f"{API_BASE}/uploadposts/users/{username}", headers=_headers(), timeout=30)
    try:
        return r.json()
    except Exception:
        return {"success": False, "error": r.text}


def generate_jwt(username: str, redirect_url: str = "", logo_url: str = "", title: str = "Connect your social accounts") -> dict:
    """Generate single-use JWT URL for user to connect their socials. Valid 48h."""
    payload = {"username": username}
    if redirect_url:
        payload["redirect_url"] = redirect_url
    if logo_url:
        payload["logo_url"] = logo_url
    if title:
        payload["title"] = title

    r = requests.post(f"{API_BASE}/uploadposts/users/generate-jwt",
                      headers=_headers(),
                      json=payload,
                      timeout=30)
    try:
        return {"ok": r.ok, "status": r.status_code, "body": r.json()}
    except Exception:
        return {"ok": r.ok, "status": r.status_code, "body": r.text}


def get_connected_platforms(username: str) -> list[str]:
    """Return list of connected platform names for a username."""
    data = get_user(username)
    if not data.get("success"):
        return []
    profiles = data.get("profiles", [])
    if not profiles:
        return []
    accounts = profiles[0].get("social_accounts", {})
    connected = []
    for platform, info in accounts.items():
        if isinstance(info, dict) and info.get("handle"):
            connected.append(platform)
        elif isinstance(info, str) and info.strip():
            connected.append(platform)
    return connected


def publish_photo(image_path: str, caption: str, platforms: list, username: str = None) -> dict:
    """Publish photo to specified platforms for a given upload-post user."""
    user = username or os.getenv("UPLOAD_POST_USER")
    if not user:
        return {"ok": False, "error": "No upload-post user provided"}
    if not platforms:
        return {"ok": False, "error": "no platforms"}

    url = f"{API_BASE}/upload_photos"
    with open(image_path, "rb") as f:
        files = [("photos[]", (os.path.basename(image_path), f, "image/jpeg"))]
        data = [("user", user), ("caption", caption)]
        for p in platforms:
            data.append(("platform[]", p))
        r = requests.post(url, headers=_headers(), data=data, files=files, timeout=120)
    try:
        body = r.json()
    except Exception:
        body = r.text
    return {"ok": r.ok, "status": r.status_code, "body": body, "platforms": platforms}


def publish_to_instagram(image_path: str, caption: str, username: str = None) -> dict:
    return publish_photo(image_path, caption, ["instagram"], username)
