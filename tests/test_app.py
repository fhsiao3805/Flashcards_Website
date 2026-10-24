import re

import pytest

from app import create_app
from models import Card, Deck, User, db


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
    })
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def register(client, username="alice", password="password123"):
    return client.post("/register", data={
        "username": username, "password": password, "confirm": password,
    }, follow_redirects=True)


def make_deck(app, client, cards=3):
    client.post("/decks", data={"name": "Spanish"})
    with app.app_context():
        deck = Deck.query.filter_by(name="Spanish").one()
        deck_id = deck.id
    for i in range(cards):
        client.post(f"/decks/{deck_id}/cards", data={"front": f"front{i}", "back": f"back{i}"})
    return deck_id


def current_front(client, deck_id):
    html = client.get(f"/decks/{deck_id}/study").get_data(as_text=True)
    match = re.search(r'/study/(\d+)"', html)
    return (int(match.group(1)) if match else None), html


def test_home_is_login_and_decks_require_login(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Log in" in resp.data
    resp = client.get("/decks")
    assert resp.status_code == 302
    assert resp.headers["Location"].startswith("/?next=")


def test_register_login_logout(client):
    assert b"My decks" in register(client).data
    client.post("/logout")
    resp = client.post("/", data={"username": "alice", "password": "wrong-pass"})
    assert b"Invalid username or password" in resp.data
    resp = client.post("/", data={"username": "ALICE", "password": "password123"}, follow_redirects=True)
    assert b"My decks" in resp.data


def test_duplicate_and_invalid_registration(client):
    register(client)
    client.post("/logout")
    assert b"already taken" in register(client, "Alice").data
    assert b"at least 8" in register(client, "bob", "short").data


def test_study_marks_known_cards_and_reset(app, client):
    register(client)
    deck_id = make_deck(app, client, cards=3)

    client.get(f"/decks/{deck_id}/study?new=1")
    first, html = current_front(client, deck_id)
    assert "3 cards left" in html
    client.post(f"/decks/{deck_id}/study/{first}", data={"result": "known"})

    second, _ = current_front(client, deck_id)
    assert second != first
    client.post(f"/decks/{deck_id}/study/{second}", data={"result": "unknown"})

    third, _ = current_front(client, deck_id)
    assert third not in (first, second)
    client.post(f"/decks/{deck_id}/study/{third}", data={"result": "known"})

    _, html = current_front(client, deck_id)
    assert "Pass complete" in html

    # A new study session only shows the card that wasn't marked known.
    client.get(f"/decks/{deck_id}/study?new=1")
    nxt, html = current_front(client, deck_id)
    assert nxt == second and "1 card left" in html

    client.post(f"/decks/{deck_id}/reset")
    with app.app_context():
        assert Card.query.filter_by(known=True).count() == 0
    client.get(f"/decks/{deck_id}/study?new=1")
    _, html = current_front(client, deck_id)
    assert "3 cards left" in html


def test_all_known_shows_reset(app, client):
    register(client)
    deck_id = make_deck(app, client, cards=1)
    card_id, _ = current_front(client, deck_id)
    client.post(f"/decks/{deck_id}/study/{card_id}", data={"result": "known"})
    _, html = current_front(client, deck_id)
    assert "You know every card" in html
    assert "reset-dialog" in html


def test_users_cannot_access_other_users_decks(app, client):
    register(client)
    deck_id = make_deck(app, client, cards=1)
    with app.app_context():
        card_id = Card.query.first().id
    client.post("/logout")

    register(client, "mallory")
    assert client.get(f"/decks/{deck_id}").status_code == 404
    assert client.get(f"/decks/{deck_id}/study").status_code == 404
    assert client.post(f"/decks/{deck_id}/reset").status_code == 404
    assert client.post(f"/cards/{card_id}/delete").status_code == 404
    assert client.post(f"/decks/{deck_id}/study/{card_id}", data={"result": "known"}).status_code == 404


def test_edit_and_delete(app, client):
    register(client)
    deck_id = make_deck(app, client, cards=1)
    with app.app_context():
        card_id = Card.query.first().id
    client.post(f"/cards/{card_id}/edit", data={"front": "hola", "back": "hello"})
    with app.app_context():
        assert db.session.get(Card, card_id).front == "hola"
    client.post(f"/decks/{deck_id}/delete")
    with app.app_context():
        assert Deck.query.count() == 0 and Card.query.count() == 0
        assert User.query.count() == 1


def test_csrf_enforced_when_enabled(tmp_path):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'c.db'}"})
    resp = app.test_client().post("/", data={"username": "x", "password": "y"})
    assert resp.status_code == 302  # rejected and redirected, not logged in


def test_add_multiple_cards_at_once(app, client):
    register(client)
    deck_id = make_deck(app, client, cards=0)
    # The empty entry boxes are submitted too and should be ignored.
    resp = client.post(f"/decks/{deck_id}/cards", data={
        "front": ["", "uno", "dos", "tres"],
        "back": ["", "one", "two", "three"],
    }, follow_redirects=True)
    assert b"Added 3 cards" in resp.data
    with app.app_context():
        assert [c.front for c in db.session.get(Deck, deck_id).cards] == ["uno", "dos", "tres"]


def test_add_multiple_cards_is_all_or_nothing(app, client):
    register(client)
    deck_id = make_deck(app, client, cards=0)
    resp = client.post(f"/decks/{deck_id}/cards", data={
        "front": ["uno", "dos"], "back": ["one", ""],
    }, follow_redirects=True)
    assert b"Card 2:" in resp.data
    resp = client.post(f"/decks/{deck_id}/cards", data={"front": [""], "back": [""]}, follow_redirects=True)
    assert b"at least one card" in resp.data
    with app.app_context():
        assert Card.query.count() == 0


def study_sequence(client, deck_id):
    """Walk a full pass marking every card 'not known'; return the card ids seen."""
    seen = []
    while True:
        card_id, _ = current_front(client, deck_id)
        if card_id is None:
            return seen
        seen.append(card_id)
        client.post(f"/decks/{deck_id}/study/{card_id}", data={"result": "unknown"})


def test_shuffle_changes_order_and_can_be_turned_off(app, client):
    register(client)
    deck_id = make_deck(app, client, cards=20)
    with app.app_context():
        added_order = [c.id for c in db.session.get(Deck, deck_id).cards]

    client.get(f"/decks/{deck_id}/study?new=1")
    assert study_sequence(client, deck_id) == added_order

    client.get(f"/decks/{deck_id}/study?new=1")
    resp = client.post(f"/decks/{deck_id}/study/shuffle", data={"mode": "on"}, follow_redirects=True)
    assert b"Shuffled" in resp.data
    shuffled = study_sequence(client, deck_id)
    assert sorted(shuffled) == sorted(added_order)  # every card exactly once
    assert shuffled != added_order  # 1 in 20! chance of a false failure

    # Shuffle stays on for the next pass, with a fresh order.
    client.get(f"/decks/{deck_id}/study?new=1")
    assert study_sequence(client, deck_id) != shuffled

    client.get(f"/decks/{deck_id}/study?new=1")
    client.post(f"/decks/{deck_id}/study/shuffle", data={"mode": "off"})
    assert study_sequence(client, deck_id) == added_order


def test_shuffled_order_is_stable_within_a_pass(app, client):
    register(client)
    deck_id = make_deck(app, client, cards=10)
    client.post(f"/decks/{deck_id}/study/shuffle", data={"mode": "on"})
    first, _ = current_front(client, deck_id)
    again, _ = current_front(client, deck_id)  # reloading doesn't reshuffle
    assert first == again
    assert client.post(f"/decks/{deck_id}/study/shuffle", data={"mode": "bogus"}).status_code == 400
