import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "leadgen.db"

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    cursor = db.cursor()
    
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            location TEXT NOT NULL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            search_id INTEGER,
            name TEXT,
            phone TEXT,
            address TEXT,
            website TEXT,
            email TEXT,
            maps_link TEXT,
            rating REAL,
            reviews INTEGER,
            bookmarked INTEGER DEFAULT 0,
            FOREIGN KEY (search_id) REFERENCES searches(id)
        );
    """)
    
    db.commit()
    db.close()
    logger.info(f"Database initialized at {DB_PATH}")
