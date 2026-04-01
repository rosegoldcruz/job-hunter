# ResumeBot

ResumeBot is a human-in-the-loop job hunt bot.

Flow:
1. Read your real resume file.
2. Build source-specific keyword pools from resume content plus configured overrides.
3. Scrape and search job sources.
4. Store and dedupe jobs in SQLite.
5. Send new jobs to Telegram.
6. Approve, save, or trash from Telegram.
7. Generate a tailored application packet.
8. Final approve from Telegram.
9. Send only when a real contact email exists.

## Why this version is safer than the old one
- No fake callback buttons.
- No hardcoded hiring email.
- No pretending the bot is reading your resume when it isn't.
- No auto-send without a second human approval.
- Real status tracking in a database.

## Commands

Run the Telegram bot:

```bash
python -m app.orchestrator bot
```

Sync fresh jobs into the queue:

```bash
python -m app.orchestrator sync
```

Build packet manually for one job:

```bash
python -m app.orchestrator packet --job-id 12
```

Send application manually for one job:

```bash
python -m app.orchestrator apply --job-id 12
```

## Telegram commands
- `/start` help
- `/sync` fetch and queue jobs
- `/queue` show pending jobs
- `/stats` show counts

## Source-specific keyword pools
- `CRAIGSLIST_KEYWORDS` should stay broader and messier because Craigslist titles are loose and speed matters.
- `INDEED_KEYWORDS` should stay mid-precision because listings are more structured.
- `LINKEDIN_KEYWORDS` are kept separate for a future LinkedIn adapter; this rebuild does not pretend LinkedIn scraping already works.
- `REMOTE_KEYWORDS` should stay literal because substring-heavy remote sources punish overly long phrases.

## Notes
- Scraping job boards is brittle. The source adapter pattern is deliberate so you can swap selectors or replace a board with an API without rewriting the rest of the system.
- This project only auto-sends when it has a real recipient email and you hit final approval.
- If a source blocks scraping, the rest of the workflow still works.
- LinkedIn keywords are configured, but the LinkedIn adapter is intentionally not implemented yet.