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


def test_deck_description_is_optional_and_editable(app, client):
    register(client)
    deck_id = make_deck(app, client, cards=0)
    resp = client.post(f"/decks/{deck_id}/details", data={
        "course": "CSEN 174", "professor": "Prof. Smith", "description": "Intro to software engineering",
    }, follow_redirects=True)
    assert b"Deck description saved" in resp.data
    assert b"Intro to software engineering" in resp.data
    assert b"Prof. Smith" in client.get("/decks").data

    # Everything can be cleared again.
    client.post(f"/decks/{deck_id}/details", data={"course": "", "professor": "", "description": ""})
    with app.app_context():
        deck = db.session.get(Deck, deck_id)
        assert (deck.course, deck.professor, deck.description) == (None, None, None)

    resp = client.post(f"/decks/{deck_id}/details", data={"description": "x" * 501}, follow_redirects=True)
    assert b"limited to 500" in resp.data


def test_existing_database_gets_new_deck_columns(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE decks (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, "
                 "user_id INTEGER NOT NULL, created_at DATETIME NOT NULL)")
    conn.commit()
    conn.close()

    create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{path}"})
    conn = sqlite3.connect(path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(decks)")}
    conn.close()
    assert {"professor", "course", "description"} <= columns


def add_deck(client, name, course="", professor="", cards=1, public=True):
    """Create a deck through the UI; public=True makes it public via Deck settings."""
    client.post("/decks", data={"name": name})
    deck_id = int(client.get("/decks").get_data(as_text=True).split("/decks/")[1].split('"')[0])
    for i in range(cards):
        client.post(f"/decks/{deck_id}/cards", data={"front": f"q{i}", "back": f"a{i}"})
    data = {"course": course, "professor": professor, "description": ""}
    if public:
        data["visibility"] = "public"
    client.post(f"/decks/{deck_id}/details", data=data)
    return deck_id


def deck_names(resp):
    return re.findall(r'class="deck-name">([^<]+)<', resp.get_data(as_text=True))


def test_find_other_decks_search(client):
    register(client, "bob")
    add_deck(client, "Cell Biology", course="BIOL 21", professor="Dr. Lee")
    add_deck(client, "Data Structures", course="CSEN 12", professor="Prof. Smith")
    add_deck(client, "Secret notes", course="BIOL 21", public=False)
    add_deck(client, "Empty biology deck", cards=0)
    client.post("/logout")

    register(client, "carol")
    add_deck(client, "My own biology deck")

    # No query: all other users' public, non-empty decks.
    assert sorted(deck_names(client.get("/find"))) == ["Cell Biology", "Data Structures"]
    # Case-insensitive, partial match across all fields.
    assert deck_names(client.get("/find?q=biol")) == ["Cell Biology"]
    assert deck_names(client.get("/find?q=smith")) == ["Data Structures"]
    # Restricting to one field.
    assert deck_names(client.get("/find?q=csen&field=course")) == ["Data Structures"]
    assert deck_names(client.get("/find?q=csen&field=professor")) == []
    assert deck_names(client.get("/find?q=lee&field=professor")) == ["Cell Biology"]
    # LIKE wildcards are matched literally.
    assert deck_names(client.get("/find?q=%25")) == []
    assert b"No shared decks match" in client.get("/find?q=zzz").data


def test_view_and_copy_shared_deck(app, client):
    register(client, "bob")
    public_id = add_deck(client, "Cell Biology", course="BIOL 21", cards=2)
    private_id = add_deck(client, "Secret notes", public=False)
    client.post("/logout")

    register(client, "carol")
    resp = client.get(f"/find/{public_id}")
    assert b"Cell Biology" in resp.data and b"shared by bob" in resp.data
    assert client.get(f"/find/{private_id}").status_code == 404
    assert client.post(f"/find/{private_id}/copy").status_code == 404
    # Viewing a shared deck doesn't grant edit access.
    assert client.get(f"/decks/{public_id}").status_code == 404

    resp = client.post(f"/find/{public_id}/copy", follow_redirects=True)
    assert b"Copied" in resp.data
    with app.app_context():
        carol = User.query.filter_by(username="carol").one()
        copy = Deck.query.filter_by(user_id=carol.id).one()
        assert copy.course == "BIOL 21"
        assert [(c.front, c.known) for c in copy.cards] == [("q0", False), ("q1", False)]
        assert len(db.session.get(Deck, public_id).cards) == 2  # original untouched


def test_decks_are_private_by_default(app, client):
    register(client, "bob")
    deck_id = add_deck(client, "Cell Biology", public=False)
    assert b"Private" in client.get(f"/decks/{deck_id}").data
    with app.app_context():
        assert db.session.get(Deck, deck_id).visibility == "private"
    client.post("/logout")

    register(client, "carol")
    assert deck_names(client.get("/find")) == []
    assert client.get(f"/find/{deck_id}").status_code == 404
    client.post("/logout")

    # Owner makes it public, then private again.
    client.post("/", data={"username": "bob", "password": "password123"})
    client.post(f"/decks/{deck_id}/details", data={"visibility": "public"})
    assert b"Public" in client.get(f"/decks/{deck_id}").data
    client.post("/logout")
    client.post("/", data={"username": "carol", "password": "password123"})
    assert deck_names(client.get("/find")) == ["Cell Biology"]
    client.post("/logout")

    client.post("/", data={"username": "bob", "password": "password123"})
    client.post(f"/decks/{deck_id}/details", data={})  # no visibility sent -> private
    with app.app_context():
        assert db.session.get(Deck, deck_id).visibility == "private"


def test_existing_decks_become_private_on_upgrade(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    # A database from the version where decks were shared by default.
    conn.execute("CREATE TABLE decks (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, "
                 "user_id INTEGER NOT NULL, created_at DATETIME NOT NULL, "
                 "is_public BOOLEAN DEFAULT 1 NOT NULL)")
    conn.execute("INSERT INTO decks (id, name, user_id, created_at) VALUES (1, 'old', 1, '2026-01-01')")
    conn.commit()
    conn.close()

    create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{path}"})
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT visibility FROM decks").fetchone() == ("private",)
    conn.close()
