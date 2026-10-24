# Flashcards Website

A Flask web app for making and studying flashcards. Each user has an account and their own decks, stored in a database.

## Features

- **The login page is the home page** (`/`). New users can sign up at `/register`. Passwords are stored as salted hashes.
- **Decks:** create, rename, and delete decks of flashcards.
- **Cards:** add, edit, and delete cards. Each card has a front and a back.
- **Study mode:** one card at a time. Click the card (or press <kbd>Space</kbd>) to flip it, then mark it:
  - **✓ I know this** (<kbd>2</kbd>): the card is saved as *known* and is skipped every time you study this deck again.
  - **✗ Don't know yet** (<kbd>1</kbd>): the card moves to the back for this pass and shows up again in your next session.
- **Reset marked cards:** a pop-up asks you to confirm. If you confirm, every known card in the deck is unmarked and shows up again the next time you study.
- Users can only see and change their own decks. All forms are CSRF-protected.

## Tech stack

| Layer      | Choice                                                         |
|------------|----------------------------------------------------------------|
| Web        | Flask 3, Jinja templates, plain CSS/JS (no build step)         |
| Auth       | Flask-Login, Werkzeug password hashing, Flask-WTF CSRF         |
| Database   | SQLAlchemy using SQLite locally and PostgreSQL in production   |
| Server     | Gunicorn                                                       |

## Project layout

```
app.py              App factory, configuration, and all routes
models.py           User, Deck, and Card database models
templates/          Jinja templates (login, register, decks, deck, study, ...)
static/             style.css and app.js (card flip, reset pop-up, shortcuts)
tests/              pytest test suite
requirements.txt    Runtime dependencies
requirements-dev.txt  Runtime dependencies plus pytest
Procfile            Start command for Heroku/Railway-style hosts
render.yaml         One-click Render blueprint (web service + Postgres)
```

## Running locally

Requires Python 3.10 or newer (developed on 3.12).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

flask --app app run --debug
```

Open http://127.0.0.1:5000, create an account, and start making decks. With no `DATABASE_URL` set, the app creates a SQLite file at `instance/flashcards.db`. Tables are created automatically on startup.

### Running the tests

```bash
pytest
```

## Configuration

All settings come from environment variables:

| Variable                | Required in production | Description |
|-------------------------|------------------------|-------------|
| `SECRET_KEY`            | **Yes**                | Long random string used to sign session cookies. Generate one with `python -c "import secrets; print(secrets.token_hex(32))"`. |
| `DATABASE_URL`          | **Yes**                | Database connection URL, e.g. `postgresql://user:pass@host:5432/db`. `postgres://` URLs are accepted too. Defaults to local SQLite. |
| `SESSION_COOKIE_SECURE` | Recommended            | Set to `1` when serving over HTTPS so cookies are sent only over HTTPS. |

## Deploying (so people can use it from anywhere)

SQLite works for local development, but deploy with PostgreSQL. Many hosts wipe the disk on every deploy, which would delete a SQLite file.

### Option A: Render (blueprint included)

1. Push this repo to GitHub.
2. In the [Render dashboard](https://dashboard.render.com), choose **New → Blueprint** and select the repo.
3. Render reads `render.yaml` and creates:
   - a PostgreSQL database (`flashcards-db`)
   - a web service that runs `gunicorn "app:create_app()"`, with `DATABASE_URL` wired to the database, a generated `SECRET_KEY`, and secure cookies turned on.
4. When the deploy finishes, open the `https://<name>.onrender.com` URL and share it.

> Render's free tier puts the web service to sleep when it's idle, and free Postgres databases expire after a limited time. Use a paid plan for anything long-lived.

### Option B: Any host that runs a Procfile (Railway, Heroku, Fly.io, etc.)

1. Create a PostgreSQL database on the host and set `DATABASE_URL` to its URL.
2. Set `SECRET_KEY` and `SESSION_COOKIE_SECURE=1`.
3. Deploy. The start command is in `Procfile`:
   ```
   web: gunicorn "app:create_app()"
   ```

The app is wrapped in `ProxyFix`, so it handles HTTPS correctly behind the load balancers these hosts use.

## How "known" cards work

- Each card has a `known` flag in the database. Studying a deck shows only cards where `known` is false.
- Marking a card **known** sets the flag, so the card stays hidden in future sessions, even after you log out.
- Marking a card **not known** leaves the flag alone. The app records it in your session for the current pass only, so you can work through the rest of the deck.
- **Reset marked cards** sets `known = false` for every card in the deck. The app asks you to confirm first.
