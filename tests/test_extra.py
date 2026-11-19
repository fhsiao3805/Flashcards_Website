import re

import pytest

from app import create_app
from models import Card, Deck, db


@pytest.fixture
def app(tmp_path):
    # Each test gets its own throwaway SQLite database.
    return create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'extra.db'}",
    })


@pytest.fixture
def client(app):
    return app.test_client()


def register(client, username="dana", password="password123"):
    return client.post("/register", data={
        "username": username, "password": password, "confirm": password,
    })


def login(client, next_url=None, username="dana", password="password123"):
    url = "/" if next_url is None else f"/?next={next_url}"
    return client.post(url, data={"username": username, "password": password})


def create_deck_with_cards(app, client, pairs):
    client.post("/decks", data={"name": "Biology"})
    with app.app_context():
        deck_id = Deck.query.filter_by(name="Biology").one().id
    client.post(f"/decks/{deck_id}/cards", data={
        "front": [f for f, _ in pairs], "back": [b for _, b in pairs],
    })
    return deck_id


def shown_card_id(client, deck_id):
    html = client.get(f"/decks/{deck_id}/study").get_data(as_text=True)
    match = re.search(r'/study/(\d+)"', html)
    return int(match.group(1)) if match else None


def test_login_next_only_redirects_to_local_paths(client):
    register(client)
    client.post("/logout")

    # A local path in ?next= is honored after logging in.
    resp = login(client, next_url="/find")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/find"
    client.post("/logout")

    # Off-site targets are ignored to prevent open redirects; the user lands on their decks.
    for evil in ("//evil.example.com", "https://evil.example.com", "/\\evil.example.com"):
        resp = login(client, next_url=evil)
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/decks", evil
        client.post("/logout")


def test_logout_requires_post_and_clears_study_progress(app, client):
    register(client)
    deck_id = create_deck_with_cards(app, client, [("cell", "unit of life"), ("DNA", "genetic code")])
    with app.app_context():
        first_id, second_id = [c.id for c in db.session.get(Deck, deck_id).cards]

    # Mark the first card "not known" so the study pass moves on to the second card.
    assert shown_card_id(client, deck_id) == first_id
    client.post(f"/decks/{deck_id}/study/{first_id}", data={"result": "unknown"})
    assert shown_card_id(client, deck_id) == second_id

    # Logging out via GET is not allowed and leaves the user logged in.
    assert client.get("/logout").status_code == 405
    assert client.get("/decks").status_code == 200

    # A real logout ends the session, and the skipped-card progress is cleared with it.
    client.post("/logout")
    assert client.get("/decks").status_code == 302
    login(client)
    assert shown_card_id(client, deck_id) == first_id


def test_invalid_card_edit_is_rejected_and_card_unchanged(app, client):
    register(client)
    deck_id = create_deck_with_cards(app, client, [("mitosis", "cell division")])
    with app.app_context():
        card_id = Card.query.filter_by(deck_id=deck_id).one().id

    # Blank back side: the form is re-shown with an error.
    resp = client.post(f"/cards/{card_id}/edit", data={"front": "meiosis", "back": "   "})
    assert resp.status_code == 200
    assert b"Both the front and back of a card are required." in resp.data

    # Text over the 2000-character limit is rejected too.
    resp = client.post(f"/cards/{card_id}/edit", data={"front": "x" * 2001, "back": "too long"})
    assert resp.status_code == 200
    assert b"limited to 2000 characters" in resp.data

    # Neither bad submission changed the stored card.
    with app.app_context():
        card = db.session.get(Card, card_id)
        assert (card.front, card.back) == ("mitosis", "cell division")
