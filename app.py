from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from pathlib import Path
import json, os, sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Secrets must be provided through environment variables (never commit them to GitHub).
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("Missing SECRET_KEY. Set it in your local .env file or hosting environment.")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
)
DATA = Path("data")
UPLOADS = Path("static/uploads")
DATA.mkdir(exist_ok=True)
UPLOADS.mkdir(parents=True, exist_ok=True)
DB = DATA / "site.json"
USER_DB = DATA / "users.db"
def db_conn():
    conn = sqlite3.connect(USER_DB)
    conn.row_factory = sqlite3.Row
    return conn
with db_conn() as conn:
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL,
        game_name TEXT NOT NULL DEFAULT '',
        email TEXT NOT NULL COLLATE NOCASE UNIQUE, password_hash TEXT NOT NULL,
        balance INTEGER NOT NULL DEFAULT 0, user_code TEXT UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
with db_conn() as conn:
    # Migrate databases created by the earlier starter version.
    cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "balance" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN balance INTEGER NOT NULL DEFAULT 0")
    if "game_name" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN game_name TEXT NOT NULL DEFAULT ''")
    if "user_code" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN user_code TEXT")
    # Assign stable public IDs to accounts from older versions.
    for row in conn.execute("SELECT id FROM users WHERE user_code IS NULL OR user_code=''").fetchall():
        conn.execute("UPDATE users SET user_code=? WHERE id=?", (f'SK{row[0]:06d}', row[0]))
    conn.execute("""CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        amount INTEGER NOT NULL, kind TEXT NOT NULL, note TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS deposit_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        amount_inr INTEGER NOT NULL, requested_coins INTEGER NOT NULL,
        transaction_ref TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'Pending', approved_coins INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, reviewed_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS registrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        match_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'Registered',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, match_id))""")
DEFAULT = {
    "app_name": "SK BATTLE",
    "notice": "Welcome to SK BATTLE Tournament",
    "apk_url": "",
    "matches": [
        {"id": 1, "title": "Solo Battle", "game": "FREE FIRE", "date": "2026-10-01", "time": "8:00 PM", "entry": "₹20", "prize": "₹500", "slots": "48/48", "status": "Registration Open", "room_id": "", "room_password": "", "image": ""}
    ],
    "payments": []
}
def load_data():
    if not DB.exists():
        save_data(DEFAULT)
    try:
        return json.loads(DB.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT.copy()
def save_data(data):
    DB.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def enrich_matches(data):
    """Attach live registration counts and normalized slot limits to matches."""
    with db_conn() as conn:
        counts = {row["match_id"]: row["n"] for row in conn.execute(
            "SELECT match_id, COUNT(*) AS n FROM registrations WHERE status='Registered' GROUP BY match_id"
        ).fetchall()}
    for match in data.get("matches", []):
        try:
            limit = int(match.get("max_slots", 0) or 0)
        except (TypeError, ValueError):
            limit = 0
        # Migrate old "current/maximum" slot text when no explicit limit exists.
        if limit <= 0:
            import re
            parts = re.findall(r"\\d+", str(match.get("slots", "")))
            limit = int(parts[-1]) if len(parts) >= 2 else (int(parts[0]) if parts else 48)
        count = int(counts.get(int(match.get("id", 0)), 0))
        match["max_slots"] = max(1, limit)
        match["registered_count"] = count
        match["slots"] = f"{count}/{match['max_slots']}"
        if count >= match["max_slots"] and str(match.get("status", "")).lower() in ("registration open", "open", "registration is open"):
            match["status"] = "Slot Full"
    return data



# --- App PIN gate (PIN 3569). Change APP_PIN in the hosting environment to override.
from flask import abort

@app.before_request
def require_app_pin():
    endpoint = request.endpoint or ""
    if endpoint == "app_pin" or endpoint == "static":
        return None
    if not session.get("pin_verified"):
        return redirect(url_for("app_pin"))

@app.route("/app-pin", methods=["GET", "POST"])
def app_pin():
    if session.get("pin_verified"):
        return redirect(url_for("home"))
    if request.method == "POST":
        expected = os.environ.get("APP_PIN")
        if expected and __import__("hmac").compare_digest(request.form.get("pin", ""), expected):
            session["pin_verified"] = True
            return redirect(url_for("home"))
        flash("ভুল PIN। আবার চেষ্টা করো।")
    return render_template("pin.html")

@app.route("/")
def home():
    if not session.get("user_id"):
        return redirect(url_for("user_login"))

    data = load_data()
    with db_conn() as conn:
        user = conn.execute("SELECT id, username, email, balance, user_code FROM users WHERE id=?", (session["user_id"],)).fetchone()
    return render_template("index.html", data=data, user=user)

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username=request.form.get("username","").strip()
        game_name=request.form.get("game_name","").strip()
        email=request.form.get("email","").strip().lower()
        password=request.form.get("password","")
        confirm=request.form.get("confirm_password","")
        if not username or not game_name or not email or not password: flash("Please fill in all fields.")
        elif len(password)<8: flash("Password must be at least 8 characters long.")
        elif password != confirm: flash("The passwords do not match.")
        else:
            try:
                with db_conn() as conn:
                    cur=conn.execute("INSERT INTO users(username,game_name,email,password_hash) VALUES(?,?,?,?)",
                        (username,game_name,email,generate_password_hash(password)))
                    uid=cur.lastrowid
                    conn.execute("UPDATE users SET user_code=? WHERE id=?", (f"SK{uid:06d}", uid))
                session.clear(); session["pin_verified"] = True; session["user_id"]=uid
                return redirect(url_for("home"))
            except sqlite3.IntegrityError:
                flash("An account with this email already exists. Please log in.")
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def user_login():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower()
        password=request.form.get("password","")
        with db_conn() as conn:
            user=conn.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
        if user and check_password_hash(user["password_hash"],password):
            session.clear(); session["pin_verified"] = True; session["user_id"]=user["id"]
            return redirect(url_for("home"))
        flash("Incorrect email or password.")
    return render_template("user_login.html")

@app.route("/logout")
def user_logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        # Set ADMIN_PASSWORD in the local .env file or hosting environment.
        password = os.environ.get("ADMIN_PASSWORD")
        supplied = request.form.get("password", "")
        if password and __import__("hmac").compare_digest(supplied, password):
            session["admin"] = True
            return redirect(url_for("admin"))
        flash("Password is incorrect.")
    return render_template("login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("home"))

def admin_required():
    return session.get("admin") is True

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not admin_required():
        return redirect(url_for("admin_login"))
    data = load_data()
    if request.method == "POST":
        data["app_name"] = request.form.get("app_name", "SK BATTLE").strip() or "SK BATTLE"
        data["notice"] = request.form.get("notice", "").strip()
        data["apk_url"] = request.form.get("apk_url", "").strip()
        save_data(data)
        flash("App settings saved.")
        return redirect(url_for("admin"))
    with db_conn() as conn:
        users=conn.execute("SELECT id, username, email, balance, user_code, created_at FROM users ORDER BY id DESC").fetchall()
        deposits=conn.execute("SELECT d.*,u.username,u.user_code,u.email FROM deposit_requests d JOIN users u ON u.id=d.user_id ORDER BY CASE d.status WHEN 'Pending' THEN 0 ELSE 1 END, d.id DESC LIMIT 200").fetchall()
    return render_template("admin.html", data=data, users=users, deposits=deposits)

@app.route("/admin/match/add", methods=["POST"])
def add_match():
    if not admin_required(): return redirect(url_for("admin_login"))
    data = load_data()
    next_id = max([m.get("id", 0) for m in data["matches"]] + [0]) + 1
    match = {
        "id": next_id, "title": request.form.get("title","New Match").strip(),
        "game": request.form.get("game","FREE FIRE").strip(),
        "date": request.form.get("date",""), "time": request.form.get("time",""),
        "entry": request.form.get("entry","Free").strip(), "prize": request.form.get("prize","").strip(),
        "slots": "0/" + str(max(1, int(request.form.get("max_slots", "48") or 48))), "max_slots": max(1, int(request.form.get("max_slots", "48") or 48)), "status": request.form.get("status","Registration Open").strip(),
        "room_id": request.form.get("room_id","").strip(), "room_password": request.form.get("room_password","").strip(),
        "image": ""
    }
    img = request.files.get("image")
    if img and img.filename:
        name = secure_filename(img.filename)
        dest = UPLOADS / f"{next_id}_{name}"
        img.save(dest)
        match["image"] = "/" + str(dest).replace("\\\\", "/")
    data["matches"].insert(0, match)
    save_data(data)
    flash("Match added.")
    return redirect(url_for("admin"))

@app.route("/admin/match/<int:match_id>/edit", methods=["POST"])
def edit_match(match_id):
    if not admin_required(): return redirect(url_for("admin_login"))
    data = load_data()
    match = next((m for m in data["matches"] if m.get("id") == match_id), None)
    if match:
        for key in ["title","game","date","time","entry","prize","status","room_id","room_password"]:
            match[key] = request.form.get(key, match.get(key,"")).strip()
        img = request.files.get("image")
        if img and img.filename:
            name = secure_filename(img.filename)
            dest = UPLOADS / f"{match_id}_{name}"
            img.save(dest)
            match["image"] = "/" + str(dest).replace("\\\\", "/")
        save_data(data)
        flash("Match updated.")
    return redirect(url_for("admin"))

@app.route("/admin/match/<int:match_id>/delete", methods=["POST"])
def delete_match(match_id):
    if not admin_required(): return redirect(url_for("admin_login"))
    data = load_data()
    data["matches"] = [m for m in data["matches"] if m.get("id") != match_id]
    save_data(data)
    flash("Match deleted.")
    return redirect(url_for("admin"))

@app.route("/wallet")
def wallet():
    if not session.get("user_id"):
        return redirect(url_for("user_login"))
    with db_conn() as conn:
        user = conn.execute("SELECT id, username, email, balance, user_code FROM users WHERE id=?", (session["user_id"],)).fetchone()
        txs = conn.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 100", (session["user_id"],)).fetchall()
        deposits = conn.execute("SELECT * FROM deposit_requests WHERE user_id=? ORDER BY id DESC LIMIT 50", (session["user_id"],)).fetchall()
    return render_template("wallet.html", user=user, txs=txs, deposits=deposits)

@app.route("/wallet/deposit-request", methods=["POST"])
def create_deposit_request():
    if not session.get("user_id"):
        return redirect(url_for("user_login"))
    try:
        amount = int(request.form.get("amount_inr", "0"))
        coins = int(request.form.get("requested_coins", "0"))
    except ValueError:
        flash("Please enter a valid amount and coin quantity."); return redirect(url_for("wallet"))
    ref = request.form.get("transaction_ref", "").strip()
    note = request.form.get("note", "").strip()
    if amount < 1 or coins < 1 or amount > 10000000 or coins > 10000000 or not ref:
        flash("Please enter a valid amount, coin quantity, and transaction ID."); return redirect(url_for("wallet"))
    with db_conn() as conn:
        conn.execute("INSERT INTO deposit_requests(user_id,amount_inr,requested_coins,transaction_ref,note) VALUES(?,?,?,?,?)",
                     (session["user_id"], amount, coins, ref, note))
    flash("Your coin request has been sent to the Admin. Coins will be added after verification.")
    return redirect(url_for("wallet"))

@app.route("/admin/deposit/<int:req_id>/approve", methods=["POST"])
def approve_deposit(req_id):
    if not admin_required(): return redirect(url_for("admin_login"))
    try: coins = int(request.form.get("approved_coins", "0"))
    except ValueError: coins = 0
    if coins < 1 or coins > 10000000:
        flash("Coin amount must be between 1 and 10,000,000."); return redirect(url_for("admin"))
    with db_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM deposit_requests WHERE id=?", (req_id,)).fetchone()
        if not row or row["status"] != "Pending":
            conn.rollback(); flash("Request not found or it has already been reviewed."); return redirect(url_for("admin"))
        conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (coins, row["user_id"]))
        conn.execute("INSERT INTO transactions(user_id,amount,kind,note) VALUES(?,?,?,?)",
                     (row["user_id"], coins, "Deposit Approved", f"Deposit Request #{req_id}; Ref: {row['transaction_ref']}"))
        conn.execute("UPDATE deposit_requests SET status='Approved',approved_coins=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=?", (coins, req_id))
        conn.commit()
    flash(f"Request #{req_id} approved — {coins} SK Coins have been added to the user's wallet.")
    return redirect(url_for("admin"))

@app.route("/admin/deposit/<int:req_id>/reject", methods=["POST"])
def reject_deposit(req_id):
    if not admin_required(): return redirect(url_for("admin_login"))
    with db_conn() as conn:
        conn.execute("UPDATE deposit_requests SET status='Rejected',reviewed_at=CURRENT_TIMESTAMP WHERE id=? AND status='Pending'", (req_id,))
        if conn.total_changes == 0:
            flash("Request not found or it has already been reviewed.")
        else:
            flash(f"Request #{req_id} has been rejected.")
    return redirect(url_for("admin"))

@app.route("/my-matches")
def my_matches():
    if not session.get("user_id"):
        return redirect(url_for("user_login"))
    data = load_data()
    with db_conn() as conn:
        rows = conn.execute("SELECT match_id,status,created_at FROM registrations WHERE user_id=? ORDER BY id DESC", (session["user_id"],)).fetchall()
    registered=[]
    for row in rows:
        match = next((m for m in data["matches"] if int(m.get("id",0)) == row["match_id"]), None)
        if match:
            registered.append({"match": match, "status": row["status"], "created_at": row["created_at"]})
    return render_template("my_matches.html", registered=registered)

@app.route("/match/<int:match_id>/join", methods=["POST"])
def join_match(match_id):
    if not session.get("user_id"):
        return redirect(url_for("user_login"))
    data=load_data()
    match=next((m for m in data["matches"] if int(m.get("id",0))==match_id),None)
    if not match:
        flash("Tournament not found."); return redirect(url_for("home"))
    raw=str(match.get("entry","0"))
    import re
    digits=re.sub(r"[^0-9]", "", raw)
    fee=int(digits or 0)
    if str(match.get("status", "")).lower() not in ("registration open", "open", "registration is open"):
        flash("Registration for this tournament is closed."); return redirect(url_for("home"))
    try:
        with db_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM registrations WHERE user_id=? AND match_id=?",(session["user_id"],match_id)).fetchone():
                conn.rollback(); flash("You have already joined this tournament."); return redirect(url_for("my_matches"))
            try:
                max_slots = int(match.get("max_slots", 0) or 0)
            except (TypeError, ValueError):
                max_slots = 0
            if max_slots <= 0:
                import re
                nums = re.findall(r"\\d+", str(match.get("slots", "")))
                max_slots = int(nums[-1]) if len(nums) >= 2 else (int(nums[0]) if nums else 48)
            count = conn.execute("SELECT COUNT(*) FROM registrations WHERE match_id=? AND status='Registered'", (match_id,)).fetchone()[0]
            if count >= max_slots:
                conn.rollback()
                flash("This tournament is full. Registration is closed.")
                return redirect(url_for("home"))
            u=conn.execute("SELECT balance FROM users WHERE id=?",(session["user_id"],)).fetchone()
            if not u or u["balance"] < fee:
                conn.rollback(); flash(f"Insufficient SK Coins. Entry fee: {fee} SK Coins."); return redirect(url_for("wallet"))
            conn.execute("UPDATE users SET balance=balance-? WHERE id=?",(fee,session["user_id"]))
            conn.execute("INSERT INTO registrations(user_id,match_id) VALUES(?,?)",(session["user_id"],match_id))
            if fee:
                conn.execute("INSERT INTO transactions(user_id,amount,kind,note) VALUES(?,?,?,?)",(session["user_id"],-fee,"Entry Fee",f"Tournament: {match['title']}"))
            conn.commit()
        flash("You have successfully joined the tournament!")
    except sqlite3.IntegrityError:
        flash("You have already joined this tournament.")
    return redirect(url_for("my_matches"))

@app.route("/admin/wallet/credit", methods=["POST"])
def admin_credit():
    if not admin_required(): return redirect(url_for("admin_login"))
    try:
        uid=int(request.form.get("user_id","")); amount=int(request.form.get("amount","0"))
    except ValueError:
        flash("Please enter a valid user and coin amount."); return redirect(url_for("admin"))
    if amount <= 0 or amount > 10000000:
        flash("Coin amount must be between 1 and 10,000,000 SK Coins."); return redirect(url_for("admin"))
    with db_conn() as conn:
        u=conn.execute("SELECT id FROM users WHERE id=?",(uid,)).fetchone()
        if not u:
            flash("User not found."); return redirect(url_for("admin"))
        conn.execute("UPDATE users SET balance=balance+? WHERE id=?",(amount,uid))
        conn.execute("INSERT INTO transactions(user_id,amount,kind,note) VALUES(?,?,?,?)",(uid,amount,"Admin Credit","Admin added SK Coin"))
    flash(f"{amount} SK Coins have been added to the user's wallet.")
    return redirect(url_for("admin"))

@app.route("/admin/wallet/debit", methods=["POST"])
def admin_debit():
    if not admin_required():
        return redirect(url_for("admin_login"))
    try:
        uid = int(request.form.get("user_id", "0"))
        amount = int(request.form.get("amount", "0"))
    except ValueError:
        flash("Please enter a valid user ID and coin amount.")
        return redirect(url_for("admin"))
    if amount <= 0 or amount > 10000000:
        flash("Coin amount must be between 1 and 10,000,000.")
        return redirect(url_for("admin"))
    with db_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        user = conn.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            conn.rollback()
            flash("User not found.")
            return redirect(url_for("admin"))
        if user["balance"] < amount:
            conn.rollback()
            flash("User does not have enough coins.")
            return redirect(url_for("admin"))
        conn.execute("UPDATE users SET balance=balance-? WHERE id=?", (amount, uid))
        conn.execute("INSERT INTO transactions(user_id,amount,kind,note) VALUES(?,?,?,?)",
                     (uid, -amount, "Admin Debit", "Coins deducted by Admin"))
        conn.commit()
    flash(f"{amount} SK Coins deducted from user #{uid}.")
    return redirect(url_for("admin"))

@app.route("/api/data")
def api_data():
    return jsonify(load_data())

if __name__ == "__main__":
    app.run(debug=False)
