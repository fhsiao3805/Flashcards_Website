import hashlib
import logging
import os
import re
import secrets

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from models import Card, Deck, User, add_missing_columns, db

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")
MIN_PASSWORD_LENGTH = 8
MAX_DECK_NAME = 100
MAX_PROFESSOR = 100
MAX_COURSE = 150
MAX_DESCRIPTION = 500
MAX_CARD_TEXT = 2000
MAX_CARDS_PER_SUBMIT = 200

csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Please log in to continue."


def database_url():
    url = os.environ.get("DATABASE_URL", "sqlite:///flashcards.db")
    # Hosts like Render/Heroku hand out postgres:// URLs; SQLAlchemy needs a driver name.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def create_app(config=None):
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        logging.warning("SECRET_KEY is not set; using an insecure development key.")
        secret_key = "dev-insecure-key-change-me"

    app.config.update(
        SECRET_KEY=secret_key,
        SQLALCHEMY_DATABASE_URI=database_url(),
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
        REMEMBER_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
    )
    if config:
        app.config.update(config)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)

    with app.app_context():
        db.create_all()
        add_missing_columns()

    register_routes(app)
    return app


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def get_owned_deck(deck_id):
    deck = db.session.get(Deck, deck_id)
    if deck is None or deck.user_id != current_user.id:
        abort(404)
    return deck


def get_owned_card(card_id):
    card = db.session.get(Card, card_id)
    if card is None or card.deck.user_id != current_user.id:
        abort(404)
    return card


def is_safe_next(target):
    return bool(target) and target.startswith("/") and not target.startswith("//") and "\\" not in target


def validate_card_text(front, back):
    if not front or not back:
        return "Both the front and back of a card are required."
    if len(front) > MAX_CARD_TEXT or len(back) > MAX_CARD_TEXT:
        return f"Card text is limited to {MAX_CARD_TEXT} characters per side."
    return None


# Study-session state lives in the signed session cookie: for each deck, the ids of
# cards the user marked "not known" during the current pass, so the pass moves on.
def get_skipped(deck_id):
    return session.get("study", {}).get(str(deck_id), [])


def set_skipped(deck_id, card_ids):
    study = dict(session.get("study", {}))
    study[str(deck_id)] = card_ids
    session["study"] = study


# Shuffle mode is stored per deck as a random seed (absent = cards in added order).
# Ordering by a hash of seed + card id keeps the order stable for the whole pass,
# even if cards are added mid-pass, without storing every card id in the cookie.
def get_shuffle_seed(deck_id):
    return session.get("shuffle", {}).get(str(deck_id))


def set_shuffle_seed(deck_id, seed):
    shuffle = dict(session.get("shuffle", {}))
    if seed is None:
        shuffle.pop(str(deck_id), None)
    else:
        shuffle[str(deck_id)] = seed
    session["shuffle"] = shuffle


def study_order(cards, seed):
    if seed is None:
        return list(cards)
    return sorted(cards, key=lambda c: hashlib.sha256(f"{seed}:{c.id}".encode()).digest())


def register_routes(app):
    @app.route("/", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("decks"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = User.query.filter(db.func.lower(User.username) == username.lower()).first()
            if user and user.check_password(password):
                login_user(user, remember=bool(request.form.get("remember")))
                next_url = request.args.get("next")
                return redirect(next_url if is_safe_next(next_url) else url_for("decks"))
            flash("Invalid username or password.", "error")

        return render_template("login.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("decks"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm", "")

            error = None
            if not USERNAME_RE.match(username):
                error = "Username must be 3-30 characters: letters, numbers, or underscores."
            elif len(password) < MIN_PASSWORD_LENGTH:
                error = f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
            elif password != confirm:
                error = "Passwords do not match."
            elif User.query.filter(db.func.lower(User.username) == username.lower()).first():
                error = "That username is already taken."

            if error:
                flash(error, "error")
                return render_template("register.html", username=username)

            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Welcome! Create your first deck below.", "success")
            return redirect(url_for("decks"))

        return render_template("register.html")

    @app.post("/logout")
    @login_required
    def logout():
        logout_user()
        session.pop("study", None)
        session.pop("shuffle", None)
        flash("You have been logged out.", "success")
        return redirect(url_for("login"))

    @app.route("/decks", methods=["GET", "POST"])
    @login_required
    def decks():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Deck name is required.", "error")
            elif len(name) > MAX_DECK_NAME:
                flash(f"Deck name is limited to {MAX_DECK_NAME} characters.", "error")
            else:
                deck = Deck(name=name, owner=current_user)
                db.session.add(deck)
                db.session.commit()
                flash(f"Created deck “{name}”. Add some cards!", "success")
                return redirect(url_for("deck_detail", deck_id=deck.id))
            return redirect(url_for("decks"))

        return render_template("decks.html", decks=current_user.decks)

    @app.get("/decks/<int:deck_id>")
    @login_required
    def deck_detail(deck_id):
        deck = get_owned_deck(deck_id)
        return render_template("deck.html", deck=deck)

    @app.post("/decks/<int:deck_id>/rename")
    @login_required
    def rename_deck(deck_id):
        deck = get_owned_deck(deck_id)
        name = request.form.get("name", "").strip()
        if not name or len(name) > MAX_DECK_NAME:
            flash(f"Deck name must be 1-{MAX_DECK_NAME} characters.", "error")
        else:
            deck.name = name
            db.session.commit()
            flash("Deck renamed.", "success")
        return redirect(url_for("deck_detail", deck_id=deck.id))

    @app.post("/decks/<int:deck_id>/details")
    @login_required
    def update_deck_details(deck_id):
        deck = get_owned_deck(deck_id)
        professor = request.form.get("professor", "").strip()
        course = request.form.get("course", "").strip()
        description = request.form.get("description", "").strip()

        if len(professor) > MAX_PROFESSOR:
            flash(f"Professor name is limited to {MAX_PROFESSOR} characters.", "error")
        elif len(course) > MAX_COURSE:
            flash(f"Course name is limited to {MAX_COURSE} characters.", "error")
        elif len(description) > MAX_DESCRIPTION:
            flash(f"Description is limited to {MAX_DESCRIPTION} characters.", "error")
        else:
            # All fields are optional; blank clears them.
            deck.professor = professor or None
            deck.course = course or None
            deck.description = description or None
            db.session.commit()
            flash("Deck description saved.", "success")
        return redirect(url_for("deck_detail", deck_id=deck.id))

    @app.post("/decks/<int:deck_id>/delete")
    @login_required
    def delete_deck(deck_id):
        deck = get_owned_deck(deck_id)
        db.session.delete(deck)
        db.session.commit()
        flash(f"Deleted deck “{deck.name}”.", "success")
        return redirect(url_for("decks"))

    @app.post("/decks/<int:deck_id>/cards")
    @login_required
    def add_card(deck_id):
        deck = get_owned_deck(deck_id)
        fronts = request.form.getlist("front")
        backs = request.form.getlist("back")
        if len(fronts) != len(backs):
            abort(400)

        # Pairs left completely blank (e.g. the empty entry boxes) are ignored.
        pairs = [(f.strip(), b.strip()) for f, b in zip(fronts, backs) if f.strip() or b.strip()]
        error = None
        if not pairs:
            error = "Add at least one card to the list first."
        elif len(pairs) > MAX_CARDS_PER_SUBMIT:
            error = f"You can add up to {MAX_CARDS_PER_SUBMIT} cards at a time."
        else:
            for i, (front, back) in enumerate(pairs, start=1):
                error = validate_card_text(front, back)
                if error:
                    error = f"Card {i}: {error}" if len(pairs) > 1 else error
                    break

        if error:
            flash(error, "error")
        else:
            db.session.add_all(Card(deck=deck, front=f, back=b) for f, b in pairs)
            db.session.commit()
            flash(f"Added {len(pairs)} card{'' if len(pairs) == 1 else 's'}.", "success")
        return redirect(url_for("deck_detail", deck_id=deck.id) + "#add-card")

    @app.route("/cards/<int:card_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_card(card_id):
        card = get_owned_card(card_id)
        if request.method == "POST":
            front = request.form.get("front", "").strip()
            back = request.form.get("back", "").strip()
            error = validate_card_text(front, back)
            if error:
                flash(error, "error")
                return render_template("edit_card.html", card=card, front=front, back=back)
            card.front = front
            card.back = back
            db.session.commit()
            flash("Card updated.", "success")
            return redirect(url_for("deck_detail", deck_id=card.deck_id))
        return render_template("edit_card.html", card=card, front=card.front, back=card.back)

    @app.post("/cards/<int:card_id>/delete")
    @login_required
    def delete_card(card_id):
        card = get_owned_card(card_id)
        deck_id = card.deck_id
        db.session.delete(card)
        db.session.commit()
        flash("Card deleted.", "success")
        return redirect(url_for("deck_detail", deck_id=deck_id))

    @app.get("/decks/<int:deck_id>/study")
    @login_required
    def study(deck_id):
        deck = get_owned_deck(deck_id)
        if request.args.get("new"):
            set_skipped(deck.id, [])
            if get_shuffle_seed(deck.id):
                set_shuffle_seed(deck.id, secrets.token_hex(8))
            return redirect(url_for("study", deck_id=deck.id))

        skipped = set(get_skipped(deck.id))
        seed = get_shuffle_seed(deck.id)
        remaining = [c for c in study_order(deck.cards, seed) if not c.known and c.id not in skipped]
        if not remaining:
            return render_template(
                "study_done.html",
                deck=deck,
                not_known=sum(1 for c in deck.cards if not c.known),
            )

        return render_template(
            "study.html",
            deck=deck,
            card=remaining[0],
            remaining=len(remaining),
            shuffled=seed is not None,
        )

    @app.post("/decks/<int:deck_id>/study/shuffle")
    @login_required
    def shuffle_deck(deck_id):
        deck = get_owned_deck(deck_id)
        # "on" turns shuffle on or reshuffles the remaining cards; "off" restores added order.
        mode = request.form.get("mode")
        if mode == "on":
            set_shuffle_seed(deck.id, secrets.token_hex(8))
        elif mode == "off":
            set_shuffle_seed(deck.id, None)
        else:
            abort(400)
        return redirect(url_for("study", deck_id=deck.id))

    @app.post("/decks/<int:deck_id>/study/<int:card_id>")
    @login_required
    def mark_card(deck_id, card_id):
        deck = get_owned_deck(deck_id)
        card = get_owned_card(card_id)
        if card.deck_id != deck.id:
            abort(404)

        result = request.form.get("result")
        if result == "known":
            card.known = True
            db.session.commit()
        elif result == "unknown":
            skipped = get_skipped(deck.id)
            if card.id not in skipped:
                set_skipped(deck.id, skipped + [card.id])
        else:
            abort(400)
        return redirect(url_for("study", deck_id=deck.id))

    @app.post("/decks/<int:deck_id>/reset")
    @login_required
    def reset_deck(deck_id):
        deck = get_owned_deck(deck_id)
        Card.query.filter_by(deck_id=deck.id).update({"known": False})
        db.session.commit()
        set_skipped(deck.id, [])
        flash("All cards in this deck will show up again when you study.", "success")
        return redirect(url_for("deck_detail", deck_id=deck.id))

    @app.errorhandler(404)
    def not_found(_):
        return render_template("error.html", message="Page not found."), 404

    @app.errorhandler(CSRFError)
    def csrf_error(_):
        flash("Your form expired. Please try again.", "error")
        return redirect(url_for("decks") if current_user.is_authenticated else url_for("login"))

    @app.errorhandler(400)
    def bad_request(_):
        return render_template("error.html", message="Bad request."), 400


if __name__ == "__main__":
    create_app().run(debug=True)
