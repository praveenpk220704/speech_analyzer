"""
db.py — MongoDB helper for SpeakEasy Coach
Database: speakeasy
Collection: sessions
"""
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient, DESCENDING

load_dotenv()

_client = None
_db = None


def _get_db():
    """Return a cached DB reference, connecting if needed. Retries on each call if previously failed."""
    global _client, _db
    if _db is not None:
        return _db

    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGO_DB", "speakeasy")

    try:
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        _client.admin.command("ping")          # verify connectivity
        _db = _client[db_name]
        print("[SpeakEasy] MongoDB connected successfully.")
        return _db
    except Exception as e:
        _client = None
        _db = None
        print(f"[SpeakEasy] MongoDB unavailable: {e}")
        return None


def get_collection():
    db = _get_db()
    return db["sessions"] if db is not None else None


# ──────────────────────────────────────────
# Write
# ──────────────────────────────────────────
def save_session(doc: dict) -> bool:
    """
    Persist one analysis session.
    Returns True on success, False if DB is unavailable.
    """
    col = get_collection()
    if col is None:
        return False
    doc["timestamp"] = datetime.now(timezone.utc)
    col.insert_one(doc)
    return True


# ──────────────────────────────────────────
# Read
# ──────────────────────────────────────────
def get_recent_sessions(limit: int = 10) -> list:
    """Return the most recent `limit` sessions, newest first."""
    col = get_collection()
    if col is None:
        return []
    cursor = col.find({}, {"_id": 0}).sort("timestamp", DESCENDING).limit(limit)
    return list(cursor)


def get_aggregate_stats() -> dict:
    """
    Aggregated stats across all sessions.
    Returns dict with keys: total, avg_score, avg_wpm, avg_fillers
    """
    col = get_collection()
    if col is None:
        return {}

    pipeline = [
        {
            "$group": {
                "_id": None,
                "total": {"$sum": 1},
                "avg_score": {
                    "$avg": {
                        "$cond": [
                            {"$ne": ["$score", None]},
                            "$score",
                            None
                        ]
                    }
                },
                "avg_wpm":     {"$avg": "$wpm"},
                "avg_fillers": {"$avg": "$filler_count"},
            }
        }
    ]
    result = list(col.aggregate(pipeline))
    if not result:
        return {"total": 0, "avg_score": None, "avg_wpm": 0, "avg_fillers": 0}
    r = result[0]
    return {
        "total":       r.get("total", 0),
        "avg_score":   round(r["avg_score"], 1) if r.get("avg_score") is not None else None,
        "avg_wpm":     round(r.get("avg_wpm", 0), 1),
        "avg_fillers": round(r.get("avg_fillers", 0), 1),
    }


def clear_all_sessions() -> int:
    """Delete every session. Returns count of deleted docs."""
    col = get_collection()
    if col is None:
        return 0
    result = col.delete_many({})
    return result.deleted_count


def is_connected() -> bool:
    """Quick health-check: True if DB is reachable."""
    return get_collection() is not None
