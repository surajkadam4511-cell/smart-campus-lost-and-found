from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from flask_mysqldb import MySQL
from flask_mail import Mail, Message
import os
import io
import re
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'enter'
app.config['MYSQL_DB'] = 'campus_lost_found'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = app.config['MAIL_USERNAME']

mail = Mail(app)

app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

with app.app_context():
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(120) UNIQUE NOT NULL,
                phone VARCHAR(15) NOT NULL,
                password VARCHAR(200) NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INT AUTO_INCREMENT PRIMARY KEY,
                type VARCHAR(10) NOT NULL,
                title VARCHAR(100) NOT NULL,
                category VARCHAR(50) NOT NULL,
                location VARCHAR(100) NOT NULL,
                date_reported VARCHAR(20) NOT NULL,
                description TEXT NOT NULL,
                hidden_details TEXT NOT NULL,
                image_url VARCHAR(200),
                reporter_email VARCHAR(120) NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS claims (
                id INT AUTO_INCREMENT PRIMARY KEY,
                item_id INT NOT NULL,
                item_title VARCHAR(100) NOT NULL,
                user_email VARCHAR(120) NOT NULL,
                proof_details TEXT NOT NULL,
                status VARCHAR(20) DEFAULT 'pending'
            )
        """)
        mysql.connection.commit()
        cursor.close()
    except Exception as e:
        print(f"Database Initialization Note: {e}")

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()

        email_regex = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not re.match(email_regex, email):
            flash('Invalid email address format.', 'danger')
            return redirect(url_for('signup'))

        if not phone.isdigit() or len(phone) != 10:
            flash('Phone number must be exactly 10 digits.', 'danger')
            return redirect(url_for('signup'))

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return redirect(url_for('signup'))

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        existing_user = cursor.fetchone()
        if existing_user:
            cursor.close()
            flash('Email is already registered. Please sign in.', 'danger')
            return redirect(url_for('signup'))

        hashed_password = generate_password_hash(password)
        cursor.execute("INSERT INTO users (name, email, phone, password) VALUES (%s, %s, %s, %s)", 
                       (name, email, phone, hashed_password))
        mysql.connection.commit()
        cursor.close()

        flash('Registration successful! Please sign in.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()

        if user and check_password_hash(user['password'], password):
            session['user'] = user['email']
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if username == 'admin' and password == 'admin123':
            session['admin'] = 'admin'
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid administrator credentials.', 'danger')
            return redirect(url_for('admin_login'))

    return render_template('admin_login.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    user_email = session['user']
    cursor = mysql.connection.cursor()
    
    cursor.execute("SELECT phone FROM users WHERE email = %s", (user_email,))
    user_record = cursor.fetchone()
    phone_number = user_record['phone'] if user_record else 'Not Registered'

    search_query = request.args.get('search', '')
    if search_query:
        query = "SELECT * FROM items WHERE title LIKE %s OR category LIKE %s OR location LIKE %s"
        like_term = f"%{search_query}%"
        cursor.execute(query, (like_term, like_term, like_term))
    else:
        cursor.execute("SELECT * FROM items")
    items = cursor.fetchall()

    cursor.execute("SELECT * FROM claims WHERE user_email = %s", (user_email,))
    my_claims = cursor.fetchall()
    cursor.close()

    return render_template('index.html', 
                           user=user_email, 
                           phone=phone_number,
                           items=items, 
                           my_claims=my_claims)

@app.route('/report', methods=['GET', 'POST'])
def report_item():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        file = request.files.get('image')
        image_filename = None
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            image_filename = f"{int(datetime.now().timestamp())}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
            image_filename = f"uploads/{image_filename}"

        cursor = mysql.connection.cursor()
        cursor.execute("""
            INSERT INTO items (type, title, category, location, date_reported, description, hidden_details, image_url, reporter_email)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            request.form.get('type'),
            request.form.get('title'),
            request.form.get('category'),
            request.form.get('location'),
            request.form.get('date_reported'),
            request.form.get('description'),
            request.form.get('hidden_details'),
            image_filename,
            session['user']
        ))
        mysql.connection.commit()
        cursor.close()
        flash('Item reported successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('report.html')

@app.route('/claim', methods=['POST'])
def claim_item():
    if 'user' not in session:
        return redirect(url_for('login'))

    item_id = request.form.get('item_id')
    cursor = mysql.connection.cursor()
    
    cursor.execute("SELECT * FROM items WHERE id = %s", (item_id,))
    item = cursor.fetchone()
    if not item:
        cursor.close()
        flash('Item not found.', 'danger')
        return redirect(url_for('dashboard'))

    cursor.execute("""
        INSERT INTO claims (item_id, item_title, user_email, proof_details, status)
        VALUES (%s, %s, %s, %s, 'pending')
    """, (item['id'], item['title'], session['user'], request.form.get('proof_details')))
    mysql.connection.commit()
    cursor.close()

    flash('Claim request submitted successfully for administrator review.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/admin-dashboard')
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    cursor = mysql.connection.cursor()
    cursor.execute("SELECT * FROM items")
    items = cursor.fetchall()

    cursor.execute("""
        SELECT claims.*, items.hidden_details AS original_hidden_details, items.image_url 
        FROM claims 
        JOIN items ON claims.item_id = items.id
    """)
    claims = cursor.fetchall()

    cursor.execute("SELECT id, name, email, phone FROM users")
    users = cursor.fetchall()
    cursor.close()

    return render_template('admin.html', items=items, claims=claims, users=users)

@app.route('/admin/delete-item/<int:item_id>')
def delete_item(item_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM items WHERE id = %s", (item_id,))
    mysql.connection.commit()
    cursor.close()
    flash('Item listing deleted successfully by admin.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete-user/<int:user_id>')
def delete_user(user_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
    mysql.connection.commit()
    cursor.close()
    flash('User account deleted successfully by admin.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/approve-claim/<int:claim_id>')
def approve_claim(claim_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT claims.*, items.id AS item_id_val, items.title AS item_title, 
               items.reporter_email, users.phone AS reporter_phone
        FROM claims 
        JOIN items ON claims.item_id = items.id 
        LEFT JOIN users ON items.reporter_email = users.email
        WHERE claims.id = %s
    """, (claim_id,))
    claim = cursor.fetchone()

    if claim:
        cursor.execute("UPDATE claims SET status = 'approved' WHERE id = %s", (claim_id,))
        cursor.execute("DELETE FROM items WHERE id = %s", (claim['item_id_val'],))
        
        mysql.connection.commit()
        cursor.close()

        try:
            reporter_email = claim['reporter_email'] or 'Not Provided'
            reporter_phone = claim['reporter_phone'] or 'Not Provided'

            msg = Message(
                subject="Claim Approved - Smart Campus Lost & Found",
                sender=app.config['MAIL_USERNAME'],
                recipients=[claim['user_email']]
            )
            msg.body = f"""Hello,

Your claim request for '{claim['item_title']}' has been APPROVED by the administrator!

You can contact the person who reported/found the item to collect it:
- Email: {reporter_email}
- Phone: {reporter_phone}

Please visit the campus office or coordinate with the reporter to retrieve your item.

Thank you,
Smart Campus Team"""
            mail.send(msg)
        except Exception as e:
            print(f"Email Error: {e}")
    else:
        cursor.close()

    flash('Claim approved, email notification sent with reporter details, and item removed from listings.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/reject-claim/<int:claim_id>')
def reject_claim(claim_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    cursor = mysql.connection.cursor()
    cursor.execute("UPDATE claims SET status = 'rejected' WHERE id = %s", (claim_id,))
    
    cursor.execute("SELECT * FROM claims WHERE id = %s", (claim_id,))
    claim = cursor.fetchone()
    
    mysql.connection.commit()
    cursor.close()

    if claim:
        try:
            msg = Message(
                subject="Claim Update - Smart Campus Lost & Found",
                sender=app.config['MAIL_USERNAME'],
                recipients=[claim['user_email']]
            )
            msg.body = f"Hello,\n\nRegrettably, your claim request for '{claim['item_title']}' was rejected after administrative review.\n\nThank you,\nSmart Campus Team"
            mail.send(msg)
        except Exception as e:
            print(f"Email Error: {e}")

    flash('Claim rejected and email notification sent.', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/download-report-pdf')
def download_report_pdf():
    if 'admin' not in session and 'user' not in session:
        return redirect(url_for('login'))

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.drawString(100, 750, "Smart Campus Lost & Found - Summary Report")
    p.drawString(100, 730, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    p.showPage()
    p.save()
    buffer.seek(0)
    
    return send_file(buffer, as_attachment=True, download_name='lost_and_found_report.pdf', mimetype='application/pdf')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out safely.', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)