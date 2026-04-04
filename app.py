from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import qrcode, io, base64, json
import os
import secrets
import re
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
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
    product = db.relationship('Product')

class KitchenTicket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    status = db.Column(db.String(20), default='to_cook')
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    order = db.relationship('Order')

# ─── Auth Helpers ──────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

def page_login_required(restaurant_only=False):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('auth'))
            if restaurant_only and session.get('user_role') != 'restaurant':
                return redirect(url_for('pos'))
            return f(*args, **kwargs)
        return decorated
    return decorator

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth'))
        user = User.query.get(session['user_id'])
        if not user or user.role != 'restaurant':
            return redirect(url_for('pos'))
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

def cleanup_reset_codes():
    now = datetime.utcnow()
    expired = [email for email, record in PASSWORD_RESET_CODES.items() if record['expires_at'] <= now]
    for email in expired:
        PASSWORD_RESET_CODES.pop(email, None)

# ─── Auth Routes ───────────────────────────────────────────
@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('user_role') == 'restaurant':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('pos'))
    return render_template('landing.html')

@app.route('/auth')
def auth():
    return render_template('auth.html')

@app.route('/api/signup', methods=['POST'])
def signup():
    d = request.json
    if User.query.filter_by(email=d['email']).first():
        return jsonify({'error': 'Email already exists'}), 400
    password_error = strong_password_error(d.get('password', ''), d.get('email', ''))
    if password_error:
        return jsonify({'error': password_error}), 400
    role = d.get('role', 'cashier')
    if role == 'admin':
        role = 'restaurant'
    # Map kitchen, manager to appropriate roles
    if role not in ('cashier', 'restaurant', 'kitchen', 'manager'):
        role = 'cashier'
    u = User(name=d['name'], email=d['email'], password=generate_password_hash(d['password'], method='scrypt'), role=role)
    db.session.add(u)
    db.session.commit()
    session['user_id'] = u.id
    session['user_name'] = u.name
    session['user_role'] = 'restaurant' if role == 'restaurant' else 'user'
    return jsonify({'ok': True, 'name': u.name, 'role': u.role})

@app.route('/api/login', methods=['POST'])
def login():
    d = request.json
    u = User.query.filter_by(email=d['email']).first()
    if not u or not check_password_hash(u.password, d['password']):
        return jsonify({'error': 'Invalid credentials'}), 401
    session['user_id'] = u.id
    session['user_name'] = u.name
    session['user_role'] = 'restaurant' if (u.role in ('restaurant', 'admin')) else 'user'
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
@page_login_required()
def pos():
    return render_template(
        'pos.html',
        user_name=session.get('user_name'),
        user_role=session.get('user_role'),
    )

@app.route('/backend')
@page_login_required(restaurant_only=True)
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
@page_login_required()
def kitchen():
    return render_template('kitchen.html', user_role=session.get('user_role'))

@app.route('/customer')
@page_login_required()
def customer():
    return render_template('customer.html', user_role=session.get('user_role'))

@app.route('/dashboard')
@page_login_required(restaurant_only=True)
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
@login_required
def get_all_products():
    products = Product.query.all()
    cats = Category.query.all()
    return jsonify({
        'products': [{'id':p.id,'name':p.name,'price':p.price,'category_id':p.category_id,'description':p.description,'tax':p.tax,'unit':p.unit,'active':p.active} for p in products],
        'categories': [{'id':c.id,'name':c.name} for c in cats]
    })

@app.route('/api/products', methods=['POST'])
@login_required
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
@login_required
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
@login_required
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
@login_required
def add_floor():
    d = request.json
    f = Floor(name=d['name'])
    db.session.add(f)
    db.session.commit()
    return jsonify({'ok':True,'id':f.id})

@app.route('/api/tables', methods=['POST'])
@login_required
def add_table():
    d = request.json
    t = Table(number=d['number'], seats=int(d.get('seats',4)), floor_id=int(d['floor_id']))
    db.session.add(t)
    db.session.commit()
    return jsonify({'ok':True,'id':t.id})

@app.route('/api/tables/<int:tid>', methods=['DELETE'])
@login_required
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
@login_required
def update_payment_method(mid):
    m = PaymentMethod.query.get_or_404(mid)
    d = request.json
    m.enabled = d.get('enabled', m.enabled)
    m.upi_id = d.get('upi_id', m.upi_id)
    db.session.commit()
    return jsonify({'ok':True})

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
@login_required
def current_session():
    s = Session.query.filter_by(user_id=session['user_id'], status='open').first()
    if s:
        return jsonify({'id':s.id,'opened_at':s.opened_at.isoformat(),'status':s.status})
    return jsonify({'id':None})

@app.route('/api/sessions/open', methods=['POST'])
@login_required
def open_session():
    existing = Session.query.filter_by(user_id=session['user_id'], status='open').first()
    if existing:
        return jsonify({'id':existing.id,'opened_at':existing.opened_at.isoformat()})
    s = Session(user_id=session['user_id'])
    db.session.add(s)
    db.session.commit()
    return jsonify({'id':s.id,'opened_at':s.opened_at.isoformat()})

@app.route('/api/sessions/close', methods=['POST'])
@login_required
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
@login_required
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
@login_required
def send_to_kitchen(oid):
    o = Order.query.get_or_404(oid)
    o.status = 'sent'
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
        'items': [{'name':i.product_name,'qty':i.qty,'id':i.id} for i in o.items]
    }
    socketio.emit('new_ticket', ticket_data)
    socketio.emit('order_update', {'order_number': o.order_number, 'status': 'preparing'})
    return jsonify({'ok':True})

@app.route('/api/orders/<int:oid>/pay', methods=['POST'])
@login_required
def pay_order(oid):
    o = Order.query.get_or_404(oid)
    d = request.json
    o.status = 'paid'
    o.payment_method = d.get('method','cash')
    if o.table:
        o.table.status = 'free'
    db.session.commit()
    socketio.emit('order_paid', {'order_number': o.order_number, 'total': o.total, 'method': o.payment_method})
    return jsonify({'ok':True})

@app.route('/api/orders/table/<int:tid>', methods=['GET'])
@login_required
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
        result.append({
            'id': kt.id,
            'order_number': kt.order.order_number,
            'table': kt.order.table.number if kt.order.table else 'Takeaway',
            'status': kt.status,
            'sent_at': kt.sent_at.isoformat(),
            'items': [{'id':i.id,'name':i.product_name,'qty':i.qty,'status':i.kitchen_status} for i in kt.order.items]
        })
    return jsonify(result)

@app.route('/api/kitchen/tickets/<int:kid>/advance', methods=['POST'])
def advance_ticket(kid):
    kt = KitchenTicket.query.get_or_404(kid)
    stages = ['to_cook','preparing','completed']
    idx = stages.index(kt.status) if kt.status in stages else 0
    if idx < len(stages)-1:
        kt.status = stages[idx+1]
        db.session.commit()
        socketio.emit('ticket_update', {'id': kid, 'status': kt.status})
    return jsonify({'ok':True,'status':kt.status})

# ─── API: Dashboard ────────────────────────────────────────
@app.route('/api/dashboard/stats', methods=['GET'])
@login_required
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
@login_required
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
@login_required
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
    ]:
        db.session.add(m)
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
    db.session.commit()

with app.app_context():
    db.create_all()
    seed_data()
    ensure_default_accounts()

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000)
