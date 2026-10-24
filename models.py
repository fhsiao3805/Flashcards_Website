from datetime import datetime, timezone

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
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
    # Optional course details shown on the deck page.
    professor = db.Column(db.String(100))
    course = db.Column(db.String(150))
    description = db.Column(db.Text)
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


def add_missing_columns():
    """Add nullable columns that were introduced after a table was first created.

    db.create_all() only creates missing tables, so existing databases need the
    new deck description columns added by hand.
    """
    inspector = inspect(db.engine)
    for table in db.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing or not column.nullable:
                continue
            col_type = column.type.compile(dialect=db.engine.dialect)
            try:
                with db.engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))
            except DBAPIError:
                # Another worker may have added it at the same moment.
                columns = inspect(db.engine).get_columns(table.name)
                if column.name not in {col["name"] for col in columns}:
                    raise
