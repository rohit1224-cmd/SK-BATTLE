# SK BATTLE — safer configuration

## Local setup (Windows PowerShell)

1. Install Python 3.10+.
2. In this folder, run:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

3. Open `.env` and set:
   - `APP_PIN=3569`
   - `ADMIN_PASSWORD=your chosen admin password`
   - `SECRET_KEY=` a long random value. Generate one with:
     `python -c "import secrets; print(secrets.token_hex(32))"`
   - Keep `COOKIE_SECURE=false` for local HTTP testing.

4. Run `python app.py`, then open `http://127.0.0.1:5000`.

## Render deployment

Build command: `pip install -r requirements.txt`
Start command: `gunicorn app:app`

In Render → your Web Service → Environment, add:
- `APP_PIN` = `3569`
- `ADMIN_PASSWORD` = your chosen admin password
- `SECRET_KEY` = a fresh random secret (do not reuse a public value)
- `COOKIE_SECURE` = `true`

Do not put secrets in source code, README, GitHub commits, or screenshots.

## Important security limits

- No app can be guaranteed impossible to hack.
- The 4-digit PIN is a shared access gate, not strong authentication. Do not rely on it to protect valuable data.
- The admin password you requested is a memorable phrase and may be guessable; choose a longer unique password for a public service.
- This package intentionally excludes the local database and site data. Your existing users, balances, tournament settings, and uploaded media are not included; back them up privately before deployment and use persistent storage/a managed database for production.
- This is a configuration hardening pass, not a full professional security audit. Add rate limiting, CSRF protection, backups, and a managed persistent database before handling real payments or valuable user data.
