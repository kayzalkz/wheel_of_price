from flask import Flask, render_template, request, redirect, url_for, session, jsonify, make_response
import sqlite3, random, json
from datetime import datetime
import locale
import csv, io 
import hashlib, os 

# Set the locale for currency formatting
try:
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, '')
    except locale.Error:
        pass 

app = Flask(__name__)
app.secret_key = "secret_key"

DB = "wheel.db"

# --- SECURITY FUNCTIONS ---
def hash_password(password):
    """Hashes a password using SHA-256 with a random salt."""
    salt = os.urandom(32)
    hashed_password = hashlib.pbkdf2_hmac(
        'sha256', 
        password.encode('utf-8'), 
        salt, 
        100000
    )
    return salt.hex(), hashed_password.hex()

def check_password(stored_salt_hex, stored_hash_hex, provided_password):
    """Verifies a password against a stored salt and hash."""
    stored_salt = bytes.fromhex(stored_salt_hex)
    stored_hash = bytes.fromhex(stored_hash_hex)
    
    hashed_provided_password = hashlib.pbkdf2_hmac(
        'sha256', 
        provided_password.encode('utf-8'), 
        stored_salt, 
        100000
    )
    return hashed_provided_password == stored_hash

# --- CUSTOM JINJA2 FILTER ---
def format_currency_filter(value):
    """Formats an integer or float as a number with commas (e.g., 35,500)"""
    if value is None:
        return "0"
    try:
        return locale.format_string("%d", int(value), grouping=True)
    except:
        return f"{value:,.0f}"

app.jinja_env.filters['format_currency'] = format_currency_filter

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE,
                        used INTEGER DEFAULT 0
                    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS prizes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        amount INTEGER,
                        quantity INTEGER
                    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS winners (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT,
                        prize INTEGER,
                        date TEXT
                    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS admin (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE,
                        password TEXT,
                        salt TEXT
                    )''')
    conn.commit() 

    cursor = conn.execute("PRAGMA table_info(admin)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'salt' not in columns:
        conn.execute("ALTER TABLE admin ADD COLUMN salt TEXT")
        conn.commit()

    cur = conn.execute("SELECT * FROM admin WHERE username='admin'")
    admin_user = cur.fetchone()

    if not admin_user:
        salt, hashed_password = hash_password("admin") 
        conn.execute("INSERT INTO admin (username, password, salt) VALUES (?,?,?)", ("admin", hashed_password, salt))
        conn.commit()
    elif admin_user['password'] == 'admin' and admin_user['salt'] is None:
        salt, hashed_password = hash_password("admin")
        conn.execute("UPDATE admin SET password=?, salt=? WHERE username='admin'", (hashed_password, salt))
        conn.commit()
    
    cur = conn.execute("SELECT * FROM prizes")
    if not cur.fetchone():
        prizes = [(1000,10),(1500,8),(2000,5),(2500,4),(3000,3),(4000,1),(5000,1)]
        conn.executemany("INSERT INTO prizes (amount,quantity) VALUES (?,?)", prizes)
        conn.commit()
        
    conn.close()

@app.route('/')
def index():
    conn = get_db()
    users = conn.execute("SELECT * FROM users").fetchall()
    winners = conn.execute("SELECT * FROM winners ORDER BY id DESC LIMIT 5").fetchall()
    
    prizes_data = conn.execute("SELECT amount, quantity FROM prizes").fetchall()
    
    prize_amounts = len(prizes_data)
    total_prizes = sum(p['quantity'] for p in prizes_data)
    total_prize_pool = sum(p['amount'] * p['quantity'] for p in prizes_data)

    conn.close()
    return render_template('index.html', users=users, winners=winners, prize_amounts=prize_amounts, total_prizes=total_prizes, total_prize_pool=total_prize_pool)

@app.route('/add_user', methods=['POST'])
def add_user():
    name = request.form['name']
    conn = get_db()
    try:
        conn.execute("INSERT INTO users (name) VALUES (?)", (name,))
        conn.commit()
    except:
        pass
    conn.close()
    return redirect('/')

@app.route('/select_user/<int:user_id>')
def select_user(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    
    # --- FIX: Check total remaining prizes ---
    # Fetch the sum of the quantity column (or 0 if NULL)
    prizes_left = conn.execute("SELECT SUM(quantity) FROM prizes").fetchone()[0] or 0
    
    # Only allow spin if user is unused AND at least one prize remains
    if user and user['used'] == 0 and prizes_left > 0:
        session['user'] = dict(user)
        conn.close()
        return redirect('/wheel')
        
    conn.close()
    return redirect('/') # Redirect to index if user is ineligible or prizes are empty

@app.route('/wheel')
def wheel():
    if 'user' not in session:
        return redirect('/')
    conn = get_db()
    
    prizes_raw = conn.execute("SELECT amount, quantity FROM prizes WHERE quantity > 0").fetchall()
    prizes = [dict(row) for row in prizes_raw]
    
    winners = conn.execute("SELECT * FROM winners ORDER BY id DESC LIMIT 5").fetchall()
    conn.close()
    return render_template("wheel.html", user=session['user'], prizes=prizes, winners=winners)

@app.route('/spin', methods=['POST'])
def spin():
    user = session.get('user')
    if not user: return jsonify({'error': 'No user'})

    conn = get_db()
    prizes = conn.execute("SELECT * FROM prizes WHERE quantity > 0").fetchall()
    
    user_status = conn.execute("SELECT used FROM users WHERE id=?", (user['id'],)).fetchone()
    if user_status and user_status['used'] == 1:
        conn.close()
        session.pop('user', None) 
        return jsonify({'error': 'User has already spun.'})
    
    weighted = [p['amount'] for p in prizes for _ in range(p['quantity'])]
    if not weighted:
        conn.close()
        return jsonify({'error': 'No prizes left'})

    won_prize = random.choice(weighted)

    conn.execute("UPDATE prizes SET quantity=quantity-1 WHERE amount=? AND quantity>0", (won_prize,))
    conn.execute("UPDATE users SET used=1 WHERE id=?", (user['id'],))
    conn.execute("INSERT INTO winners (name,prize,date) VALUES (?,?,?)", (user['name'], won_prize, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

    session.pop('user', None)
    return jsonify({'prize': won_prize})

# ---------- Admin ----------

@app.route('/admin_login', methods=['GET','POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db()
        admin_row = conn.execute("SELECT username, password, salt FROM admin WHERE username=?", (username,)).fetchone()
        conn.close()
        
        if admin_row and check_password(admin_row['salt'], admin_row['password'], password):
            session['admin'] = username
            return redirect('/admin_manage')
        return render_template('admin_login.html', error='Invalid credentials')
    return render_template('admin_login.html')

@app.route('/admin_manage', methods=['GET','POST'])
def admin_manage():
    if 'admin' not in session:
        return redirect('/admin_login')

    conn = get_db()
    users = conn.execute("SELECT * FROM users").fetchall()
    prizes = conn.execute("SELECT * FROM prizes").fetchall()
    winners = conn.execute("SELECT * FROM winners ORDER BY id DESC LIMIT 10").fetchall()
    
    total_prizes = sum(p['quantity'] for p in prizes)
    total_prize_pool = sum(p['amount'] * p['quantity'] for p in prizes)
    
    conn.close()
    return render_template("admin_manage.html", users=users, prizes=prizes, winners=winners, total_prizes=total_prizes, total_prize_pool=total_prize_pool)

@app.route('/admin/export_winners_csv')
def export_winners_csv():
    if 'admin' not in session:
        return redirect('/admin_login')
    
    conn = get_db()
    winner_data = conn.execute("SELECT name, prize, date FROM winners ORDER BY date DESC").fetchall()
    conn.close()

    si = io.StringIO()
    cw = csv.writer(si)
    
    cw.writerow(['Name', 'Prize Amount', 'Date Won'])
    
    for row in winner_data:
        cw.writerow([row['name'], row['prize'], row['date']])
    
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=wheel_winners_{}.csv".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    output.headers["Content-type"] = "text/csv"
    return output

@app.route('/admin/add_prize', methods=['POST'])
def admin_add_prize():
    if 'admin' not in session: return redirect('/admin_login')
    amount = request.form['amount']
    quantity = request.form['quantity']
    conn = get_db()
    conn.execute("INSERT INTO prizes (amount,quantity) VALUES (?,?)", (amount,quantity))
    conn.commit()
    conn.close()
    return redirect('/admin_manage')

@app.route('/admin/delete_prize/<int:id>')
def admin_delete_prize(id):
    if 'admin' not in session: return redirect('/admin_login')
    conn = get_db()
    conn.execute("DELETE FROM prizes WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect('/admin_manage')

@app.route('/admin/add_user', methods=['POST'])
def admin_add_user():
    if 'admin' not in session: return redirect('/admin_login')
    name = request.form['name']
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO users (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()
    return redirect('/admin_manage')

@app.route('/admin/delete_user/<int:id>')
def admin_delete_user(id):
    if 'admin' not in session: return redirect('/admin_login')
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect('/admin_manage')

@app.route('/admin/reset')
def admin_reset():
    if 'admin' not in session: return redirect('/admin_login')
    conn = get_db()
    conn.execute("UPDATE users SET used=0")
    conn.execute("DELETE FROM winners")
    conn.commit()
    conn.close()
    return redirect('/admin_manage')

@app.route('/admin/change_password', methods=['POST'])
def admin_change_password():
    if 'admin' not in session: return redirect('/admin_login')
    new_password = request.form['password']
    conn = get_db()
    
    salt, hashed_password = hash_password(new_password)
    conn.execute("UPDATE admin SET password=?, salt=? WHERE username='admin'", (hashed_password, salt))
    conn.commit()
    conn.close()
    return redirect('/admin_manage')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/')



if __name__ == '__main__': # <--- Line 326 (or near it)
    init_db()              # <--- Line 327, must be indented
    app.run(debug=True, host='0.0.0.0')
