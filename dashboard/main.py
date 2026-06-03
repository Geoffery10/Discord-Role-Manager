import os
import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime, date

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.requests import Request

# Ensure project root is on path for importing shared modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.discord_api import refresh_role_cache, get_role_name, get_cached_guild_roles

app = FastAPI(title="Rolm Dashboard")

# Static + templates
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

DB_PATH = PROJECT_ROOT / "discord.db"
ROLES_PATH = PROJECT_ROOT / "roles.json"
BIRTHDAY_PATH = PROJECT_ROOT / "birthday.json"
LOG_PATH = PROJECT_ROOT / "rolm.log"

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def db_conn():
    return sqlite3.connect(DB_PATH)

def read_json(path: Path):
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def write_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# ------------------------------------------------------------------
# Models
# ------------------------------------------------------------------
class RoleMap(BaseModel):
    roles: dict

# ------------------------------------------------------------------
# Pages
# ------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")

# ------------------------------------------------------------------
# API: Stats
# ------------------------------------------------------------------
@app.get("/api/stats")
async def stats():
    conn = db_conn()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM users")
    user_count = c.fetchone()[0]

    c.execute("SELECT COUNT(DISTINCT guild_id) FROM user_guilds")
    guild_count = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM user_guilds")
    member_count = c.fetchone()[0]

    conn.close()

    roles = read_json(ROLES_PATH)
    birthday_cfg = read_json(BIRTHDAY_PATH)
    # Count total roles across all guilds (support flat & guild-scoped)
    role_count = 0
    if roles:
        if any(isinstance(v, dict) for v in roles.values()):
            role_count = sum(len(v) for v in roles.values())
        else:
            role_count = len(roles)

    return {
        "users": user_count,
        "guilds": guild_count,
        "members": member_count,
        "reaction_roles": role_count,
        "birthday_guilds": len(birthday_cfg.get("guilds", [])),
    }

# ------------------------------------------------------------------
# API: Users
# ------------------------------------------------------------------
@app.get("/api/users")
async def users(q: str = "", guild_id: str = "", limit: int = 200, offset: int = 0):
    conn = db_conn()
    c = conn.cursor()

    base_sql = """
        SELECT u.user_id, u.username, u.birthday, u.tag,
               GROUP_CONCAT(ug.guild_id) as guild_ids
        FROM users u
        LEFT JOIN user_guilds ug ON u.user_id = ug.user_id
    """
    where_clauses = []
    params = []

    if q:
        where_clauses.append("(u.username LIKE ? OR u.user_id LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])
    if guild_id:
        where_clauses.append("u.user_id IN (SELECT user_id FROM user_guilds WHERE guild_id = ?)")
        params.append(guild_id)

    if where_clauses:
        base_sql += " WHERE " + " AND ".join(where_clauses)

    base_sql += " GROUP BY u.user_id ORDER BY u.username LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    c.execute(base_sql, params)
    rows = c.fetchall()
    conn.close()

    return {
        "users": [
            {
                "user_id": r[0],
                "username": r[1],
                "birthday": r[2],
                "tag": r[3],
                "guilds": r[4].split(",") if r[4] else [],
            }
            for r in rows
        ]
    }

# ------------------------------------------------------------------
# API: Roles
# ------------------------------------------------------------------
@app.get("/api/roles")
async def roles(guild_id: str = ""):
    data = read_json(ROLES_PATH)
    # Support old flat format
    if data and not any(isinstance(v, dict) for v in data.values()):
        data = {"254779349352448001": data}
    # Stringify role IDs so JS doesn't lose precision on 18-digit snowflakes
    for gid, mapping in data.items():
        data[gid] = {k: str(v) for k, v in mapping.items()}
    if guild_id:
        mapping = data.get(guild_id, {})
        enriched = []
        for emoji, role_id in mapping.items():
            name = get_role_name(guild_id, role_id)
            enriched.append({"emoji": emoji, "role_id": role_id, "role_name": name})
        return {"guild_id": guild_id, "roles": enriched}
    return data

@app.post("/api/roles/refresh")
async def refresh_roles():
    data = read_json(ROLES_PATH)
    if data and not any(isinstance(v, dict) for v in data.values()):
        guild_ids = ["254779349352448001"]
    else:
        guild_ids = list(data.keys())
    errors = {}
    for gid in guild_ids:
        try:
            await refresh_role_cache([gid])
        except Exception as e:
            errors[gid] = str(e)
    # Debug: return cache peek
    sample = {}
    for gid in guild_ids:
        cache = get_cached_guild_roles(gid)
        sample[gid] = {"role_count": len(cache), "first_keys": list(cache.keys())[:3]}
    return {"ok": True, "guilds": guild_ids, "errors": errors, "cache_peek": sample}

@app.post("/api/roles")
async def update_roles(data: RoleMap):
    raw = read_json(ROLES_PATH)
    # Support old flat format migration
    if raw and not any(isinstance(v, dict) for v in raw.values()):
        raw = {"254779349352448001": raw}
    # data.roles shape from frontend: {guild_id: {emoji: role_id, ...}, ...}
    # or flat if no guild selector was used (legacy safety)
    for gid, mapping in data.roles.items():
        raw[gid] = mapping
    write_json(ROLES_PATH, raw)
    return {"ok": True}

# ------------------------------------------------------------------
# API: Guilds
# ------------------------------------------------------------------
@app.get("/api/guilds")
async def guilds():
    cfg = read_json(BIRTHDAY_PATH)
    guild_list = cfg.get("guilds", [])
    # Ensure all snowflake IDs are strings so JS doesn't lose precision
    for g in guild_list:
        g["id"] = str(g.get("id", ""))
        g["birthday_channel"] = str(g.get("birthday_channel", ""))
        g["birthday_role"] = str(g.get("birthday_role", ""))
    return guild_list

# ------------------------------------------------------------------
# API: Birthdays
# ------------------------------------------------------------------
@app.get("/api/birthdays")
async def birthdays():
    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT user_id, username, birthday FROM users WHERE birthday != '00-00'")
    rows = c.fetchall()
    conn.close()

    today = date.today()
    bdays = []
    for uid, name, bday in rows:
        try:
            parsed = datetime.strptime(bday, "%m-%d").date()
            next_bday = parsed.replace(year=today.year)
            if next_bday < today:
                next_bday = parsed.replace(year=today.year + 1)
            delta = (next_bday - today).days
            bdays.append({
                "user_id": uid,
                "username": name,
                "birthday": bday,
                "month": parsed.month,
                "day": parsed.day,
                "days_till": delta,
            })
        except ValueError:
            continue

    bdays.sort(key=lambda x: (x["month"], x["day"]))
    return {"birthdays": bdays}

# ------------------------------------------------------------------
# API: Logs
# ------------------------------------------------------------------
@app.get("/api/logs")
async def logs(lines: int = 200):
    if not LOG_PATH.exists():
        return {"logs": []}
    with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()
    return {"logs": [ln.rstrip("\n") for ln in all_lines[-lines:]]}

# ------------------------------------------------------------------
# Run
# ------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
