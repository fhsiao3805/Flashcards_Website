from datetime import datetime, timezone

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    decks = db.relationship(
        "Deck",
        back_populates="owner",
        cascade="all, delete-orphan",
        order_by="Deck.created_at.desc()",
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Deck(db.Model):
    __tablename__ = "decks"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    owner = db.relationship("User", back_populates="decks")
    cards = db.relationship(
        "Card",
        back_populates="deck",
        cascade="all, delete-orphan",
        order_by="Card.id",
    )

    @property
    def known_count(self):
        return sum(1 for card in self.cards if card.known)


class Card(db.Model):
    __tablename__ = "cards"

    id = db.Column(db.Integer, primary_key=True)
    deck_id = db.Column(
        db.Integer, db.ForeignKey("decks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    front = db.Column(db.Text, nullable=False)
    back = db.Column(db.Text, nullable=False)
    # Cards marked known are skipped when studying until the deck is reset.
    known = db.Column(db.Boolean, default=False, nullable=False)

    deck = db.relationship("Deck", back_populates="cards")
