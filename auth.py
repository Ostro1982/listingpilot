"""Auth helpers: register, login, session, decorators."""
import re
import uuid
from functools import wraps

from flask import session, redirect, url_for, request, jsonify, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

from db import Session, Agent, make_api_key
from generators import upload_post as up


def _safe_username(email: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "_", email.split("@")[0])[:20] or "user"
    return f"{base}_{uuid.uuid4().hex[:6]}"


def register_agent(email: str, password: str, full_name: str = "", brokerage: str = "") -> Agent:
    email = email.strip().lower()
    if not email or len(password) < 8:
        raise ValueError("Email and password (min 8 chars) required")

    with Session() as s:
        if s.query(Agent).filter_by(email=email).first():
            raise ValueError("Email already registered")

        up_username = _safe_username(email)
        try:
            up.create_user(up_username)
        except Exception:
            pass

        agent = Agent(
            id=uuid.uuid4().hex[:12],
            email=email,
            password_hash=generate_password_hash(password),
            full_name=full_name.strip(),
            brokerage=brokerage.strip(),
            api_key=make_api_key(),
            credits_remaining=1,
            plan="trial",
            upload_post_username=up_username,
        )
        s.add(agent)
        s.commit()
        s.refresh(agent)
        return agent


def authenticate(email: str, password: str):
    email = email.strip().lower()
    with Session() as s:
        agent = s.query(Agent).filter_by(email=email).first()
        if not agent or not check_password_hash(agent.password_hash, password):
            return None
        return agent


def login_session(agent: Agent):
    session["agent_id"] = agent.id
    session.permanent = True


def logout_session():
    session.pop("agent_id", None)


def current_agent():
    aid = session.get("agent_id")
    if not aid:
        return None
    with Session() as s:
        return s.query(Agent).filter_by(id=aid).first()


def require_login(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("agent_id"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("login", next=request.path))
        return fn(*a, **kw)
    return wrapper


def require_admin(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        agent = current_agent()
        if not agent or not agent.is_admin:
            abort(403)
        return fn(*a, **kw)
    return wrapper


def auth_via_api_key():
    """Resolve agent from Authorization: Bearer <api_key>. Returns Agent or None."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    key = auth[7:].strip()
    if not key:
        return None
    with Session() as s:
        return s.query(Agent).filter_by(api_key=key).first()


def require_api_key(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        agent = auth_via_api_key()
        if not agent:
            return jsonify({"error": "invalid api key"}), 401
        request.agent = agent
        return fn(*a, **kw)
    return wrapper
