import hashlib, json, sqlite3
from pathlib import Path
from .models import Evidence

DB=Path("data/tradingdyor.db")

def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con=sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS evidence(
      id INTEGER PRIMARY KEY,
      source TEXT NOT NULL,
      url TEXT NOT NULL,
      retrieved_at TEXT NOT NULL,
      title TEXT,
      excerpt TEXT,
      confidence REAL,
      extraction_method TEXT,
      content_hash TEXT UNIQUE
    )""")
    con.commit()
    return con

def save_evidence(e: Evidence):
    digest=hashlib.sha256((e.url+"|"+e.title+"|"+e.excerpt).encode()).hexdigest()
    with connect() as con:
        con.execute(
          "INSERT OR IGNORE INTO evidence(source,url,retrieved_at,title,excerpt,confidence,extraction_method,content_hash) VALUES(?,?,?,?,?,?,?,?)",
          (e.source,e.url,e.retrieved_at.isoformat(),e.title,e.excerpt,e.confidence,e.extraction_method,digest)
        )
        con.commit()

def count():
    with connect() as con:
        return con.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
