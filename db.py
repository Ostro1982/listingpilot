import json
import secrets
import uuid
from datetime import datetime
from pathlib import Path

from slugify import slugify
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

BASE = Path(__file__).parent
DB_PATH = BASE / "inmo.db"
engine = create_engine(f"sqlite:///{DB_PATH}", future=True)
Session = sessionmaker(bind=engine, autoflush=False, future=True)
Base = declarative_base()


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_admin = Column(Boolean, default=False)

    full_name = Column(String, default="")
    brokerage = Column(String, default="")
    phone = Column(String, default="")
    license_number = Column(String, default="")
    logo_path = Column(String, default="")
    primary_color = Column(String, default="#079992")

    plan = Column(String, default="trial")
    credits_remaining = Column(Integer, default=1)
    stripe_customer_id = Column(String, default="")

    api_key = Column(String, default="")

    upload_post_username = Column(String, default="")
    connected_platforms_json = Column(Text, default="[]")
    last_connection_check = Column(DateTime, nullable=True)

    listings = relationship("Listing", back_populates="agent", cascade="all, delete-orphan")

    @property
    def connected_platforms(self):
        return json.loads(self.connected_platforms_json or "[]")

    @connected_platforms.setter
    def connected_platforms(self, v):
        self.connected_platforms_json = json.dumps(v)

    def public_branding(self):
        return {
            "agency": self.brokerage or "Real Estate Agent",
            "name": self.full_name or "Agent",
            "phone": self.phone or "",
            "email": self.email,
            "logo_path": self.logo_path or "",
            "primary_color": self.primary_color or "#079992",
            "license_number": self.license_number or "",
        }


class Listing(Base):
    __tablename__ = "listings"

    id = Column(String, primary_key=True)
    slug = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=True, index=True)

    property_type = Column(String)
    operation = Column(String)
    address = Column(String)
    city = Column(String)
    state = Column(String)
    zip_code = Column(String)
    price = Column(Integer)
    currency = Column(String, default="USD")
    bedrooms = Column(String)
    bathrooms = Column(String)
    living_area_sqft = Column(Integer)
    lot_size_sqft = Column(Integer)
    garage_spaces = Column(String)
    year_built = Column(String)
    hoa_fee = Column(Float, default=0)
    features_json = Column(Text)
    photos_json = Column(Text)

    description = Column(Text)
    instagram_caption = Column(Text)
    headline = Column(String)

    pdf_path = Column(String)
    ig_image_path = Column(String)

    publish_results_json = Column(Text)
    is_published = Column(Boolean, default=False)

    agent = relationship("Agent", back_populates="listings")

    @property
    def features(self):
        return json.loads(self.features_json or "[]")

    @features.setter
    def features(self, v):
        self.features_json = json.dumps(v)

    @property
    def photos(self):
        return json.loads(self.photos_json or "[]")

    @photos.setter
    def photos(self, v):
        self.photos_json = json.dumps(v)

    @property
    def publish_results(self):
        return json.loads(self.publish_results_json or "{}")

    @publish_results.setter
    def publish_results(self, v):
        self.publish_results_json = json.dumps(v)

    def to_prop_dict(self):
        return {
            "property_type": self.property_type, "operation": self.operation,
            "address": self.address, "city": self.city, "state": self.state, "zip_code": self.zip_code,
            "price": self.price, "currency": self.currency,
            "bedrooms": self.bedrooms, "bathrooms": self.bathrooms,
            "living_area_sqft": self.living_area_sqft, "lot_size_sqft": self.lot_size_sqft,
            "garage_spaces": self.garage_spaces, "year_built": self.year_built or "-",
            "hoa_fee": self.hoa_fee,
            "features": self.features,
        }

    def to_text_dict(self):
        return {
            "description": self.description,
            "instagram_caption": self.instagram_caption,
            "headline": self.headline,
        }


def init_db():
    Base.metadata.create_all(engine)


def make_slug(prop_dict, session) -> str:
    base = slugify(f"{prop_dict['property_type']}-{prop_dict['bedrooms']}-bed-{prop_dict['city']}-{prop_dict['operation']}")
    suffix = uuid.uuid4().hex[:6]
    slug = f"{base}-{suffix}"
    while session.query(Listing).filter_by(slug=slug).first():
        suffix = uuid.uuid4().hex[:6]
        slug = f"{base}-{suffix}"
    return slug


def make_api_key():
    return f"lpk_{secrets.token_urlsafe(32)}"
