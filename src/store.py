"""Persistent storage for experiment history using SQLite"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional


DB_PATH = Path.home() / ".agent-causal" / "history.db"


def _get_db():
    """Get database connection, creating if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    _init_db(conn)
    return conn


def _init_db(conn):
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mode TEXT NOT NULL,
            decision TEXT NOT NULL,
            confidence TEXT NOT NULL,
            summary TEXT,
            primary_lift REAL,
            p_value REAL,
            created_at TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            inputs_json TEXT NOT NULL,
            planning_json TEXT,
            experiment_name TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_mode ON experiments(mode);
        CREATE INDEX IF NOT EXISTS idx_decision ON experiments(decision);
        CREATE INDEX IF NOT EXISTS idx_created_at ON experiments(created_at);
        CREATE INDEX IF NOT EXISTS idx_experiment_name ON experiments(experiment_name);
    """)


def save_experiment(result_json: str, mode: str, inputs_json: str) -> int:
    """Save an experiment result to history. Returns the row id."""
    data = json.loads(result_json)
    rec = data.get("recommendation", {})
    planning = data.get("planning")
    experiment_name = data.get("inputs", {}).get("experiment_name")

    conn = _get_db()
    cursor = conn.execute(
        """
        INSERT INTO experiments (
            mode, decision, confidence, summary, primary_lift, p_value,
            created_at, raw_json, inputs_json, planning_json, experiment_name
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            mode,
            rec.get("decision", "unknown"),
            rec.get("confidence", "unknown"),
            rec.get("summary", ""),
            rec.get("primary_metricLift"),
            rec.get("p_value"),
            datetime.utcnow().isoformat() + "Z",
            result_json,
            inputs_json,
            json.dumps(planning) if planning else None,
            experiment_name
        )
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def list_experiments(mode: Optional[str] = None, limit: int = 20) -> list:
    """List recent experiments, optionally filtered by mode."""
    conn = _get_db()
    if mode:
        rows = conn.execute(
            "SELECT * FROM experiments WHERE mode = ? ORDER BY created_at DESC LIMIT ?",
            (mode, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM experiments ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_experiment(experiment_id: int) -> Optional[dict]:
    """Get a single experiment by ID."""
    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM experiments WHERE id = ?", (experiment_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_experiment(experiment_id: int) -> bool:
    """Delete an experiment by ID. Returns True if deleted."""
    conn = _get_db()
    cursor = conn.execute(
        "DELETE FROM experiments WHERE id = ?", (experiment_id,)
    )
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def compare_experiments(experiment_ids: list) -> dict:
    """Compare multiple experiments by ID. Returns comparison summary."""
    conn = _get_db()
    placeholders = ",".join(["?"] * len(experiment_ids))
    rows = conn.execute(
        f"SELECT * FROM experiments WHERE id IN ({placeholders})",
        experiment_ids
    ).fetchall()
    conn.close()

    if len(rows) < 2:
        return {"error": "Need at least 2 experiments to compare"}

    experiments = [dict(row) for row in rows]
    comparison = {
        "count": len(experiments),
        "experiments": [],
        "by_decision": {},
        "by_mode": {},
        "lift_summary": {}
    }

    for exp in experiments:
        mode = exp["mode"]
        decision = exp["decision"]
        lift = exp["primary_lift"]
        p_val = exp["p_value"]

        # By decision
        if decision not in comparison["by_decision"]:
            comparison["by_decision"][decision] = []
        comparison["by_decision"][decision].append({
            "id": exp["id"],
            "mode": mode,
            "lift": lift,
            "p_value": p_val,
            "created_at": exp["created_at"]
        })

        # By mode
        if mode not in comparison["by_mode"]:
            comparison["by_mode"][mode] = []
        comparison["by_mode"][mode].append(exp["id"])

        # Per-experiment summary
        comparison["experiments"].append({
            "id": exp["id"],
            "mode": mode,
            "decision": decision,
            "confidence": exp["confidence"],
            "primary_lift": lift,
            "p_value": p_val,
            "created_at": exp["created_at"],
            "experiment_name": exp["experiment_name"]
        })

    # Lift summary
    lifts = [e["primary_lift"] for e in experiments if e["primary_lift"] is not None]
    if lifts:
        comparison["lift_summary"] = {
            "max": max(lifts),
            "min": min(lifts),
            "avg": round(sum(lifts) / len(lifts), 4),
            "count": len(lifts)
        }

    # Recommend attention (experiments with conflicting decisions or negative lifts)
    ship_ids = [e["id"] for e in experiments if e["decision"] == "ship"]
    reject_ids = [e["id"] for e in experiments if e["decision"] == "reject"]
    negative_lift_ids = [e["id"] for e in experiments if e["primary_lift"] is not None and e["primary_lift"] < 0]

    comparison["attention"] = {
        "conflicting_decisions": bool(ship_ids and reject_ids),
        "ship_count": len(ship_ids),
        "reject_count": len(reject_ids),
        "negative_lifts": negative_lift_ids,
        "suggestion": None
    }

    if len(ship_ids) > 1:
        comparison["attention"]["suggestion"] = f"{len(ship_ids)} experiments recommend ship. Review if they test the same metric."
    elif reject_ids:
        comparison["attention"]["suggestion"] = f"{len(reject_ids)} experiments recommend reject. Investigate negative outcomes."
    elif negative_lift_ids:
        comparison["attention"]["suggestion"] = f"{len(negative_lift_ids)} experiments show negative lift."

    return comparison


if __name__ == "__main__":
    # Test
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        experiments = list_experiments(limit=10)
        for e in experiments:
            print(f"[{e['id']}] {e['created_at'][:10]} | {e['mode']} | {e['decision']} | {e['summary'][:60]}")
    elif cmd == "save":
        data = json.loads(sys.stdin.read())
        row_id = save_experiment(json.dumps(data), data.get("mode"), json.dumps(data.get("inputs", {})))
        print(f"Saved as id={row_id}")