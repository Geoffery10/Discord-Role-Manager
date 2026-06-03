# Rolm Web Dashboard

A dark-themed web dashboard for managing the Discord Role Manager (Rolm) bot.

## Run

```bash
cd /root/projects/Discord-Role-Manager
.venv/bin/uvicorn dashboard.main:app --host 0.0.0.0 --port 8080
```

## Features

- **Overview** — stats cards + next upcoming birthday
- **Users** — searchable/filterable user table from sqlite db
- **Roles** — edit reaction role mappings live (roles.json)
- **Birthdays** — calendar view, month filter, today highlight
- **Guilds** — birthday channel / role configuration viewer
- **Logs** — tail the latest bot logs in real-time

## Stack

- FastAPI + Jinja2 + Uvicorn
- Vanilla JS frontend
- Dark Discord-inspired CSS

## Notes

- The logger (`utils/logger.py`) now also writes to `rolm.log` so the dashboard can read it.
- Dashboard expects `discord.db`, `roles.json`, `birthday.json`, and `rolm.log` in the project root.
