from flask import Flask, jsonify, render_template, request, redirect, url_for
from pathlib import Path
import os
import sqlite3
import datetime

app = Flask(__name__)
DATABASE_PATH = Path(os.environ.get(
    "DATABASE_PATH",
    str(Path(__file__).resolve().parent / "arasaka_music.db"),
))

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
    
    return render_template("index.html", songs=songs, feed=feed, query=query)

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