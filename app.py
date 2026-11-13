from flask import Flask, jsonify, render_template, request, redirect, url_for
from contextlib import closing
from pathlib import Path
from functools import wraps
import hmac
import os
import secrets
import sqlite3
import datetime
from flask import abort, session

app = Flask(__name__)
secret_key = os.environ.get("SECRET_KEY")
moderator_password = os.environ.get("MODERATOR_PASSWORD")
if not secret_key:
    raise RuntimeError("Set the SECRET_KEY environment variable before starting the app.")
if not moderator_password:
    raise RuntimeError("Set the MODERATOR_PASSWORD environment variable before starting the app.")
if len(moderator_password) < 16:
    raise RuntimeError("MODERATOR_PASSWORD must contain at least 16 characters.")

app.config.update(
    SECRET_KEY=secret_key,
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(hours=12),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true",
)
MODERATOR_PASSWORD = moderator_password
DATABASE_PATH = Path(os.environ.get(
    "DATABASE_PATH",
    str(Path(__file__).resolve().parent / "arasaka_music.db"),
))


def generate_csrf_token():
    token = session.get("_csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def validate_csrf_token():
    expected_token = session.get("_csrf_token", "")
    submitted_token = request.form.get("csrf_token", "")
    if not expected_token or not hmac.compare_digest(submitted_token, expected_token):
        abort(400, description="Token de seguridad inválido.")


def moderator_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("is_moderator") is not True:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def init_db():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT, artist TEXT, creator TEXT, genre TEXT,
            genre_desc TEXT, release_date TEXT, duration TEXT,
            artist_info TEXT, lyrics TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS threads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            song_id INTEGER,
            author TEXT,
            timestamp TEXT,
            content TEXT,
            upvotes INTEGER DEFAULT 0,
            FOREIGN KEY(song_id) REFERENCES songs(id)
        )
    """)
    cursor.execute("SELECT COUNT(*) FROM songs")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO songs (title, artist, creator, genre, genre_desc, release_date, duration, artist_info, lyrics)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'Chippin In', 'SAMURAI (Refused)', 'Johnny Silverhand / Refused',
            'Cyberpunk / Hard Rock', 'Subgénero de rock pesado con temáticas de rebelión anti-corporativa.',
            '2077', '3:33', 'SAMURAI fue una famosa banda de chrome rock en Night City.',
            'Can you feel it?\nCan you touch it?\nGet up, on your feet, yeah!\nChippin in!'
        ))
        cursor.execute("""
            INSERT INTO threads (song_id, author, timestamp, content, upvotes)
            VALUES (1, 'V_Cyber', '2026-11-10 14:32:05', 'Un clásico absoluto de Night City. La guitarra de Johnny suena increíble.', 5)
        """)
        conn.commit()
    conn.close()

init_db()

@app.route("/")
def index():
    query = request.args.get("q", "").lower()
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    if query:
        cursor.execute("SELECT * FROM songs WHERE LOWER(title) LIKE ? OR LOWER(artist) LIKE ? OR LOWER(genre) LIKE ?", 
                       (f"%{query}%", f"%{query}%", f"%{query}%"))
    else:
        cursor.execute("SELECT * FROM songs")
    songs = cursor.fetchall()

    cursor.execute("""
        SELECT threads.id, threads.author, threads.timestamp, threads.content, threads.upvotes, songs.title, songs.artist 
        FROM threads 
        JOIN songs ON threads.song_id = songs.id 
        ORDER BY threads.id DESC
    """)
    feed = cursor.fetchall()
    conn.close()
    
    return render_template(
        "index.html",
        songs=songs,
        feed=feed,
        query=query,
        is_moderator=session.get("is_moderator") is True,
        csrf_token=generate_csrf_token(),
    )


@app.route("/moderator/login", methods=["GET", "POST"])
def moderator_login():
    if request.method == "POST":
        validate_csrf_token()
        submitted_password = request.form.get("password", "")
        if hmac.compare_digest(submitted_password.encode("utf-8"), MODERATOR_PASSWORD.encode("utf-8")):
            session.clear()
            session["is_moderator"] = True
            session.permanent = True
            return redirect(url_for("index"))
        return render_template(
            "moderator_login.html",
            csrf_token=generate_csrf_token(),
            error="Clave incorrecta.",
        ), 401

    return render_template("moderator_login.html", csrf_token=generate_csrf_token())


@app.route("/moderator/logout", methods=["POST"])
@moderator_required
def moderator_logout():
    validate_csrf_token()
    session.clear()
    return redirect(url_for("index"))


@app.route("/moderator/songs/<int:song_id>/delete", methods=["POST"])
@moderator_required
def moderator_delete_song(song_id):
    validate_csrf_token()
    with closing(sqlite3.connect(DATABASE_PATH)) as conn:
        with conn:
            conn.execute("DELETE FROM threads WHERE song_id = ?", (song_id,))
            result = conn.execute("DELETE FROM songs WHERE id = ?", (song_id,))
    if result.rowcount == 0:
        abort(404)
    return redirect(url_for("index"))


@app.route("/moderator/threads/<int:thread_id>/delete", methods=["POST"])
@moderator_required
def moderator_delete_thread(thread_id):
    validate_csrf_token()
    with closing(sqlite3.connect(DATABASE_PATH)) as conn:
        with conn:
            result = conn.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
    if result.rowcount == 0:
        abort(404)
    return redirect(url_for("index"))

@app.route("/api/feed")
def api_feed():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT threads.id, threads.author, threads.timestamp, threads.content,
               threads.upvotes, songs.title
        FROM threads
        JOIN songs ON threads.song_id = songs.id
        ORDER BY threads.id DESC
    """)
    feed = [
        {
            "id": row[0],
            "author": row[1],
            "timestamp": row[2],
            "content": row[3],
            "upvotes": row[4],
            "song": row[5],
        }
        for row in cursor.fetchall()
    ]
    conn.close()
    return jsonify(feed)

@app.route("/add_song", methods=["POST"])
def add_song():
    title = request.form.get("title")
    artist = request.form.get("artist")
    creator = request.form.get("creator")
    genre = request.form.get("genre")
    genre_desc = request.form.get("genre_desc")
    release_date = request.form.get("release_date")
    duration = request.form.get("duration")
    artist_info = request.form.get("artist_info")
    lyrics = request.form.get("lyrics")

    if title and artist:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO songs (title, artist, creator, genre, genre_desc, release_date, duration, artist_info, lyrics)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (title, artist, creator, genre, genre_desc, release_date, duration, artist_info, lyrics))
        conn.commit()
        conn.close()
    return redirect(url_for("index"))

@app.route("/post_thread/<int:song_id>", methods=["POST"])
def post_thread(song_id):
    author = request.form.get("author", "Netrunner_Anónimo")
    content = request.form.get("content")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if content and author:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO threads (song_id, author, timestamp, content, upvotes) VALUES (?, ?, ?, ?, 0)",
                       (song_id, author, timestamp, content))
        conn.commit()
        conn.close()
    return redirect(url_for("index"))

@app.route("/upvote/<int:thread_id>")
def upvote(thread_id):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE threads SET upvotes = upvotes + 1 WHERE id = ?", (thread_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)