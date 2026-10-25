# Flashcards Website

A Flask web app for making and studying flashcards. Each user has an account and their own decks, stored in a database.

## Features

- **The login page is the home page** (`/`). New users can sign up at `/register`. Passwords are stored as salted hashes.
- **Decks:** create, rename, and delete decks of flashcards. Under **Deck settings**, you can add an optional **description**: the course name, the professor's name, and a short course description. These appear at the top of the deck page, and the course and professor also appear on the deck's tile in **My decks**.
- **Find Other Decks** (`/find`, linked in the top bar): search decks other users have shared by **deck name**, **course name**, or **professor**, or across all three. Matching is case-insensitive and also matches part of a word. With no search terms, the page lists recently shared decks. Each result opens a read-only preview of the deck's cards with a **Copy to my decks** button, which makes your own copy to study and edit.
- **Public or private decks:** every deck is **private** by default, so only you can see it. To share one, open **Deck settings → Description**, choose **🌐 Public** under **Visibility**, and click **Save description**. Public decks appear in Find Other Decks, where other users can view and copy them. Switch back to **🔒 Private** at any time to hide the deck again. Each deck shows a Public or Private badge on its page and on its tile in **My decks**. Decks with no cards never appear in search, even if they're public.
- **Cards:** each card has a front and a back. To add cards, fill in the front and back and click **+ Add to list** (or press <kbd>Ctrl</kbd>/<kbd>⌘</kbd>+<kbd>Enter</kbd>). Repeat for as many cards as you like. They appear as a numbered list that you can remove items from. Then click **Add cards** to save the whole list to the deck at once. Cards can also be edited or deleted later.
- **Study mode:** one card at a time. Click the card (or press <kbd>Space</kbd>) to flip it, then mark it:
  - **✓ I know this** (<kbd>2</kbd>): the card is saved as *known* and is skipped every time you study this deck again.
  - **✗ Don't know yet** (<kbd>1</kbd>): the card moves to the back for this pass and shows up again in your next session.
- **How known cards work:**
  - Each card has a `known` flag in the database. Studying a deck shows only cards where `known` is false.
  - Marking a card **known** sets the flag, so the card stays hidden in future sessions, even after you log out.
  - Marking a card **not known** leaves the flag alone. The app records it in your session for the current pass only, so you can work through the rest of the deck.
  - **Reset marked cards** sets `known = false` for every card in the deck.
- **Shuffle:** on the study page, click **🔀 Shuffle cards** (or press <kbd>S</kbd>) to study the remaining cards in random order instead of the order you added them. While shuffle is on, **Reshuffle** picks a new random order and **Use added order** turns it off. Shuffle stays on for that deck, and each new study session gets a fresh random order.
- **Reset marked cards:** a pop-up asks you to confirm. If you confirm, every known card in the deck is unmarked and shows up again the next time you study.
- Users can only change their own decks. Other users can view and copy shared decks, but can't edit them.

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

Requires Python 3.10 or newer (developed on 3.12). Check your version with `python3 --version` on macOS or `py --version` on Windows. If Python isn't installed, download it from [python.org](https://www.python.org/downloads/). On Windows, check **Add python.exe to PATH** during setup.

All commands below are run from the project folder (the one containing `app.py`).

### macOS

Open **Terminal** and run:

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements-dev.txt

# 3. Start the app
flask --app app run --debug
```

### Windows

Open **PowerShell** and run:

```powershell
# 1. Create and activate a virtual environment
py -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements-dev.txt

# 3. Start the app
flask --app app run --debug
```

If PowerShell says running scripts is disabled, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then try activating again. If you use **Command Prompt** instead of PowerShell, activate with `.venv\Scripts\activate.bat`.

### Using the app

Open http://127.0.0.1:5000, create an account, and start making decks. Press <kbd>Ctrl</kbd>+<kbd>C</kbd> in the terminal to stop the server.

With no `DATABASE_URL` set, the app creates a SQLite file at `instance/flashcards.db`. Tables are created automatically on startup. If a database was created by an older version of the app, any new optional columns (such as the deck description fields) are added automatically on startup. Your data is kept.

Next time, you only need to activate the virtual environment (step 1's second line) and start the app (step 3).

### Running the tests

With the virtual environment activated, on either system:

```bash
pytest
```

## Configuration

No configuration is needed to run locally. These optional environment variables change the app's settings:

| Variable                | Description |
|-------------------------|-------------|
| `SECRET_KEY`            | Long random string used to sign session cookies. If unset, the app uses an insecure development key and logs a warning. Generate one with `python -c "import secrets; print(secrets.token_hex(32))"`. |
| `DATABASE_URL`          | Database connection URL, e.g. `postgresql://user:pass@host:5432/db`. `postgres://` URLs are accepted too. Defaults to local SQLite. |
| `SESSION_COOKIE_SECURE` | Set to `1` when serving over HTTPS so cookies are sent only over HTTPS. |

To set a variable before starting the app:

- **macOS:** `export SECRET_KEY=your-key-here`
- **Windows (PowerShell):** `$env:SECRET_KEY = "your-key-here"`
- **Windows (Command Prompt):** `set SECRET_KEY=your-key-here`
