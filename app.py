from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import qrcode, io, base64, json
import os
import secrets
import re
import hmac
import hashlib
import urllib.request
import urllib.error
import smtplib
from datetime import datetime, timedelta
from functools import wraps
from email.message import EmailMessage

try:
    import resend
except ImportError:
    resend = None

env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'pos-cafe-hackathon-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pos.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

SMTP_HOST = os.getenv('SMTP_HOST', '').strip()
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER', '').strip()
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '').strip()
SMTP_FROM = os.getenv('SMTP_FROM', SMTP_USER or 'no-reply@pos-cafe.local').strip()
SMTP_USE_TLS = os.getenv('SMTP_USE_TLS', '1').strip() != '0'
RESEND_API_KEY = os.getenv('RESEND_API_KEY', '').strip()
RESEND_FROM = os.getenv(
    'RESEND_FROM',
    os.getenv('EMAIL_FROM', 'POS Cafe <onboarding@resend.dev>')
).strip()
if RESEND_API_KEY and resend is not None:
    resend.api_key = RESEND_API_KEY

RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID', '').strip()
RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET', '').strip()
RAZORPAY_CURRENCY = os.getenv('RAZORPAY_CURRENCY', 'INR').strip().upper() or 'INR'
RAZORPAY_MERCHANT_NAME = os.getenv('RAZORPAY_MERCHANT_NAME', 'POS Cafe').strip() or 'POS Cafe'

PASSWORD_RESET_CODES = {}

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")
CORS(app)

# ─── Models ───────────────────────────────────────────────
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='cashier')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    products = db.relationship('Product', backref='category', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    description = db.Column(db.Text, default='')
    tax = db.Column(db.Float, default=0)
    unit = db.Column(db.String(20), default='pcs')
    active = db.Column(db.Boolean, default=True)

class Floor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    tables = db.relationship('Table', backref='floor', lazy=True)

class Table(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(10), nullable=False)
    seats = db.Column(db.Integer, default=4)
    floor_id = db.Column(db.Integer, db.ForeignKey('floor.id'))
    active = db.Column(db.Boolean, default=True)
    status = db.Column(db.String(20), default='free')  # free, occupied

class PaymentMethod(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # cash, digital, upi
    enabled = db.Column(db.Boolean, default=True)
    upi_id = db.Column(db.String(100), default='')

class Session(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    opened_at = db.Column(db.DateTime, default=datetime.utcnow)
    closed_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='open')
    closing_amount = db.Column(db.Float, default=0)
    user = db.relationship('User', backref='sessions')

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), nullable=False)
    table_id = db.Column(db.Integer, db.ForeignKey('table.id'), nullable=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(30), default='draft')  # draft, sent, paid
    payment_method = db.Column(db.String(30), default='')
    total = db.Column(db.Float, default=0)
    tip = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_to_kitchen_at = db.Column(db.DateTime, nullable=True)  # When sent to kitchen
    started_at = db.Column(db.DateTime, nullable=True)  # When kitchen starts preparing
    completed_at = db.Column(db.DateTime, nullable=True)  # When order is ready
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
    reviews = db.relationship('Review', backref='order', lazy=True, cascade='all, delete-orphan')
    table = db.relationship('Table', backref='orders')
    user = db.relationship('User', backref='orders')

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    product_name = db.Column(db.String(100))
    qty = db.Column(db.Integer, default=1)
    price = db.Column(db.Float, default=0)
    kitchen_status = db.Column(db.String(20), default='pending')  # pending, to_cook, preparing, completed
    started_at = db.Column(db.DateTime, nullable=True)  # When item preparation starts
    completed_at = db.Column(db.DateTime, nullable=True)  # When item is ready
    product = db.relationship('Product')

class KitchenTicket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    status = db.Column(db.String(20), default='to_cook')
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)  # When preparing starts
    completed_at = db.Column(db.DateTime, nullable=True)  # When all items completed
    order = db.relationship('Order')

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    rating = db.Column(db.Integer, default=5)  # 1-5 stars
    comment = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ─── Auth Helpers ──────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

def normalize_role(role):
    role = (role or 'cashier').strip().lower()
    if role == 'admin':
        return 'restaurant'
    if role in ('user', 'staff', 'pos'):
        return 'cashier'
    if role not in ('cashier', 'restaurant', 'kitchen', 'manager', 'customer'):
        return 'cashier'
    return role

def role_home(role):
    role = normalize_role(role)
    if role == 'restaurant':
        return url_for('admin_dashboard')
    if role == 'customer':
        return url_for('customer')
    return url_for('pos')

def page_login_required(allowed_roles=None, redirect_to=None):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('auth'))
            role = normalize_role(session.get('user_role'))
            if allowed_roles is not None:
                allowed = {normalize_role(r) for r in allowed_roles}
                if role not in allowed:
                    return redirect(redirect_to or role_home(role))
            return f(*args, **kwargs)
        return decorated
    return decorator

def staff_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'unauthorized'}), 401
        role = normalize_role(session.get('user_role'))
        if role == 'customer':
            return jsonify({'error': 'forbidden'}), 403
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth'))
        user = User.query.get(session['user_id'])
        if not user or normalize_role(user.role) != 'restaurant':
            return redirect(role_home(normalize_role(session.get('user_role'))))
        return f(*args, **kwargs)
    return decorated

def get_current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

def find_user_by_email(email):
    email = (email or '').strip()
    if not email:
        return None
    return User.query.filter(db.func.lower(User.email) == email.lower()).first()

def password_strength_issues(password, email=''):
    password = password or ''
    email = (email or '').strip().lower()
    issues = []

    if len(password) < 12:
        issues.append('at least 12 characters')
    if len(password) > 128:
        issues.append('no more than 128 characters')
    if re.search(r'\s', password):
        issues.append('no spaces')
    if not re.search(r'[a-z]', password):
        issues.append('a lowercase letter')
    if not re.search(r'[A-Z]', password):
        issues.append('an uppercase letter')
    if not re.search(r'\d', password):
        issues.append('a number')
    if not re.search(r'[^A-Za-z0-9]', password):
        issues.append('a symbol')

    common = {
        'password', 'password1', 'password123', 'admin123', 'welcome123',
        'qwerty123', 'letmein123', 'restaurant123', 'cafe12345'
    }
    if password.lower() in common:
        issues.append('not a common password')

    if email and '@' in email:
        local_part = email.split('@', 1)[0]
        if local_part and local_part in password.lower():
            issues.append('not contain your email name')

    return issues

def strong_password_error(password, email=''):
    issues = password_strength_issues(password, email)
    if not issues:
        return None
    if issues == ['at least 12 characters']:
        return 'Password must be at least 12 characters long.'
    return (
        'Password must be at least 12 characters and include an uppercase letter, '
        'a lowercase letter, a number, and a symbol. It must also avoid spaces, '
        'common passwords, and your email name.'
    )

def send_reset_email(email, otp):
    subject = 'POS Cafe password reset code'
    body = (
        f'Your POS Cafe password reset code is {otp}. '
        'This code expires in 10 minutes.'
    )

    if RESEND_API_KEY:
        if resend is None:
            return False
        try:
            result = resend.Emails.send({
                'from': RESEND_FROM,
                'to': [email],
                'subject': subject,
                'text': body,
                'html': f'<p>{body}</p>',
            })
            if isinstance(result, dict):
                return bool(result.get('id'))
            return bool(getattr(result, 'id', result))
        except Exception:
            return False

    if not SMTP_HOST:
        return False

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = SMTP_FROM
    msg['To'] = email
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
        if SMTP_USE_TLS:
            smtp.starttls()
        if SMTP_USER:
            smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.send_message(msg)
    return True

def call_razorpay_api(path, payload):
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        return None, 'Razorpay keys are not configured'

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        f'https://api.razorpay.com/v1/{path.lstrip("/")}',
        data=data,
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Basic ' + base64.b64encode(
                f'{RAZORPAY_KEY_ID}:{RAZORPAY_KEY_SECRET}'.encode('utf-8')
            ).decode('ascii'),
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode('utf-8')
            return json.loads(body), None
    except urllib.error.HTTPError as exc:
        try:
            return None, json.loads(exc.read().decode('utf-8'))
        except Exception:
            return None, {'error': f'Razorpay HTTP {exc.code}'}
    except Exception as exc:
        return None, {'error': str(exc)}

def verify_razorpay_signature(order_id, payment_id, signature):
    if not RAZORPAY_KEY_SECRET:
        return False
    message = f'{order_id}|{payment_id}'.encode('utf-8')
    expected = hmac.new(
        RAZORPAY_KEY_SECRET.encode('utf-8'),
        message,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature or '')

def cleanup_reset_codes():
    now = datetime.utcnow()
    expired = [email for email, record in PASSWORD_RESET_CODES.items() if record['expires_at'] <= now]
    for email in expired:
        PASSWORD_RESET_CODES.pop(email, None)

# ─── Auth Routes ───────────────────────────────────────────
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(role_home(session.get('user_role')))
    return render_template('landing.html')

@app.route('/auth')
def auth():
    if 'user_id' in session:
        return redirect(role_home(session.get('user_role')))
    return render_template('auth.html')

@app.route('/api/signup', methods=['POST'])
def signup():
    d = request.json
    if User.query.filter_by(email=d['email']).first():
        return jsonify({'error': 'Email already exists'}), 400
    password_error = strong_password_error(d.get('password', ''), d.get('email', ''))
    if password_error:
        return jsonify({'error': password_error}), 400
    role = normalize_role(d.get('role', 'cashier'))
    # Map unsupported roles to the closest valid role.
    if role not in ('cashier', 'restaurant', 'kitchen', 'manager', 'customer'):
        role = 'cashier'
    u = User(name=d['name'], email=d['email'], password=generate_password_hash(d['password'], method='scrypt'), role=role)
    db.session.add(u)
    db.session.commit()
    session['user_id'] = u.id
    session['user_name'] = u.name
    session['user_role'] = role
    return jsonify({'ok': True, 'name': u.name, 'role': u.role})

@app.route('/api/login', methods=['POST'])
def login():
    d = request.json
    u = User.query.filter_by(email=d['email']).first()
    if not u or not check_password_hash(u.password, d['password']):
        return jsonify({'error': 'Invalid credentials'}), 401
    session['user_id'] = u.id
    session['user_name'] = u.name
    session['user_role'] = normalize_role(u.role)
    return jsonify({'ok': True, 'name': u.name, 'role': session['user_role']})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/password-reset/request', methods=['POST'])
def password_reset_request():
    cleanup_reset_codes()
    d = request.json or {}
    email = (d.get('email') or '').strip()
    if not email:
        return jsonify({'error': 'Email is required'}), 400

    user = find_user_by_email(email)
    if not user:
        return jsonify({'error': 'No account found for that email'}), 404

    otp = f'{secrets.randbelow(1000000):06d}'
    PASSWORD_RESET_CODES[email.lower()] = {
        'otp': otp,
        'expires_at': datetime.utcnow() + timedelta(minutes=10),
        'attempts': 0,
    }

    email_sent = False
    try:
        email_sent = send_reset_email(user.email, otp)
    except Exception:
        return jsonify({'error': 'Email provider rejected the message. Check RESEND_FROM and verified domain.'}), 500

    if not email_sent:
        PASSWORD_RESET_CODES.pop(email.lower(), None)
        return jsonify({'error': 'Unable to send reset code right now'}), 500

    return jsonify({'ok': True, 'message': 'Reset code sent to your email'})

@app.route('/api/password-reset/complete', methods=['POST'])
def password_reset_complete():
    cleanup_reset_codes()
    d = request.json or {}
    email = (d.get('email') or '').strip()
    otp = (d.get('otp') or '').strip()
    password = d.get('password') or ''
    confirm_password = d.get('confirm_password') or ''

    if not email or not otp or not password or not confirm_password:
        return jsonify({'error': 'Fill all fields'}), 400
    if password != confirm_password:
        return jsonify({'error': 'Passwords do not match'}), 400
    password_error = strong_password_error(password, email)
    if password_error:
        return jsonify({'error': password_error}), 400

    record = PASSWORD_RESET_CODES.get(email.lower())
    if not record:
        return jsonify({'error': 'Reset code not found or expired'}), 400
    if record['expires_at'] < datetime.utcnow():
        PASSWORD_RESET_CODES.pop(email.lower(), None)
        return jsonify({'error': 'Reset code expired'}), 400
    if record['otp'] != otp:
        record['attempts'] += 1
        if record['attempts'] >= 5:
            PASSWORD_RESET_CODES.pop(email.lower(), None)
            return jsonify({'error': 'Too many invalid attempts'}), 400
        return jsonify({'error': 'Invalid reset code'}), 400

    user = find_user_by_email(email)
    if not user:
        PASSWORD_RESET_CODES.pop(email.lower(), None)
        return jsonify({'error': 'Account not found'}), 404

    user.password = generate_password_hash(password, method='scrypt')
    db.session.commit()
    PASSWORD_RESET_CODES.pop(email.lower(), None)
    return jsonify({'ok': True})

# ─── Pages ────────────────────────────────────────────────
@app.route('/pos')
@page_login_required(allowed_roles=('cashier', 'kitchen', 'manager', 'restaurant'))
def pos():
    return render_template(
        'pos.html',
        user_name=session.get('user_name'),
        user_role=session.get('user_role'),
    )

@app.route('/backend')
@page_login_required(allowed_roles=('restaurant',))
def backend():
    return render_template(
        'backend.html',
        user_name=session.get('user_name'),
        user_role=session.get('user_role'),
    )

@app.route('/admin')
@admin_required
def admin_dashboard():
    return render_template(
        'admin_dashboard.html',
        user_name=session.get('user_name'),
    )

@app.route('/kitchen')
@page_login_required(allowed_roles=('cashier', 'kitchen', 'manager', 'restaurant'))
def kitchen():
    return render_template('kitchen.html', user_role=session.get('user_role'))

@app.route('/customer')
@page_login_required(allowed_roles=('customer',))
def customer():
    return render_template('customer.html', user_role=session.get('user_role'))

@app.route('/dashboard')
@page_login_required(allowed_roles=('restaurant',))
def dashboard():
    return render_template(
        'dashboard.html',
        user_name=session.get('user_name'),
        user_role=session.get('user_role'),
    )

# ─── API: Products ─────────────────────────────────────────
@app.route('/api/products', methods=['GET'])
def get_products():
    cats = Category.query.all()
    result = []
    for c in cats:
        prods = [{'id':p.id,'name':p.name,'price':p.price,'description':p.description,'tax':p.tax,'unit':p.unit} for p in c.products if p.active]
        if prods:
            result.append({'id':c.id,'name':c.name,'products':prods})
    return jsonify(result)

@app.route('/api/products/all', methods=['GET'])
@staff_required
def get_all_products():
    products = Product.query.all()
    cats = Category.query.all()
    return jsonify({
        'products': [{'id':p.id,'name':p.name,'price':p.price,'category_id':p.category_id,'description':p.description,'tax':p.tax,'unit':p.unit,'active':p.active} for p in products],
        'categories': [{'id':c.id,'name':c.name} for c in cats]
    })

@app.route('/api/products', methods=['POST'])
@staff_required
def add_product():
    d = request.json
    cat = Category.query.filter_by(name=d.get('category','')).first()
    if not cat:
        cat = Category(name=d.get('category','General'))
        db.session.add(cat)
        db.session.flush()
    p = Product(name=d['name'], price=float(d['price']), category_id=cat.id,
                description=d.get('description',''), tax=float(d.get('tax',0)), unit=d.get('unit','pcs'))
    db.session.add(p)
    db.session.commit()
    return jsonify({'ok':True,'id':p.id})

@app.route('/api/products/<int:pid>', methods=['PUT'])
@staff_required
def update_product(pid):
    p = Product.query.get_or_404(pid)
    d = request.json
    p.name = d.get('name', p.name)
    p.price = float(d.get('price', p.price))
    p.description = d.get('description', p.description)
    p.tax = float(d.get('tax', p.tax))
    p.active = d.get('active', p.active)
    db.session.commit()
    return jsonify({'ok':True})

@app.route('/api/products/<int:pid>', methods=['DELETE'])
@staff_required
def delete_product(pid):
    p = Product.query.get_or_404(pid)
    p.active = False
    db.session.commit()
    return jsonify({'ok':True})

# ─── API: Floors & Tables ──────────────────────────────────
@app.route('/api/floors', methods=['GET'])
def get_floors():
    floors = Floor.query.all()
    result = []
    for f in floors:
        tables = [{'id':t.id,'number':t.number,'seats':t.seats,'status':t.status,'active':t.active} for t in f.tables if t.active]
        result.append({'id':f.id,'name':f.name,'tables':tables})
    return jsonify(result)

@app.route('/api/floors', methods=['POST'])
@staff_required
def add_floor():
    d = request.json
    f = Floor(name=d['name'])
    db.session.add(f)
    db.session.commit()
    return jsonify({'ok':True,'id':f.id})

@app.route('/api/tables', methods=['POST'])
@staff_required
def add_table():
    d = request.json
    t = Table(number=d['number'], seats=int(d.get('seats',4)), floor_id=int(d['floor_id']))
    db.session.add(t)
    db.session.commit()
    return jsonify({'ok':True,'id':t.id})

@app.route('/api/tables/<int:tid>', methods=['DELETE'])
@staff_required
def delete_table(tid):
    t = Table.query.get_or_404(tid)
    t.active = False
    db.session.commit()
    return jsonify({'ok':True})

# ─── API: Payment Methods ──────────────────────────────────
@app.route('/api/payment-methods', methods=['GET'])
def get_payment_methods():
    methods = PaymentMethod.query.all()
    return jsonify([{'id':m.id,'name':m.name,'type':m.type,'enabled':m.enabled,'upi_id':m.upi_id} for m in methods])

@app.route('/api/payment-methods/<int:mid>', methods=['PUT'])
@staff_required
def update_payment_method(mid):
    m = PaymentMethod.query.get_or_404(mid)
    d = request.json
    m.enabled = d.get('enabled', m.enabled)
    m.upi_id = d.get('upi_id', m.upi_id)
    db.session.commit()
    return jsonify({'ok':True})

@app.route('/api/razorpay/order', methods=['POST'])
@staff_required
def create_razorpay_order():
    d = request.json or {}
    order_id = d.get('order_id')
    if not order_id:
        return jsonify({'error': 'order_id is required'}), 400

    order = Order.query.get_or_404(order_id)
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        return jsonify({'error': 'Razorpay keys are not configured'}), 400

    amount_paise = int(round(float(order.total) * 100))
    payload = {
        'amount': amount_paise,
        'currency': RAZORPAY_CURRENCY,
        'receipt': order.order_number,
        'payment_capture': 1,
        'notes': {
            'order_id': str(order.id),
            'order_number': order.order_number,
            'source': 'pos-cafe-localhost',
        },
    }
    result, err = call_razorpay_api('orders', payload)
    if err:
        message = err.get('error') if isinstance(err, dict) else str(err)
        return jsonify({'error': message or 'Unable to create Razorpay order'}), 400

    return jsonify({
        'ok': True,
        'razorpay_order_id': result.get('id'),
        'amount': result.get('amount'),
        'currency': result.get('currency'),
        'key_id': RAZORPAY_KEY_ID,
        'merchant_name': RAZORPAY_MERCHANT_NAME,
        'order_number': order.order_number,
        'customer_name': session.get('user_name', 'Customer'),
    })

@app.route('/api/razorpay/verify', methods=['POST'])
@staff_required
def verify_razorpay_payment():
    d = request.json or {}
    order_id = d.get('razorpay_order_id')
    payment_id = d.get('razorpay_payment_id')
    signature = d.get('razorpay_signature')
    order_number = d.get('order_number')
    if not order_id or not payment_id or not signature:
        return jsonify({'error': 'Missing Razorpay verification fields'}), 400
    if not verify_razorpay_signature(order_id, payment_id, signature):
        return jsonify({'error': 'Invalid Razorpay signature'}), 400
    return jsonify({'ok': True, 'order_number': order_number})

# ─── API: QR Code ──────────────────────────────────────────
@app.route('/api/qr/<string:upi_id>/<float:amount>')
def generate_qr(upi_id, amount):
    upi_string = f"upi://pay?pa={upi_id}&am={amount:.2f}&cu=INR"
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(upi_string)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()
    return jsonify({'qr': f'data:image/png;base64,{b64}', 'upi_string': upi_string})

@app.route('/qr.jpeg')
def qr_image():
    return send_from_directory(os.path.dirname(__file__), 'qr.jpeg')

# ─── API: Sessions ─────────────────────────────────────────
@app.route('/api/sessions/current', methods=['GET'])
@staff_required
def current_session():
    s = Session.query.filter_by(user_id=session['user_id'], status='open').first()
    if s:
        return jsonify({'id':s.id,'opened_at':s.opened_at.isoformat(),'status':s.status})
    return jsonify({'id':None})

@app.route('/api/sessions/open', methods=['POST'])
@staff_required
def open_session():
    existing = Session.query.filter_by(user_id=session['user_id'], status='open').first()
    if existing:
        return jsonify({'id':existing.id,'opened_at':existing.opened_at.isoformat()})
    s = Session(user_id=session['user_id'])
    db.session.add(s)
    db.session.commit()
    return jsonify({'id':s.id,'opened_at':s.opened_at.isoformat()})

@app.route('/api/sessions/close', methods=['POST'])
@staff_required
def close_session():
    s = Session.query.filter_by(user_id=session['user_id'], status='open').first()
    if s:
        s.status = 'closed'
        s.closed_at = datetime.utcnow()
        total = sum(o.total for o in Order.query.filter_by(session_id=s.id, status='paid').all())
        s.closing_amount = total
        db.session.commit()
    return jsonify({'ok':True})

# ─── API: Orders ───────────────────────────────────────────
@app.route('/api/orders', methods=['POST'])
@staff_required
def create_order():
    d = request.json
    s = Session.query.filter_by(user_id=session['user_id'], status='open').first()
    if not s:
        return jsonify({'error':'No open session'}), 400
    count = Order.query.count() + 1
    order_num = f"ORD-{count:04d}"
    total = sum(item['price'] * item['qty'] for item in d['items'])
    o = Order(order_number=order_num, table_id=d.get('table_id'), session_id=s.id,
              user_id=session['user_id'], total=total)
    db.session.add(o)
    db.session.flush()
    for item in d['items']:
        oi = OrderItem(order_id=o.id, product_id=item['product_id'],
                       product_name=item['name'], qty=item['qty'], price=item['price'])
        db.session.add(oi)
    if d.get('table_id'):
        t = Table.query.get(d['table_id'])
        if t: t.status = 'occupied'
    db.session.commit()
    return jsonify({'ok':True,'id':o.id,'order_number':order_num})

@app.route('/api/orders/<int:oid>/send-kitchen', methods=['POST'])
@staff_required
def send_to_kitchen(oid):
    o = Order.query.get_or_404(oid)
    o.status = 'sent'
    o.sent_to_kitchen_at = datetime.utcnow()  # Track when order is sent to kitchen
    kt = KitchenTicket(order_id=oid)
    db.session.add(kt)
    for item in o.items:
        item.kitchen_status = 'to_cook'
    db.session.commit()
    ticket_data = {
        'id': kt.id,
        'order_number': o.order_number,
        'table': o.table.number if o.table else 'Takeaway',
        'status': 'to_cook',
        'total': o.total,
        'sent_at': kt.sent_at.isoformat(),
        'items': [{'id':i.id,'name':i.product_name,'qty':i.qty,'price':i.price,'status':i.kitchen_status} for i in o.items]
    }
    socketio.emit('new_ticket', ticket_data)
    socketio.emit('order_update', {'order_number': o.order_number, 'status': 'preparing'})
    return jsonify({'ok':True})

@app.route('/api/orders/<int:oid>/pay', methods=['POST'])
@staff_required
def pay_order(oid):
    o = Order.query.get_or_404(oid)
    d = request.json
    o.status = 'paid'
    o.payment_method = d.get('method','cash')
    o.tip = d.get('tip', 0) or 0  # Add tip support
    if o.table:
        o.table.status = 'free'
    db.session.commit()
    socketio.emit('order_paid', {'order_number': o.order_number, 'total': o.total, 'tip': o.tip, 'method': o.payment_method})
    return jsonify({'ok':True})

@app.route('/api/orders/table/<int:tid>', methods=['GET'])
@staff_required
def get_table_order(tid):
    o = Order.query.filter_by(table_id=tid).filter(Order.status.in_(['draft','sent'])).first()
    if not o:
        return jsonify({'order': None})
    return jsonify({'order': {
        'id': o.id, 'order_number': o.order_number, 'status': o.status, 'total': o.total,
        'items': [{'id':i.id,'product_id':i.product_id,'name':i.product_name,'qty':i.qty,'price':i.price} for i in o.items]
    }})

# ─── API: Kitchen ──────────────────────────────────────────
@app.route('/api/kitchen/tickets', methods=['GET'])
def get_tickets():
    tickets = KitchenTicket.query.filter(KitchenTicket.status != 'completed').order_by(KitchenTicket.sent_at).all()
    result = []
    for kt in tickets:
        o = kt.order
        total_price = sum(i.qty * i.price for i in o.items)
        
        # Calculate time elapsed in each stage
        now = datetime.utcnow()
        time_in_preparation = 0
        if kt.started_at:
            time_in_preparation = int((now - kt.started_at).total_seconds() / 60)
        
        result.append({
            'id': kt.id,
            'order_number': o.order_number,
            'table': o.table.number if o.table else 'Takeaway',
            'status': kt.status,
            'sent_at': kt.sent_at.isoformat(),
            'started_at': kt.started_at.isoformat() if kt.started_at else None,
            'total': total_price,
            'time_in_prep': time_in_preparation,
            'items': [{
                'id':i.id,
                'name':i.product_name,
                'qty':i.qty,
                'price':i.price,
                'status':i.kitchen_status,
                'started_at': i.started_at.isoformat() if i.started_at else None,
                'completed_at': i.completed_at.isoformat() if i.completed_at else None
            } for i in o.items]
        })
    return jsonify(result)

@app.route('/api/kitchen/tickets/<int:kid>/advance', methods=['POST'])
@staff_required
def advance_ticket(kid):
    kt = KitchenTicket.query.get_or_404(kid)
    o = kt.order
    stages = ['to_cook','preparing','completed']
    idx = stages.index(kt.status) if kt.status in stages else 0
    if idx < len(stages)-1:
        new_stage = stages[idx+1]
        kt.status = new_stage
        
        # Track timestamps
        if new_stage == 'preparing':
            kt.started_at = datetime.utcnow()
            o.started_at = datetime.utcnow()
            for item in o.items:
                if item.kitchen_status == 'to_cook':
                    item.kitchen_status = 'preparing'
                    item.started_at = datetime.utcnow()
        elif new_stage == 'completed':
            kt.completed_at = datetime.utcnow()
            o.completed_at = datetime.utcnow()
            for item in o.items:
                if item.kitchen_status != 'completed':
                    item.kitchen_status = 'completed'
                    item.completed_at = datetime.utcnow()
        
        db.session.commit()
        socketio.emit('ticket_update', {'id': kid, 'status': kt.status, 'started_at': kt.started_at.isoformat() if kt.started_at else None})
        socketio.emit('order_update', {'order_number': o.order_number, 'status': new_stage, 'started_at': o.started_at.isoformat() if o.started_at else None, 'completed_at': o.completed_at.isoformat() if o.completed_at else None})
    return jsonify({'ok':True,'status':kt.status})

@app.route('/api/kitchen/items/<int:item_id>/complete', methods=['POST'])
@staff_required
def mark_item_complete(item_id):
    item = OrderItem.query.get_or_404(item_id)
    if item.kitchen_status != 'completed':
        item.kitchen_status = 'completed'
        item.completed_at = datetime.utcnow()
        db.session.commit()
        
        # Check if all items in the order are completed
        order = item.order
        all_completed = all(i.kitchen_status == 'completed' for i in order.items)
        if all_completed:
            kt = KitchenTicket.query.filter_by(order_id=order.id).first()
            if kt and kt.status != 'completed':
                kt.status = 'completed'
                kt.completed_at = datetime.utcnow()
                order.completed_at = datetime.utcnow()
                db.session.commit()
                socketio.emit('ticket_update', {'id': kt.id, 'status': 'completed'})
                socketio.emit('order_update', {'order_number': order.order_number, 'status': 'completed', 'completed_at': order.completed_at.isoformat()})
        
        socketio.emit('item_update', {'item_id': item_id, 'status': 'completed'})
    return jsonify({'ok': True, 'item_id': item_id})

# ─── API: Dashboard ────────────────────────────────────────
@app.route('/api/dashboard/stats', methods=['GET'])
@staff_required
def dashboard_stats():
    period = request.args.get('period','today')
    now = datetime.utcnow()
    if period == 'today':
        start = now.replace(hour=0,minute=0,second=0)
    elif period == 'week':
        start = now - timedelta(days=7)
    else:
        start = now - timedelta(days=30)
    orders = Order.query.filter(Order.status=='paid', Order.created_at>=start).all()
    total_sales = sum(o.total for o in orders)
    total_orders = len(orders)
    by_method = {}
    for o in orders:
        by_method[o.payment_method] = by_method.get(o.payment_method, 0) + o.total
    # Top products
    item_counts = {}
    for o in orders:
        for i in o.items:
            item_counts[i.product_name] = item_counts.get(i.product_name, 0) + i.qty
    top_products = sorted(item_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    return jsonify({
        'total_sales': round(total_sales, 2),
        'total_orders': total_orders,
        'avg_order': round(total_sales/total_orders, 2) if total_orders else 0,
        'by_method': by_method,
        'top_products': [{'name':n,'qty':q} for n,q in top_products]
    })

# ─── API: Admin / User Management ──────────────────────────
@app.route('/api/users', methods=['GET'])
@staff_required
def get_users():
    user = User.query.get(session['user_id'])
    if not user or user.role != 'restaurant':
        return jsonify({'error': 'unauthorized'}), 403
    
    users = User.query.exclude(User.id == session['user_id']).all()
    return jsonify([{
        'id': u.id,
        'name': u.name,
        'email': u.email,
        'role': u.role,
        'created_at': u.created_at.isoformat()
    } for u in users])

@app.route('/api/users/<int:uid>', methods=['DELETE'])
@staff_required
def delete_user(uid):
    admin = User.query.get(session['user_id'])
    if not admin or admin.role != 'restaurant':
        return jsonify({'error': 'unauthorized'}), 403
    
    if uid == admin.id:
        return jsonify({'error': 'Cannot delete yourself'}), 400
    
    user = User.query.get_or_404(uid)
    db.session.delete(user)
    db.session.commit()
    return jsonify({'ok': True})

# ─── API: Reviews and Tips ─────────────────────────────────
@app.route('/api/orders/<int:oid>/review', methods=['POST'])
def submit_review(oid):
    o = Order.query.get_or_404(oid)
    if o.status != 'paid':
        return jsonify({'error': 'Can only review paid orders'}), 400
    
    d = request.json
    rating = d.get('rating', 5)
    comment = (d.get('comment') or '').strip()
    
    # Validate rating
    if not isinstance(rating, int) or rating < 1 or rating > 5:
        return jsonify({'error': 'Rating must be 1-5'}), 400
    
    # Check if review already exists
    existing = Review.query.filter_by(order_id=oid).first()
    if existing:
        existing.rating = rating
        existing.comment = comment
        existing.created_at = datetime.utcnow()
    else:
        review = Review(order_id=oid, rating=rating, comment=comment)
        db.session.add(review)
    
    db.session.commit()
    return jsonify({'ok': True, 'message': 'Review submitted successfully'})

@app.route('/api/reviews', methods=['GET'])
@admin_required
def get_reviews():
    reviews = Review.query.order_by(Review.created_at.desc()).all()
    return jsonify([{
        'id': r.id,
        'order_number': r.order.order_number,
        'table': r.order.table.number if r.order.table else 'Takeaway',
        'rating': r.rating,
        'comment': r.comment,
        'total': r.order.total,
        'created_at': r.created_at.isoformat()
    } for r in reviews])

@app.route('/api/orders/<int:oid>/check-review', methods=['GET'])
def check_review(oid):
    review = Review.query.filter_by(order_id=oid).first()
    if review:
        return jsonify({'has_review': True, 'rating': review.rating, 'comment': review.comment})
    return jsonify({'has_review': False})

# ─── SocketIO ──────────────────────────────────────────────
@socketio.on('connect')
def on_connect():
    emit('connected', {'status':'ok'})

# ─── Seed Data ─────────────────────────────────────────────
def seed_data():
    if Category.query.first(): return
    cats = ['Food','Beverages','Desserts']
    products = {
        'Food': [('Pizza Margherita',350),('Pasta Arrabbiata',280),('Burger Classic',220),('Grilled Sandwich',180),('Caesar Salad',200)],
        'Beverages': [('Coffee',80),('Cold Coffee',120),('Fresh Juice',100),('Mineral Water',30),('Soft Drink',60)],
        'Desserts': [('Chocolate Cake',150),('Ice Cream',100),('Brownie',120)]
    }
    for cname in cats:
        c = Category(name=cname)
        db.session.add(c)
        db.session.flush()
        for pname, price in products[cname]:
            db.session.add(Product(name=pname, price=price, category_id=c.id))
    floor = Floor(name='Ground Floor')
    db.session.add(floor)
    db.session.flush()
    for i in [1,2,3,4,5,6]:
        db.session.add(Table(number=str(i), seats=4 if i<=4 else 6, floor_id=floor.id))
    for m in [
        PaymentMethod(name='Cash',type='cash',enabled=True),
        PaymentMethod(name='Card / Bank',type='digital',enabled=True),
        PaymentMethod(name='UPI / QR',type='upi',enabled=True,upi_id='cafe@ybl'),
        PaymentMethod(name='Razorpay',type='razorpay',enabled=True),
    ]:
        db.session.add(m)
    db.session.commit()

def ensure_payment_methods():
    defaults = [
        {'name': 'Cash', 'type': 'cash', 'upi_id': ''},
        {'name': 'Card / Bank', 'type': 'digital', 'upi_id': ''},
        {'name': 'UPI / QR', 'type': 'upi', 'upi_id': 'cafe@ybl'},
        {'name': 'Razorpay', 'type': 'razorpay', 'upi_id': ''},
    ]
    changed = False
    for item in defaults:
        method = PaymentMethod.query.filter_by(type=item['type']).first()
        if not method:
            db.session.add(PaymentMethod(name=item['name'], type=item['type'], enabled=True, upi_id=item['upi_id']))
            changed = True
    if changed:
        db.session.commit()

def ensure_default_accounts():
    admin_email = 'admin@cafe.com'
    admin = User.query.filter_by(email=admin_email).first()
    if not admin:
        admin = User(
            name='Admin',
            email=admin_email,
            password=generate_password_hash('password'),
            role='restaurant',
        )
        db.session.add(admin)
    else:
        admin.role = 'restaurant'

    customer_email = 'customer@cafe.com'
    customer = User.query.filter_by(email=customer_email).first()
    if not customer:
        customer = User(
            name='Customer',
            email=customer_email,
            password=generate_password_hash('Customer@1234', method='scrypt'),
            role='customer',
        )
        db.session.add(customer)
    else:
        customer.name = 'Customer'
        customer.role = 'customer'
    db.session.commit()

with app.app_context():
    db.create_all()
    seed_data()
    ensure_payment_methods()
    ensure_default_accounts()

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000)
