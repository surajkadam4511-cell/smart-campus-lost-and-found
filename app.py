import psycopg2
import psycopg2.extras
import urllib.parse as urlparse
import pymysql
pymysql.install_as_MySQLdb()
import ssl
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from flask_mysqldb import MySQL
from flask_mail import Mail, Message
import os
import io
import re
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# MySQL Configurations
# --- Aiven Cloud MySQL Direct Connection ---
def get_db_connection():
    return psycopg2.connect(
        os.getenv('DATABASE_URL'),
        cursor_factory=psycopg2.extras.DictCursor
    )

# Flask-Mail Configurations
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'adminoffice1028@gmail.com'
app.config['MAIL_PASSWORD'] = 'uqwl znbj wwzz gnqx'
app.config['MAIL_DEFAULT_SENDER'] = 'adminoffice1028@gmail.com'

mail = Mail(app)

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Helper Regex for Email
EMAIL_REGEX = r'^[\w\.-]+@[\w\.-]+\.\w+$'

# ----------------- AUTHENTICATION ROUTES -----------------

@app.route('/')
def index():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
    
    cur = mysql.connection.cursor()
    search_query = request.args.get('search', '')
    
    if search_query:
        cur.execute("SELECT * FROM items WHERE status = 'active' AND (title LIKE %s OR category LIKE %s OR location LIKE %s)", 
                    ('%' + search_query + '%', '%' + search_query + '%', '%' + search_query + '%'))
    else:
        cur.execute("SELECT * FROM items WHERE status = 'active'")
    items = cur.fetchall()
    
    cur.execute("""
        SELECT claims.*, items.title as item_title, items.image_url 
        FROM claims 
        JOIN items ON claims.item_id = items.id 
        WHERE claims.claimant_email = %s
    """, (session['user'],))
    my_claims = cur.fetchall()
    
    cur.execute("SELECT email, phone, profile_pic FROM users WHERE email = %s", (session['user'],))
    user_profile = cur.fetchone()
    
    cur.close()
    return render_template('index.html', items=items, my_claims=my_claims, user_profile=user_profile, user=session['user'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        if not email or not password:
            return render_template('login.html', is_admin_portal=False, error="Both email and password are required.")
        
        if not re.match(EMAIL_REGEX, email):
            return render_template('login.html', is_admin_portal=False, error="Please enter a valid email address.")
        
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s AND password = %s", (email, password))
        user = cur.fetchone()
        cur.close()
        
        if user:
            is_admin_val = user.get('is_admin', 0)
            if str(is_admin_val) in ['1', 'True', 'true']:
                return render_template('login.html', is_admin_portal=False, error="This is the Student Portal. Please use the Admin Login.")
            
            session['user'] = user['email']
            session['is_admin'] = False
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', is_admin_portal=False, error="Invalid Student Credentials")
            
    return render_template('login.html', is_admin_portal=False)

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        if not email or not password:
            return render_template('login.html', is_admin_portal=True, error="Both email and password are required.")
        
        if not re.match(EMAIL_REGEX, email):
            return render_template('login.html', is_admin_portal=True, error="Please enter a valid email address.")
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s AND password = %s", (email, password))
        user = cur.fetchone()
        cur.close()
        
        if user:
            is_admin_val = user.get('is_admin', 0)
            if str(is_admin_val) not in ['1', 'True', 'true']:
                return render_template('login.html', is_admin_portal=True, error="Access Denied: Admin credentials required.")
            
            session['user'] = user['email']
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('login.html', is_admin_portal=True, error="Invalid Admin Credentials")
            
    return render_template('login.html', is_admin_portal=True)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()
        
        # 1. Empty field checks
        if not email or not phone or not password:
            return render_template('signup.html', error="All fields are required.")
        
        # 2. Email validation
        if not re.match(EMAIL_REGEX, email):
            return render_template('signup.html', error="Please enter a valid email address.")
        
        # 3. Mobile number validation (Must be numbers only and exactly 10 digits)
        if not phone.isdigit() or len(phone) != 10:
            return render_template('signup.html', error="Mobile number must be exactly 10 digits.")
        
        # 4. Password validation (Minimum 6 characters)
        if len(password) < 6:
            return render_template('signup.html', error="Password must be at least 6 characters long.")
        
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        existing_user = cur.fetchone()
        
        if existing_user:
            cur.close()
            return render_template('signup.html', error="Email is already registered. Please sign in.")
            
        cur.execute("""
            INSERT INTO users (email, phone, password, is_admin) 
            VALUES (%s, %s, %s, 0)
        """, (email, phone, password))
        mysql.connection.commit()
        cur.close()
        
        return redirect(url_for('login'))
        
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ----------------- PROFILE & ITEM ROUTES -----------------

@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'user' not in session:
        return redirect(url_for('login'))
        
    if 'profile_pic' in request.files:
        file = request.files['profile_pic']
        if file and file.filename != '':
            filename = secure_filename("profile_" + session['user'].replace('@', '_') + "_" + file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            profile_pic_url = f"uploads/{filename}"
            
            cur = mysql.connection.cursor()
            cur.execute("UPDATE users SET profile_pic = %s WHERE email = %s", (profile_pic_url, session['user']))
            mysql.connection.commit()
            cur.close()
            
    return redirect(url_for('dashboard'))

@app.route('/report_item', methods=['POST'])
def report_item():
    if 'user' not in session:
        return redirect(url_for('login'))
        
    title = request.form.get('title')
    category = request.form.get('category')
    location = request.form.get('location')
    date_reported = request.form.get('date_reported')
    item_type = request.form.get('type')
    hidden_details = request.form.get('hidden_details')
    description = request.form.get('description')
    reporter_email = session['user']
    
    if not hidden_details or not description or 'image' not in request.files:
        return redirect(url_for('dashboard'))
        
    file = request.files['image']
    if not file or file.filename == '':
        return redirect(url_for('dashboard'))
        
    filename = secure_filename(file.filename)
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    image_url = f"uploads/{filename}"
            
    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO items (title, category, location, date_reported, type, hidden_details, description, image_url, reporter_email, status) 
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'active')
    """, (title, category, location, date_reported, item_type, hidden_details, description, image_url, reporter_email))
    mysql.connection.commit()
    cur.close()
    
    return redirect(url_for('dashboard'))

@app.route('/claim_item', methods=['POST'])
@app.route('/claim_item/<int:item_id>', methods=['POST'])
def claim_item(item_id=None):
    if 'user' not in session:
        return redirect(url_for('login'))
        
    if not item_id:
        item_id = request.form.get('item_id')
        
    proof_details = request.form.get('proof_details') or request.form.get('proof')
    claimant_email = session['user']
    
    if item_id and proof_details:
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO claims (item_id, claimant_email, proof_details, status) 
            VALUES (%s, %s, %s, 'pending')
        """, (item_id, claimant_email, proof_details))
        mysql.connection.commit()
        cur.close()
    
    return redirect(url_for('dashboard'))

# ----------------- ADMIN DASHBOARD & FEATURES -----------------

@app.route('/admin')
def admin_dashboard():
    if 'user' not in session or not session.get('is_admin'):
        return redirect(url_for('login'))
        
    cur = mysql.connection.cursor()
    
    cur.execute("SELECT COUNT(*) as count FROM items WHERE type='lost' AND status='active'")
    active_lost = cur.fetchone()['count']
    
    cur.execute("SELECT COUNT(*) as count FROM items WHERE type='found' AND status='active'")
    active_found = cur.fetchone()['count']
    
    cur.execute("SELECT COUNT(*) as count FROM claims WHERE status='pending'")
    pending_claims = cur.fetchone()['count']
    
    cur.execute("SELECT COUNT(*) as count FROM items WHERE status='resolved'")
    resolved_count = cur.fetchone()['count']
    
    cur.execute("""
        SELECT claims.*, items.title as item_title, items.hidden_details, items.image_url 
        FROM claims 
        JOIN items ON claims.item_id = items.id
    """)
    claims = cur.fetchall()
    
    cur.execute("SELECT * FROM items")
    all_items = cur.fetchall()
    
    cur.execute("SELECT * FROM users")
    all_users = cur.fetchall()
    
    cur.execute("SELECT category, COUNT(*) as count FROM items GROUP BY category")
    category_stats = cur.fetchall()
    
    cur.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 10")
    audit_logs = cur.fetchall()
    
    cur.close()
    
    return render_template('admin.html', 
                           active_lost=active_lost, 
                           active_found=active_found, 
                           pending_claims=pending_claims, 
                           resolved_count=resolved_count,
                           claims=claims, 
                           all_items=all_items, 
                           all_users=all_users, 
                           category_stats=category_stats,
                           audit_logs=audit_logs)

@app.route('/admin/verify/<int:claim_id>', methods=['POST'])
def admin_verify_claim(claim_id):
    if 'user' not in session or not session.get('is_admin'):
        return jsonify({'success': False})
        
    data = request.get_json()
    action = data.get('action')
    status = 'approved' if action == 'approve' else 'rejected'
    
    cur = mysql.connection.cursor()
    cur.execute("UPDATE claims SET status = %s WHERE id = %s", (status, claim_id))
    
    if status == 'approved':
        cur.execute("""
            SELECT c.claimant_email, i.id as item_id, i.title as item_title, i.reporter_email, u.phone as reporter_phone 
            FROM claims c
            JOIN items i ON c.item_id = i.id 
            LEFT JOIN users u ON i.reporter_email = u.email
            WHERE c.id = %s
        """, (claim_id,))
        claim = cur.fetchone()
        
        if claim:
            cur.execute("UPDATE items SET status = 'resolved' WHERE id = %s", (claim['item_id'],))
            try:
                item_name = claim['item_title']
                rep_email = claim['reporter_email']
                rep_phone = claim['reporter_phone'] if claim['reporter_phone'] else 'Not Provided'
                
                msg = Message("Smart Campus Claim Approved!", recipients=[claim['claimant_email']])
                msg.body = f"""Your claim has been verified and approved by the admin!

Item Details: {item_name}

Reporter Contact Information:
- Email: {rep_email}
- Mobile Number: {rep_phone}

Please reach out to the reporter or visit the campus office to collect your item."""
                
                mail.send(msg)
            except Exception as e:
                print(f"Email notification failed: {e}")

    elif status == 'rejected':
        cur.execute("""
            SELECT c.claimant_email, i.title as item_title 
            FROM claims c
            JOIN items i ON c.item_id = i.id 
            WHERE c.id = %s
        """, (claim_id,))
        claim = cur.fetchone()
        
        if claim:
            try:
                item_name = claim['item_title']
                
                msg = Message("Smart Campus Claim Status Update", recipients=[claim['claimant_email']])
                msg.body = f"""Hello,

Your claim for '{item_name}' has been rejected because the proof you provided was insufficient or could not be verified.

Please feel free to submit a new claim with valid proof details if you believe this is a mistake.

Smart Campus Team"""
                
                mail.send(msg)
            except Exception as e:
                print(f"Rejection email notification failed: {e}")

    cur.execute("INSERT INTO audit_logs (admin_email, action) VALUES (%s, %s)", 
                (session['user'], f"Claim #{claim_id} {status}"))
    mysql.connection.commit()
    cur.close()
    
    return jsonify({'success': True})

@app.route('/admin/download_report')
def admin_download_report():
    if 'user' not in session or not session.get('is_admin'):
        return redirect(url_for('login'))

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    p.setFont("Helvetica-Bold", 18)
    p.setFillColor(colors.HexColor("#1e293b"))
    p.drawString(50, height - 50, "Smart Campus Lost & Found - System Report")

    p.setFont("Helvetica", 10)
    p.setFillColor(colors.HexColor("#64748b"))
    p.drawString(50, height - 68, "Generated from Admin Dashboard Control Panel")
    
    p.setStrokeColor(colors.HexColor("#cbd5e1"))
    p.setLineWidth(1)
    p.line(50, height - 78, width - 50, height - 78)

    cur = mysql.connection.cursor()
    cur.execute("SELECT id, title, category, type, status, reporter_email FROM items")
    items_data = cur.fetchall()
    cur.close()

    y = height - 120
    p.setFont("Helvetica-Bold", 11)
    p.setFillColor(colors.HexColor("#0f172a"))
    p.drawString(50, y, "ID")
    p.drawString(90, y, "Title")
    p.drawString(230, y, "Category")
    p.drawString(320, y, "Type")
    p.drawString(380, y, "Status")
    p.drawString(450, y, "Reporter")
    
    y -= 15
    p.line(50, y, width - 50, y)
    y -= 20

    p.setFont("Helvetica", 10)
    p.setFillColor(colors.HexColor("#334155"))
    
    for item in items_data:
        if y < 50:
            p.showPage()
            y = height - 50
            p.setFont("Helvetica", 10)

        p.drawString(50, y, str(item['id']))
        p.drawString(90, y, str(item['title'][:25]))
        p.drawString(230, y, str(item['category']))
        p.drawString(320, y, str(item['type']).upper())
        p.drawString(380, y, str(item['status']))
        p.drawString(450, y, str(item['reporter_email'][:20]))
        y -= 20

    p.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name="smart_campus_report.pdf", mimetype="application/pdf")

@app.route('/admin/item/delete/<int:item_id>', methods=['POST'])
def admin_delete_item(item_id):
    if 'user' not in session or not session.get('is_admin'):
        return redirect(url_for('login'))
        
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM items WHERE id = %s", (item_id,))
    mysql.connection.commit()
    cur.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/user/delete/<int:user_id>', methods=['POST'])
def admin_delete_user(user_id):
    if 'user' not in session or not session.get('is_admin'):
        return redirect(url_for('login'))
        
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    mysql.connection.commit()
    cur.close()
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True)