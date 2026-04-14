from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import qrcode, io, base64, json
import sqlite3
import os
import tempfile
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

LEGACY_DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'pos.db')
DB_DIR = os.path.join(tempfile.gettempdir(), 'pos-cafe')
DB_PATH = os.path.join(DB_DIR, 'pos_runtime.db')
os.makedirs(DB_DIR, exist_ok=True)
if os.path.exists(DB_PATH):
    def _db_is_writable(path):
        conn = None
        try:
            conn = sqlite3.connect(path)
            cur = conn.cursor()
            cur.execute('CREATE TABLE IF NOT EXISTS __db_write_test (id INTEGER)')
            cur.execute('INSERT INTO __db_write_test (id) VALUES (1)')
            conn.commit()
            cur.execute('DROP TABLE __db_write_test')
            conn.commit()
            return True
        except Exception:
            return False
        finally:
            if conn is not None:
                conn.close()

    if not _db_is_writable(DB_PATH):
        try:
            os.remove(DB_PATH)
        except Exception:
            pass

app = Flask(__name__)
app.config['SECRET_KEY'] = 'pos-cafe-hackathon-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + DB_PATH.replace('\\', '/')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'connect_args': {'timeout': 30}}

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
try:
    import gevent  # noqa: F401
    _async_mode = 'gevent'
except ImportError:
    try:
        import eventlet  # noqa: F401
        _async_mode = 'eventlet'
    except ImportError:
        _async_mode = None
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=_async_mode)
CORS(app)

@app.template_filter('from_json')
def from_json_filter(s):
    try:
        return json.loads(s)
    except:
        return {}

# ─── Models ───────────────────────────────────────────────
class Tenant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    logo_b64 = db.Column(db.Text, default='')
    plan = db.Column(db.String(20), default='free')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    owner_id = db.Column(db.Integer, nullable=True)

class Branch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.Text, default='')
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tenant = db.relationship('Tenant', backref='branches')

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='cashier')
    hourly_rate = db.Column(db.Float, default=0)
    is_superadmin = db.Column(db.Boolean, default=False)
    is_platform_admin = db.Column(db.Boolean, default=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branch.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tenant = db.relationship('Tenant', backref='users')
    branch = db.relationship('Branch', backref='users')

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    products = db.relationship('Product', backref='category', lazy=True)
    tenant = db.relationship('Tenant', backref='categories')

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    branch_id = db.Column(db.Integer, db.ForeignKey('branch.id'), nullable=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    description = db.Column(db.Text, default='')
    tax = db.Column(db.Float, default=0)
    tax_config_json = db.Column(db.Text, default='{}')  # JSON: {"CGST": 2.5, "SGST": 2.5}
    unit = db.Column(db.String(20), default='pcs')
    active = db.Column(db.Boolean, default=True)
    image_b64 = db.Column(db.Text, default='')  # base64 data URL for product photo
    branch = db.relationship('Branch', backref='products')
    tenant = db.relationship('Tenant', backref='products')

class Floor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    tables = db.relationship('Table', backref='floor', lazy=True)
    tenant = db.relationship('Tenant', backref='floors')

class Table(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(10), nullable=False)
    seats = db.Column(db.Integer, default=4)
    floor_id = db.Column(db.Integer, db.ForeignKey('floor.id'))
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    active = db.Column(db.Boolean, default=True)
    status = db.Column(db.String(20), default='free')  # free, occupied
    tenant = db.relationship('Tenant', backref='tables')

class PaymentMethod(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # cash, digital, upi
    enabled = db.Column(db.Boolean, default=True)
    upi_id = db.Column(db.String(100), default='')
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    tenant = db.relationship('Tenant', backref='payment_methods')

class CafeSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), default='POS Cafe')
    phone = db.Column(db.String(20), default='')
    email = db.Column(db.String(120), default='')
    address = db.Column(db.Text, default='')
    logo_b64 = db.Column(db.Text, default='')  # base64 data URL for cafe logo
    open_time = db.Column(db.String(5), default='09:00')  # HH:MM format
    close_time = db.Column(db.String(5), default='22:00')  # HH:MM format
    tax_rate = db.Column(db.Float, default=5.0)
    gst_no = db.Column(db.String(50), default='')
    fssai_no = db.Column(db.String(50), default='')
    footer_note = db.Column(db.Text, default='')
    loyalty_points_per_100 = db.Column(db.Float, default=10.0)  # Owner decides ratio
    points_redemption_value = db.Column(db.Float, default=0.5)  # 1 point = ₹0.50
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    tenant = db.relationship('Tenant', backref='settings')

class Session(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    opened_at = db.Column(db.DateTime, default=datetime.utcnow)
    closed_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='open')
    closing_amount = db.Column(db.Float, default=0)
    user = db.relationship('User', backref='sessions')
    tenant = db.relationship('Tenant', backref='sessions')

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), default='')
    phone = db.Column(db.String(20), index=True)
    email = db.Column(db.String(120), default='')
    loyalty_points = db.Column(db.Float, default=0.0)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tenant = db.relationship('Tenant', backref='customers')


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), nullable=False)
    table_id = db.Column(db.Integer, db.ForeignKey('table.id'), nullable=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    branch_id = db.Column(db.Integer, db.ForeignKey('branch.id'), nullable=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=True)
    customer_name = db.Column(db.String(100), default='')  # For takeaway orders or fast input
    customer_phone = db.Column(db.String(20), default='')
    status = db.Column(db.String(30), default='draft')  # draft, sent, paid
    payment_method = db.Column(db.String(30), default='')
    subtotal = db.Column(db.Float, default=0)
    tax_amount = db.Column(db.Float, default=0)
    tax_breakdown_json = db.Column(db.Text, default='{}')
    round_off = db.Column(db.Float, default=0)
    total_qty = db.Column(db.Integer, default=0)
    total = db.Column(db.Float, default=0)
    tip = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_to_kitchen_at = db.Column(db.DateTime, nullable=True)  # When sent to kitchen
    started_at = db.Column(db.DateTime, nullable=True)  # When kitchen starts preparing
    completed_at = db.Column(db.DateTime, nullable=True)  # When order is ready
    razorpay_order_id = db.Column(db.String(100), nullable=True)  # Razorpay order ID for payment tracking
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
    reviews = db.relationship('Review', backref='order', lazy=True, cascade='all, delete-orphan')
    order_customer = db.relationship('Customer', backref='orders')
    table = db.relationship('Table', backref='orders')
    user = db.relationship('User', backref='orders')
    branch = db.relationship('Branch', backref='orders')
    tenant = db.relationship('Tenant', backref='orders')

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    product_name = db.Column(db.String(100))
    qty = db.Column(db.Integer, default=1)
    price = db.Column(db.Float, default=0)
    notes = db.Column(db.Text, default='')  # Item modifier notes (e.g. 'no onion')
    tax_rate = db.Column(db.Float, default=0)
    tax_amount = db.Column(db.Float, default=0)
    tax_info_json = db.Column(db.Text, default='{}')
    kitchen_status = db.Column(db.String(20), default='pending')  # pending, to_cook, preparing, completed
    started_at = db.Column(db.DateTime, nullable=True)  # When item preparation starts
    completed_at = db.Column(db.DateTime, nullable=True)  # When item is ready
    product = db.relationship('Product')

class KitchenTicket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    status = db.Column(db.String(20), default='to_cook')
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)  # When preparing starts
    completed_at = db.Column(db.DateTime, nullable=True)  # When all items completed
    order = db.relationship('Order')
    tenant = db.relationship('Tenant', backref='kitchen_tickets')

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    rating = db.Column(db.Integer, default=5)  # 1-5 stars
    comment = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    table_id = db.Column(db.Integer, db.ForeignKey('table.id'), nullable=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    reserved_at = db.Column(db.DateTime, nullable=False)  # date+time of booking
    party_size = db.Column(db.Integer, default=2)
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, seated, completed, cancelled
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('ReservationItem', backref='reservation', cascade='all, delete-orphan', lazy=True)
    customer = db.relationship('User', backref='reservations')
    table = db.relationship('Table', backref='reservations')
    tenant = db.relationship('Tenant', backref='reservations')

class ReservationItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reservation_id = db.Column(db.Integer, db.ForeignKey('reservation.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    product_name = db.Column(db.String(100))
    qty = db.Column(db.Integer, default=1)
    price = db.Column(db.Float)
    notes = db.Column(db.Text, default='')
    product = db.relationship('Product')

class PushSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    table_id = db.Column(db.Integer, nullable=True)  # For guest self-orders via QR
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    subscription_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tenant = db.relationship('Tenant', backref='push_subscriptions')

class AttendanceEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branch.id'), nullable=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    action = db.Column(db.String(10), nullable=False)  # in/out
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    staff = db.relationship('User', backref='attendance_events')
    branch = db.relationship('Branch', backref='attendance_events')
    tenant = db.relationship('Tenant', backref='attendance_events')

class InventoryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    unit = db.Column(db.String(20), default='unit')  # kg, litre, gram, pcs, box etc.
    current_stock = db.Column(db.Float, default=0.0)
    min_threshold = db.Column(db.Float, default=0.0)
    unit_cost = db.Column(db.Float, default=0.0)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    tenant = db.relationship('Tenant', backref='inventory_items')

class ProductRecipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id'), nullable=False)
    quantity = db.Column(db.Float, default=1.0)  # Amount of inventory item used per product unit
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    product = db.relationship('Product', backref='recipe_items')
    inventory_item = db.relationship('InventoryItem')

class InventoryLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id'), nullable=False)
    action = db.Column(db.String(20), nullable=False)  # purchase, sale, adjustment, wastage
    quantity = db.Column(db.Float, nullable=False)
    note = db.Column(db.Text, default='')
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    inventory_item = db.relationship('InventoryItem', backref='logs')

class WastageLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    reason = db.Column(db.Text, default='')
    reported_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    inventory_item = db.relationship('InventoryItem', backref='wastage_logs')
    user = db.relationship('User')

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
        return url_for('dashboard')
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
        if not user:
            return redirect(url_for('auth'))
        role = normalize_role(user.role)
        if role not in ('restaurant', 'manager') and not user.is_superadmin:
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

def make_slug(name):
    """Convert a name like 'Chai Point Cafe' to 'chai-point-cafe'."""
    slug = re.sub(r'[^a-z0-9]+', '-', (name or '').strip().lower()).strip('-')
    return slug or 'my-cafe'

def get_current_tenant_id():
    """Get the current tenant_id from session."""
    return session.get('tenant_id')

def get_current_tenant():
    """Get the current Tenant object."""
    tid = get_current_tenant_id()
    if tid:
        return Tenant.query.get(tid)
    return None

def utc_iso(dt):
    """Format a naive UTC datetime as an ISO string with Z suffix.
    This tells JavaScript's Date constructor to treat it as UTC
    so toLocaleString() converts correctly to the user's timezone."""
    if dt is None:
        return None
    return dt.isoformat() + 'Z'

def apply_tenant_scope(query, model_class):
    """Filter any query to the current tenant. Skips for platform admins."""
    user = get_current_user()
    if user and getattr(user, 'is_platform_admin', False):
        return query  # Platform admins see everything
    tid = get_current_tenant_id()
    if tid and hasattr(model_class, 'tenant_id'):
        return query.filter(model_class.tenant_id == tid)
    return query

def get_default_branch():
    tid = get_current_tenant_id()
    q = Branch.query
    if tid:
        q = q.filter_by(tenant_id=tid)
    return q.order_by(Branch.id.asc()).first()

def is_superadmin(user=None):
    user = user or get_current_user()
    return bool(user and user.is_superadmin)

def get_active_branch_id(user=None):
    user = user or get_current_user()
    if not user:
        return None
    if is_superadmin(user):
        branch_id = session.get('active_branch_id') or user.branch_id
        if branch_id:
            return int(branch_id)
        default_branch = get_default_branch()
        if default_branch:
            session['active_branch_id'] = default_branch.id
            return default_branch.id
        return None
    return user.branch_id

def get_accessible_branch_ids(user=None):
    user = user or get_current_user()
    if not user:
        return []
    if is_superadmin(user):
        q = Branch.query
        if user.tenant_id:
            q = q.filter_by(tenant_id=user.tenant_id)
        return [b.id for b in q.order_by(Branch.name.asc()).all()]
    return [user.branch_id] if user.branch_id else []

def apply_branch_scope(query, column, include_all_for_superadmin=False):
    user = get_current_user()
    if not user:
        default_branch = get_default_branch()
        if default_branch:
            return query.filter(column == default_branch.id)
        return query
    if include_all_for_superadmin and is_superadmin(user):
        return query
    active_branch_id = get_active_branch_id(user)
    if active_branch_id is None:
        return query.filter(column.is_(None))
    return query.filter(column == active_branch_id)

def ensure_branch_access(branch_id, user=None):
    user = user or get_current_user()
    if not user:
        return False
    if branch_id is None:
        return not get_accessible_branch_ids(user)
    return branch_id in get_accessible_branch_ids(user)

def require_branch_access_or_403(branch_id):
    if not ensure_branch_access(branch_id):
        return jsonify({'error': 'forbidden'}), 403
    return None

def get_selected_branch():
    active_branch_id = get_active_branch_id()
    if not active_branch_id:
        return None
    return Branch.query.get(active_branch_id)

def get_current_shift_start(staff_id):
    events = AttendanceEvent.query.filter_by(staff_id=staff_id).order_by(AttendanceEvent.timestamp.asc(), AttendanceEvent.id.asc()).all()
    open_event = None
    for event in events:
        if event.action == 'in':
            open_event = event
        elif event.action == 'out' and open_event:
            open_event = None
    return open_event

def build_attendance_shifts(events, start_date=None, end_date=None, staff_filter=None):
    shifts = []
    events_by_staff = {}
    for event in events:
        if staff_filter and event.staff_id != staff_filter:
            continue
        events_by_staff.setdefault(event.staff_id, []).append(event)

    for staff_events in events_by_staff.values():
        open_in = None
        for event in sorted(staff_events, key=lambda e: (e.timestamp, e.id)):
            if event.action == 'in':
                if open_in:
                    shifts.append((open_in, None))
                open_in = event
            elif event.action == 'out':
                if open_in:
                    shifts.append((open_in, event))
                    open_in = None
        if open_in:
            shifts.append((open_in, None))

    rows = []
    for clock_in_event, clock_out_event in shifts:
        shift_date = clock_in_event.timestamp.date()
        if start_date and shift_date < start_date:
            continue
        if end_date and shift_date > end_date:
            continue
        staff = clock_in_event.staff
        hours_worked = 0
        if clock_out_event and clock_out_event.timestamp >= clock_in_event.timestamp:
            hours_worked = round((clock_out_event.timestamp - clock_in_event.timestamp).total_seconds() / 3600, 2)
        hourly_rate = float(getattr(staff, 'hourly_rate', 0) or 0)
        rows.append({
            'clock_in_event_id': clock_in_event.id,
            'clock_out_event_id': clock_out_event.id if clock_out_event else None,
            'staff_id': staff.id,
            'staff_name': staff.name,
            'date': shift_date.isoformat(),
            'clock_in_at': clock_in_event.timestamp,
            'clock_out_at': clock_out_event.timestamp if clock_out_event else None,
            'hours_worked': hours_worked,
            'hourly_rate': hourly_rate,
            'pay': round(hours_worked * hourly_rate, 2),
            'is_open_shift': clock_out_event is None,
            'branch_id': clock_in_event.branch_id,
        })
    rows.sort(key=lambda row: (row['clock_in_at'], row['staff_name']), reverse=True)
    return rows

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

def verify_razorpay_webhook_signature(webhook_data, signature):
    if not RAZORPAY_KEY_SECRET:
        return False
    message = webhook_data.encode('utf-8')
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
    d = request.json or {}
    if User.query.filter_by(email=d['email']).first():
        return jsonify({'error': 'Email already exists'}), 400
    password_error = strong_password_error(d.get('password', ''), d.get('email', ''))
    if password_error:
        return jsonify({'error': password_error}), 400
    role = normalize_role(d.get('role', 'cashier'))
    # Map unsupported roles to the closest valid role.
    if role not in ('cashier', 'restaurant', 'kitchen', 'manager', 'customer'):
        role = 'cashier'
    creator = get_current_user()
    branch_id = d.get('branch_id')
    if branch_id:
        try:
            branch_id = int(branch_id)
        except (TypeError, ValueError):
            branch_id = None
    elif creator:
        branch_id = get_active_branch_id(creator)
    else:
        default_branch = get_default_branch()
        branch_id = default_branch.id if default_branch else None

    if creator and not is_superadmin(creator):
        branch_id = creator.branch_id

    tenant_id = None
    if creator:
        tenant_id = creator.tenant_id
    elif d.get('tenant_id'):
        tenant_id = int(d['tenant_id'])
    else:
        # Assign to default tenant
        t = Tenant.query.order_by(Tenant.id.asc()).first()
        tenant_id = t.id if t else None

    u = User(
        name=d['name'],
        email=d['email'],
        password=generate_password_hash(d['password'], method='scrypt'),
        role=role,
        branch_id=branch_id,
        tenant_id=tenant_id,
        hourly_rate=float(d.get('hourly_rate', 0) or 0),
        is_superadmin=bool(d.get('is_superadmin', False)) and bool(creator and is_superadmin(creator)),
    )
    db.session.add(u)
    db.session.commit()
    if not creator:
        session['user_id'] = u.id
        session['user_name'] = u.name
        session['user_role'] = role
        session['tenant_id'] = u.tenant_id
        if u.branch_id:
            session['active_branch_id'] = u.branch_id
    return jsonify({'ok': True, 'name': u.name, 'role': u.role})

@app.route('/api/login', methods=['POST'])
def login():
    d = request.json or {}
    u = User.query.filter_by(email=d['email']).first()
    if not u or not check_password_hash(u.password, d['password']):
        return jsonify({'error': 'Invalid credentials'}), 401
    session['user_id'] = u.id
    session['user_name'] = u.name
    session['user_role'] = normalize_role(u.role)
    session['tenant_id'] = u.tenant_id
    if u.branch_id:
        session['active_branch_id'] = u.branch_id
    elif is_superadmin(u):
        default_branch = get_default_branch()
        if default_branch:
            session['active_branch_id'] = default_branch.id
    else:
        session.pop('active_branch_id', None)
    return jsonify({
        'ok': True,
        'name': u.name,
        'role': session['user_role'],
        'is_superadmin': u.is_superadmin,
        'active_branch_id': session.get('active_branch_id'),
        'tenant_id': u.tenant_id,
    })

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/quick-login', methods=['POST'])
def quick_login():
    """Dev endpoint: quickly login as a test user by role (customer/staff/owner)."""
    d = request.json or {}
    role_param = (d.get('role') or '').strip().lower()
    
    role_map = {
        'customer': 'customer',
        'user': 'customer',
        'staff': 'cashier',
        'pos': 'cashier',
        'owner': 'restaurant',
        'admin': 'restaurant'
    }
    
    role = role_map.get(role_param, 'customer')
    test_email = f'{role_param}@test.cafe'
    test_password = 'Test@1234567'
    
    # Try to find existing test user
    user = User.query.filter_by(email=test_email).first()
    
    # Create test user if doesn't exist
    if not user:
        from werkzeug.security import generate_password_hash
        # Get or create Default Tenant for test users
        default_tenant = Tenant.query.filter_by(slug='default').first()
        if not default_tenant:
            default_tenant = Tenant(name='Default Tenant', slug='default', plan='free', is_active=True)
            db.session.add(default_tenant)
            db.session.flush()
        
        default_branch = Branch.query.filter_by(tenant_id=default_tenant.id).order_by(Branch.id.asc()).first()
        branch_id = default_branch.id if default_branch else None
        
        user = User(
            name=f'Test {role_param.title()}',
            email=test_email,
            password=generate_password_hash(test_password, method='scrypt'),
            role=role,
            tenant_id=default_tenant.id,
            branch_id=branch_id,
            is_superadmin=(role == 'restaurant')
        )
        db.session.add(user)
        db.session.commit()
    
    # Log them in
    session['user_id'] = user.id
    session['user_name'] = user.name
    session['user_role'] = normalize_role(user.role)
    session['tenant_id'] = user.tenant_id or Tenant.query.filter_by(slug='default').first().id
    if user.branch_id:
        session['active_branch_id'] = user.branch_id
    elif is_superadmin(user):
        default_branch = get_default_branch()
        if default_branch:
            session['active_branch_id'] = default_branch.id
    
    session.modified = True  # Force Flask to save session
    home_url = role_home(session['user_role'])
    
    return jsonify({
        'ok': True,
        'name': user.name,
        'role': session['user_role'],
        'home': home_url
    })

@app.route('/api/register-restaurant', methods=['POST'])
def register_restaurant():
    """Onboard a new restaurant: creates Tenant + Branch + Owner user."""
    d = request.json or {}
    restaurant_name = (d.get('restaurant_name') or '').strip()
    name = (d.get('name') or '').strip()
    email = (d.get('email') or '').strip()
    password = d.get('password') or ''

    if not restaurant_name or not name or not email or not password:
        return jsonify({'error': 'Restaurant name, your name, email, and password are required'}), 400
    if find_user_by_email(email):
        return jsonify({'error': 'Email already exists'}), 400
    password_error = strong_password_error(password, email)
    if password_error:
        return jsonify({'error': password_error}), 400

    # Create unique slug
    base_slug = make_slug(restaurant_name)
    slug = base_slug
    counter = 1
    while Tenant.query.filter_by(slug=slug).first():
        slug = f'{base_slug}-{counter}'
        counter += 1

    # Create tenant
    tenant = Tenant(name=restaurant_name, slug=slug)
    db.session.add(tenant)
    db.session.flush()

    # Create default branch
    branch = Branch(name=f'{restaurant_name} — Main', tenant_id=tenant.id)
    db.session.add(branch)
    db.session.flush()

    # Create owner user
    owner = User(
        name=name,
        email=email,
        password=generate_password_hash(password, method='scrypt'),
        role='restaurant',
        tenant_id=tenant.id,
        branch_id=branch.id,
        is_superadmin=True,
    )
    db.session.add(owner)
    db.session.flush()

    tenant.owner_id = owner.id

    # Create default payment methods for this tenant
    for pm_name, pm_type in [('Cash', 'cash'), ('UPI / QR', 'upi'), ('Card', 'digital')]:
        db.session.add(PaymentMethod(name=pm_name, type=pm_type, enabled=True, tenant_id=tenant.id))

    # Create default cafe settings for this tenant
    db.session.add(CafeSettings(name=restaurant_name, tenant_id=tenant.id))

    db.session.commit()

    # Log them in
    session['user_id'] = owner.id
    session['user_name'] = owner.name
    session['user_role'] = 'restaurant'
    session['tenant_id'] = tenant.id
    session['active_branch_id'] = branch.id

    return jsonify({
        'ok': True,
        'name': owner.name,
        'role': 'restaurant',
        'tenant_slug': tenant.slug,
    })

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
        active_branch=get_selected_branch(),
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
def admin_redirect():
    return redirect(url_for('dashboard'))

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
        active_branch=get_selected_branch(),
        is_superadmin=is_superadmin(),
    )

# ─── API: Products ─────────────────────────────────────────
@app.route('/api/products', methods=['GET'])
def get_products():
    branch_id = get_active_branch_id()
    products = apply_tenant_scope(apply_branch_scope(Product.query.filter_by(active=True), Product.branch_id), Product).all()
    products_by_category = {}
    for product in products:
        products_by_category.setdefault(product.category_id, []).append(product)
    cats = apply_tenant_scope(Category.query, Category).all()
    result = []
    for c in cats:
        prods = [{
            'id': p.id,
            'name': p.name,
            'price': p.price,
            'description': p.description,
            'tax': p.tax,
            'unit': p.unit,
            'image_b64': p.image_b64 or '',
            'branch_id': p.branch_id or branch_id,
        } for p in products_by_category.get(c.id, [])]
        if prods:
            result.append({'id':c.id,'name':c.name,'products':prods})
    return jsonify(result)

@app.route('/api/products/all', methods=['GET'])
@staff_required
def get_all_products():
    products = apply_tenant_scope(apply_branch_scope(Product.query, Product.branch_id), Product).all()
    cats = apply_tenant_scope(Category.query, Category).all()
    return jsonify({
        'products': [{'id':p.id,'name':p.name,'price':p.price,'category_id':p.category_id,'description':p.description,'tax':p.tax,'unit':p.unit,'active':p.active,'image_b64':p.image_b64 or '', 'branch_id': p.branch_id} for p in products],
        'categories': [{'id':c.id,'name':c.name} for c in cats]
    })

@app.route('/api/products', methods=['POST'])
@staff_required
def add_product():
    d = request.json
    cat = apply_tenant_scope(Category.query.filter_by(name=d.get('category','')), Category).first()
    if not cat:
        cat = Category(name=d.get('category','General'), tenant_id=get_current_tenant_id())
        db.session.add(cat)
        db.session.flush()
    p = Product(name=d['name'], price=float(d['price']), category_id=cat.id,
                description=d.get('description',''), 
                tax=float(d.get('tax',0)), 
                tax_config_json=json.dumps(d.get('tax_config', {})),
                unit=d.get('unit','pcs'),
                branch_id=get_active_branch_id(), tenant_id=get_current_tenant_id())
    db.session.add(p)
    db.session.commit()
    return jsonify({'ok':True,'id':p.id})

@app.route('/api/products/<int:pid>', methods=['PUT'])
@staff_required
def update_product(pid):
    tid = get_current_tenant_id()
    p = Product.query.filter_by(id=pid, tenant_id=tid).first_or_404()
    access_error = require_branch_access_or_403(p.branch_id)
    if access_error:
        return access_error
    d = request.json
    p.name = d.get('name', p.name)
    p.price = float(d.get('price', p.price))
    p.description = d.get('description', p.description)
    p.tax = float(d.get('tax', p.tax))
    if 'tax_config' in d:
        p.tax_config_json = json.dumps(d['tax_config'])
    p.unit = d.get('unit', p.unit)
    p.active = d.get('active', p.active)
    if 'image_b64' in d:
        p.image_b64 = d['image_b64'] or ''
    if 'category' in d and d['category']:
        cat = apply_tenant_scope(Category.query.filter_by(name=d['category']), Category).first()
        if not cat:
            cat = Category(name=d['category'], tenant_id=get_current_tenant_id())
            db.session.add(cat)
            db.session.flush()
        p.category_id = cat.id
    db.session.commit()
    return jsonify({'ok':True})

@app.route('/api/products/<int:pid>', methods=['DELETE'])
@staff_required
def delete_product(pid):
    tid = get_current_tenant_id()
    p = Product.query.filter_by(id=pid, tenant_id=tid).first_or_404()
    access_error = require_branch_access_or_403(p.branch_id)
    if access_error:
        return access_error
    db.session.delete(p)
    db.session.commit()
    return jsonify({'ok':True})

# ─── API: Floors & Tables ──────────────────────────────────
@app.route('/api/floors', methods=['GET'])
def get_floors():
    floors = apply_tenant_scope(Floor.query, Floor).all()
    result = []
    for f in floors:
        tables = [{'id':t.id,'number':t.number,'seats':t.seats,'status':t.status,'active':t.active} for t in f.tables if t.active]
        result.append({'id':f.id,'name':f.name,'tables':tables})
    return jsonify(result)

@app.route('/api/floors', methods=['POST'])
@staff_required
def add_floor():
    d = request.json
    f = Floor(name=d['name'], tenant_id=get_current_tenant_id())
    db.session.add(f)
    db.session.commit()
    return jsonify({'ok':True,'id':f.id})

@app.route('/api/tables', methods=['POST'])
@staff_required
def add_table():
    d = request.json
    t = Table(number=d['number'], seats=int(d.get('seats',4)), floor_id=int(d['floor_id']), tenant_id=get_current_tenant_id())
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

@app.route('/api/tables/<int:tid>/status', methods=['PUT'])
@staff_required
def update_table_status(tid):
    t = Table.query.get_or_404(tid)
    d = request.json
    status = d.get('status', 'free')  # 'free' or 'occupied'
    if status not in ['free', 'occupied']:
        return jsonify({'error': 'Invalid status'}), 400
    t.status = status
    db.session.commit()
    return jsonify({'ok': True, 'status': t.status})

# ─── API: Payment Methods ──────────────────────────────────
@app.route('/api/payment-methods', methods=['GET'])
def get_payment_methods():
    methods = apply_tenant_scope(PaymentMethod.query, PaymentMethod).all()
    return jsonify([{'id':m.id,'name':m.name,'type':m.type,'enabled':m.enabled,'upi_id':m.upi_id} for m in methods])

@app.route('/api/payment-methods/<int:mid>', methods=['PUT'])
@staff_required
def update_payment_method(mid):
    m = PaymentMethod.query.filter_by(id=mid, tenant_id=get_current_tenant_id()).first_or_404()
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

    # Save Razorpay order ID
    order.razorpay_order_id = result.get('id')
    db.session.commit()

    # Generate QR code for payment link
    payment_link = f"https://rzp.io/i/{result.get('id')}"
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(payment_link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return jsonify({
        'ok': True,
        'razorpay_order_id': result.get('id'),
        'amount': result.get('amount'),
        'currency': result.get('currency'),
        'key_id': RAZORPAY_KEY_ID,
        'merchant_name': RAZORPAY_MERCHANT_NAME,
        'order_number': order.order_number,
        'customer_name': session.get('user_name', 'Customer'),
        'qr_code': f'data:image/png;base64,{qr_b64}',
        'payment_link': payment_link,
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

# ─── API: Razorpay Payment Integration ──────────────────────
@app.route('/api/razorpay-webhook', methods=['POST'])
def razorpay_webhook():
    """Webhook endpoint to handle Razorpay payment confirmations"""
    try:
        event_data = request.get_data(as_text=True)
        webhook_signature = request.headers.get('X-Razorpay-Signature', '')
        
        # Verify webhook signature
        if not verify_razorpay_webhook_signature(event_data, webhook_signature):
            return jsonify({'error': 'Invalid signature'}), 401
        
        event = json.loads(event_data)
        event_type = event.get('event', '')
        
        # Handle payment.authorized event (payment successful)
        if event_type == 'payment.authorized':
            payment = event.get('payload', {}).get('payment', {}).get('entity', {})
            razorpay_order_id = payment.get('order_id', '')
            payment_id = payment.get('id', '')
            
            # Find order by Razorpay order ID
            o = Order.query.filter_by(razorpay_order_id=razorpay_order_id).first()
            if not o:
                return jsonify({'error': 'Order not found'}), 404
            
            # Mark order as paid
            if o.status != 'paid':
                o.status = 'paid'
                o.payment_method = 'razorpay'
                if o.table:
                    o.table.status = 'free'
                process_loyalty_earning(o)
                db.session.commit()
                
                # Notify via WebSocket
                socketio.emit('order_paid', {
                    'order_number': o.order_number,
                    'total': o.total,
                    'tip': o.tip,
                    'method': 'razorpay',
                    'razorpay_payment_id': payment_id
                })
        
        # Handle payment.captured event (payment captured)
        elif event_type == 'payment.captured':
            payment = event.get('payload', {}).get('payment', {}).get('entity', {})
            razorpay_order_id = payment.get('order_id', '')
            payment_id = payment.get('id', '')
            
            # Find order by Razorpay order ID
            o = Order.query.filter_by(razorpay_order_id=razorpay_order_id).first()
            if not o:
                return jsonify({'error': 'Order not found'}), 404
            
            # Mark order as paid
            if o.status != 'paid':
                o.status = 'paid'
                o.payment_method = 'razorpay'
                if o.table:
                    o.table.status = 'free'
                process_loyalty_earning(o)
                db.session.commit()
                
                # Notify via WebSocket
                socketio.emit('order_paid', {
                    'order_number': o.order_number,
                    'total': o.total,
                    'tip': o.tip,
                    'method': 'razorpay',
                    'razorpay_payment_id': payment_id
                })
        
        return jsonify({'status': 'ok'}), 200
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500

@app.route('/api/orders/<int:oid>/payment-status', methods=['GET'])
def check_payment_status(oid):
    """Check if payment has been confirmed for an order"""
    o = Order.query.filter_by(id=oid, tenant_id=get_current_tenant_id()).first_or_404()
    access_error = require_branch_access_or_403(o.branch_id)
    if access_error:
        return access_error
    return jsonify({
        'order_id': o.id,
        'order_number': o.order_number,
        'status': o.status,
        'razorpay_order_id': o.razorpay_order_id,
        'payment_method': o.payment_method,
        'total': o.total,
        'is_paid': o.status == 'paid'
    })

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
    s = Session(user_id=session['user_id'], tenant_id=get_current_tenant_id())
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

@app.route('/api/customer/lookup', methods=['GET'])
@staff_required
def lookup_customer():
    phone = request.args.get('phone', '').strip()
    if not phone:
        return jsonify({'error': 'Phone required'}), 400
    tenant_id = get_current_tenant_id()
    c = Customer.query.filter_by(tenant_id=tenant_id, phone=phone).first()
    if c:
        return jsonify({'found': True, 'name': c.name, 'id': c.id})
    return jsonify({'found': False})

# ─── API: Orders ───────────────────────────────────────────
# ─── Inventory Deduction Helper ────────────────────────
def deduct_inventory_for_order(order):
    """Deduct stock from ingredients based on product recipes."""
    if not order: return
    
    for item in order.items:
        # Get recipe for this product
        recipe = ProductRecipe.query.filter_by(product_id=item.product_id).all()
        for r_item in recipe:
            ing = InventoryItem.query.get(r_item.inventory_item_id)
            if ing:
                total_deduction = r_item.quantity * item.qty
                ing.current_stock -= total_deduction
                
                # Log the deduction
                log = InventoryLog(
                    inventory_item_id=ing.id,
                    action='sale',
                    quantity=-total_deduction,
                    note=f'Order #{order.order_number}',
                    tenant_id=order.tenant_id
                )
                db.session.add(log)
    db.session.commit()

# ─── Loyalty Helper ──────────────────────────────────
def process_loyalty_earning(order):
    """Calculate and grant loyalty points based on order total."""
    if not order or not order.customer_id: return
    
    settings = CafeSettings.query.filter_by(tenant_id=order.tenant_id).first()
    if not settings: return
    
    ratio = settings.loyalty_points_per_100 or 10.0
    points_earned = (order.total / 100.0) * ratio
    
    customer = Customer.query.get(order.customer_id)
    if customer:
        customer.loyalty_points += points_earned
        db.session.commit()

@app.route('/api/orders', methods=['POST'])
@staff_required
def create_order():
    try:
        d = request.json or {}
        tid = get_current_tenant_id()
        if not tid:
            return jsonify({'error': 'Unauthorized or session expired'}), 401
        
        # Validate request data
        if 'items' not in d or not isinstance(d['items'], list):
            return jsonify({'error': 'Invalid request: missing or invalid items array'}), 400
        if not d['items']:
            return jsonify({'error': 'Invalid request: items array cannot be empty'}), 400
        
        uid = session.get('user_id')
        s = Session.query.filter_by(user_id=uid, status='open').first() if uid else None
        if not s:
            return jsonify({'error':'No open session. Please open register first.'}), 400
            
        branch_id = session.get('active_branch_id')
        settings = CafeSettings.query.filter_by(tenant_id=tid).first()
        global_tax_rate = settings.tax_rate if settings else 0.0

        subtotal = 0
        total_item_tax = 0
        total_qty = 0
        tax_breakdown = {} # Label -> total amount

        order_items_data = []

        for item in d['items']:
            # Validate item
            if not isinstance(item, dict) or 'product_id' not in item or 'price' not in item or 'qty' not in item:
                return jsonify({'error': 'Invalid item: missing product_id, price, or qty'}), 400
            
            try:
                prod = Product.query.get(item['product_id'])
                item_price = float(item['price'])
                qty = int(item['qty'])
                if qty <= 0:
                    return jsonify({'error': 'Invalid item: qty must be greater than 0'}), 400
            except (ValueError, TypeError):
                return jsonify({'error': 'Invalid item: price or qty must be numeric'}), 400
            
            item_subtotal = item_price * qty
            subtotal += item_subtotal
            total_qty += qty

            # Item-level taxes
            tax_config = {}
            if prod and prod.tax_config_json:
                try:
                    tax_config = json.loads(prod.tax_config_json)
                except: pass
            
            # If no custom config, fallback to product.tax if > 0
            if not tax_config and prod and prod.tax > 0:
                tax_config = {"Tax": prod.tax}
            
            item_tax_total = 0
            item_tax_details = {}
            for tax_label, rate in tax_config.items():
                t_amt = round(item_subtotal * (float(rate) / 100), 2)
                item_tax_total += t_amt
                item_tax_details[tax_label] = t_amt
                tax_breakdown[tax_label] = tax_breakdown.get(tax_label, 0) + t_amt
            
            total_item_tax += item_tax_total
            order_items_data.append({
                'product_id': item['product_id'],
                'name': item['name'],
                'qty': qty,
                'price': item_price,
                'notes': item.get('notes', ''),
                'tax_rate': sum(float(r) for r in tax_config.values()),
                'tax_amount': item_tax_total,
                'tax_info_json': json.dumps(item_tax_details)
            })

        # Second layer: Global Tax
        intermediate_total = subtotal + total_item_tax
        global_tax_amount = round(intermediate_total * (global_tax_rate / 100), 2)
        if global_tax_rate > 0:
            tax_breakdown['Service Tax'] = tax_breakdown.get('Service Tax', 0) + global_tax_amount

        raw_total = intermediate_total + global_tax_amount
        final_total = round(raw_total)
        round_off = round(final_total - raw_total, 2)

        table_id = d.get('table_id')  # None for takeaway
        is_takeaway = d.get('takeaway', False) or not table_id
        customer_name = d.get('customer_name', '').strip()
        customer_phone = d.get('customer_phone', '').strip()
        
        customer_id = None
        if customer_phone:
            c = Customer.query.filter_by(tenant_id=tid, phone=customer_phone).first()
            if not c:
                c = Customer(phone=customer_phone, name=customer_name, tenant_id=tid)
                db.session.add(c)
                db.session.flush()
            else:
                if customer_name and c.name != customer_name:
                    c.name = customer_name
            customer_id = c.id
            customer_name = c.name

        o = None
        if table_id and not is_takeaway:
            o = (
                Order.query
                .filter_by(session_id=s.id, table_id=table_id, branch_id=branch_id)
                .filter(Order.status.in_(['draft', 'sent']))
                .order_by(Order.created_at.desc())
                .first()
            )

        if o:
            for item_data in order_items_data:
                oi = OrderItem(
                    order_id=o.id,
                    product_id=item_data['product_id'],
                    product_name=item_data['name'],
                    qty=item_data['qty'],
                    price=item_data['price'],
                    notes=item_data['notes'],
                    tax_rate=item_data['tax_rate'],
                    tax_amount=item_data['tax_amount'],
                    tax_info_json=item_data['tax_info_json']
                )
                db.session.add(oi)
            o.subtotal = (o.subtotal or 0) + subtotal
            o.tax_amount = (o.tax_amount or 0) + total_item_tax
            o.total = (o.total or 0) + final_total
            o.round_off = (o.round_off or 0) + round_off
            o.total_qty = (o.total_qty or 0) + total_qty
            
            # Merge tax breakdown
            try:
                old_breakdown = json.loads(o.tax_breakdown_json or '{}')
            except: old_breakdown = {}
            for k, v in tax_breakdown.items():
                old_breakdown[k] = old_breakdown.get(k, 0) + v
            o.tax_breakdown_json = json.dumps(old_breakdown)
            if customer_id:
                o.customer_id = customer_id
                o.customer_phone = customer_phone
                o.customer_name = customer_name
            if table_id:
                t = Table.query.get(table_id)
                if t:
                    t.status = 'occupied'
            order_num = o.order_number
        else:
            count = Order.query.count() + 1
            order_num = f"ORD-{count:04d}"
            o = Order(
                order_number=order_num,
                table_id=table_id if not is_takeaway else None,
                session_id=s.id,
                user_id=session['user_id'],
                subtotal=subtotal,
                tax_amount=total_item_tax,
                tax_breakdown_json=json.dumps(tax_breakdown),
                round_off=round_off,
                total_qty=total_qty,
                total=final_total,
                branch_id=branch_id,
                tenant_id=get_current_tenant_id(),
            )
            if customer_name:
                o.customer_name = customer_name
            if customer_phone:
                o.customer_phone = customer_phone
                o.customer_id = customer_id
            db.session.add(o)
            db.session.flush()
            for item_data in order_items_data:
                oi = OrderItem(
                    order_id=o.id,
                    product_id=item_data['product_id'],
                    product_name=item_data['name'],
                    qty=item_data['qty'],
                    price=item_data['price'],
                    notes=item_data['notes'],
                    tax_rate=item_data['tax_rate'],
                    tax_amount=item_data['tax_amount'],
                    tax_info_json=item_data['tax_info_json']
                )
                db.session.add(oi)
            if table_id and not is_takeaway:
                t = Table.query.get(table_id)
                if t:
                    t.status = 'occupied'
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': f'Database error: {str(e)}'}), 500
        
        if not o or not o.id:
            return jsonify({'error': 'Failed to create order'}), 500
        
        return jsonify({'ok':True,'id':o.id,'order_number':order_num})
    
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500

def serialize_bill(order):
    subtotal = sum(i.qty * i.price for i in order.items)
    is_sent = order.sent_to_kitchen_at or order.status == 'sent' or order.status == 'paid'
    
    # Calculate tax data
    tax_breakdown = {}
    total_tax = 0
    if order.tax_breakdown_json:
        try:
            tax_breakdown = json.loads(order.tax_breakdown_json)
            total_tax = sum(tax_breakdown.values())
        except: pass

    return {
        'id': order.id,
        'order_number': order.order_number,
        'table_id': order.table_id,
        'table': order.table.number if order.table else 'Takeaway',
        'customer_name': order.customer_name or 'Walk-in',
        'customer_phone': order.customer_phone or '',
        'is_takeaway': order.table_id is None,
        'status': order.status,
        'subtotal': subtotal,
        'tax_amount': total_tax,
        'tax_breakdown': tax_breakdown,
        'round_off': order.round_off or 0,
        'total': order.total if is_sent else 0,
        'total_qty': order.total_qty or sum(i.qty for i in order.items),
        'tip': order.tip or 0,
        'created_at': order.created_at.isoformat() if order.created_at else None,
        'sent_to_kitchen_at': order.sent_to_kitchen_at.isoformat() if order.sent_to_kitchen_at else None,
        'items': [{
            'id': i.id,
            'product_id': i.product_id,
            'name': i.product_name,
            'qty': i.qty,
            'price': i.price,
            'tax_amount': i.tax_amount or 0,
            'notes': i.notes or '',
        } for i in order.items],
    }

@app.route('/api/orders/<int:oid>/send-kitchen', methods=['POST'])
@staff_required
def send_to_kitchen(oid):
    try:
        o = Order.query.filter_by(id=oid, tenant_id=get_current_tenant_id()).first_or_404()
        access_error = require_branch_access_or_403(o.branch_id)
        if access_error:
            return access_error
        if o.status == 'paid':
            return jsonify({'error': 'Cannot send paid order to kitchen'}), 400
        pending_items = [item for item in o.items if item.kitchen_status == 'pending']
        if not pending_items and o.status == 'sent':
            return jsonify({'ok': True, 'message': 'Order already sent to kitchen'})

        o.status = 'sent'
        o.sent_to_kitchen_at = o.sent_to_kitchen_at or datetime.utcnow()

        kt = KitchenTicket.query.filter_by(order_id=oid).order_by(KitchenTicket.sent_at.desc()).first()
        created_new_ticket = False
        if not kt or kt.status == 'completed':
            kt = KitchenTicket(order_id=oid, tenant_id=o.tenant_id)
            db.session.add(kt)
            created_new_ticket = True

        for item in pending_items:
            item.kitchen_status = 'to_cook'
        db.session.commit()
        
        ticket_data = {
            'id': kt.id,
            'order_id': o.id,
            'order_number': o.order_number,
            'table': o.table.number if o.table else 'Takeaway',
            'status': kt.status if kt.status in ('to_cook', 'preparing', 'completed') else 'to_cook',
            'total': o.total,
            'sent_at': kt.sent_at.isoformat(),
            'items': [{'id':i.id,'name':i.product_name,'qty':i.qty,'price':i.price,'status':i.kitchen_status} for i in o.items]
        }
        if created_new_ticket:
            socketio.emit('new_ticket', ticket_data)
        else:
            socketio.emit('ticket_update', {'id': kt.id, 'status': kt.status, 'items': ticket_data['items'], 'order_number': o.order_number})
        socketio.emit('order_update', {'order_number': o.order_number, 'status': 'preparing'})
        return jsonify({'ok': True, 'message': 'Order sent to kitchen'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bills', methods=['GET'])
@staff_required
def get_bills():
    s = Session.query.filter_by(user_id=session['user_id'], status='open').first()
    if not s:
        return jsonify([])
    orders = apply_branch_scope(
        Order.query.filter_by(session_id=s.id, status='sent'),
        Order.branch_id,
    ).order_by(Order.created_at.desc()).all()
    return jsonify([serialize_bill(o) for o in orders])

@app.route('/api/orders/all', methods=['GET'])
@admin_required
def get_all_orders():
    tid = get_current_tenant_id()
    # Deep query for analytics, limited to last 1000 for performance
    orders = Order.query.filter_by(tenant_id=tid).order_by(Order.created_at.desc()).limit(1000).all()
    return jsonify([serialize_bill(o) for o in orders])

@app.route('/api/bills/table/<int:tid>', methods=['GET'])
@staff_required
def get_bill_for_table(tid):
    s = Session.query.filter_by(user_id=session['user_id'], status='open').first()
    if not s:
        return jsonify({'bill': None})
    order = (
        Order.query
        .filter_by(session_id=s.id, table_id=tid, status='sent', branch_id=get_active_branch_id(), tenant_id=get_current_tenant_id())
        .order_by(Order.created_at.desc())
        .first()
    )
    if not order:
        return jsonify({'bill': None})
    return jsonify({'bill': serialize_bill(order)})

@app.route('/api/orders/<int:oid>/pay', methods=['POST'])
@staff_required
def pay_order(oid):
    o = Order.query.filter_by(id=oid, tenant_id=get_current_tenant_id()).first_or_404()
    access_error = require_branch_access_or_403(o.branch_id)
    if access_error:
        return access_error
    d = request.json
    
    o.status = 'paid'
    o.payment_method = d.get('method','cash')
    o.tip = float(d.get('tip', 0) or 0)
    
    # Recalculate grand total based on persisted total (Sub + Taxes) + Tip
    # Actually, order.total already has Sub + Taxes + RoundOff (calculated in create_order)
    # We just need to ensure tip is part of the final captured amount if needed for reporting.
    
    if o.table:
        o.table.status = 'free'
    db.session.commit()
    socketio.emit('order_paid', {'order_number': o.order_number, 'total': o.total, 'tip': o.tip, 'method': o.payment_method})
    return jsonify({'ok':True})

@app.route('/api/orders/<int:oid>', methods=['DELETE'])
@staff_required
def delete_order(oid):
    o = Order.query.filter_by(id=oid, tenant_id=get_current_tenant_id()).first_or_404()
    access_error = require_branch_access_or_403(o.branch_id)
    if access_error:
        return access_error
    if o.status == 'paid':
        return jsonify({'error': 'Cannot delete a paid bill'}), 400

    table_id = o.table_id
    db.session.query(KitchenTicket).filter_by(order_id=o.id).delete(synchronize_session=False)
    db.session.delete(o)

    if table_id:
        has_active_orders = (
            Order.query
            .filter(Order.table_id == table_id, Order.id != oid, Order.status.in_(['draft', 'sent']), Order.branch_id == o.branch_id)
            .first()
        )
        if not has_active_orders:
            table = Table.query.get(table_id)
            if table:
                table.status = 'free'

    db.session.commit()
    socketio.emit('order_deleted', {'order_id': oid, 'table_id': table_id})
    return jsonify({'ok': True})

@app.route('/api/orders/table/<int:tid>', methods=['GET'])
@staff_required
def get_table_order(tid):
    o = (
        Order.query
        .filter_by(table_id=tid, status='draft', branch_id=get_active_branch_id())
        .order_by(Order.created_at.desc())
        .first()
    )
    if not o:
        return jsonify({'order': None})
    return jsonify({'order': {
        'id': o.id, 'order_number': o.order_number, 'status': o.status, 'total': o.total,
        'items': [{'id':i.id,'product_id':i.product_id,'name':i.product_name,'qty':i.qty,'price':i.price} for i in o.items]
    }})

# ─── API: Kitchen ──────────────────────────────────────────
def get_avg_prep_minutes():
    """Rolling average prep time from last 10 completed tickets."""
    completed = (
        KitchenTicket.query
        .join(Order, Order.id == KitchenTicket.order_id)
        .filter(KitchenTicket.status == 'completed',
                Order.branch_id == get_active_branch_id(),
                KitchenTicket.started_at.isnot(None),
                KitchenTicket.completed_at.isnot(None))
        .order_by(KitchenTicket.completed_at.desc())
        .limit(10)
        .all()
    )
    if not completed:
        return 15  # default estimate
    total = sum((kt.completed_at - kt.started_at).total_seconds() for kt in completed)
    return max(1, int(total / len(completed) / 60))

@app.route('/api/kitchen/orders', methods=['GET'])
@app.route('/api/kitchen/tickets', methods=['GET'])
def get_tickets():
    tickets = (
        KitchenTicket.query
        .join(Order, Order.id == KitchenTicket.order_id)
        .filter(KitchenTicket.status != 'completed', Order.branch_id == get_active_branch_id(), KitchenTicket.tenant_id == get_current_tenant_id())
        .order_by(KitchenTicket.sent_at.asc())
        .all()
    )
    result = []
    avg_prep = get_avg_prep_minutes()
    now = datetime.utcnow()
    for kt in tickets:
        o = kt.order
        total_price = sum(i.qty * i.price for i in o.items)
        time_in_preparation = 0
        if kt.started_at:
            time_in_preparation = int((now - kt.started_at).total_seconds() / 60)
        # Estimated time remaining
        if kt.status == 'to_cook':
            eta_minutes = avg_prep
        elif kt.status == 'preparing':
            eta_minutes = max(0, avg_prep - time_in_preparation)
        else:
            eta_minutes = 0
        result.append({
            'id': kt.id,
            'order_id': o.id,
            'order_number': o.order_number,
            'table': o.table.number if o.table else 'Takeaway',
            'is_takeaway': o.table_id is None,
            'customer_name': getattr(o, 'customer_name', None) or '',
            'status': kt.status,
            'sent_at': kt.sent_at.isoformat(),
            'started_at': kt.started_at.isoformat() if kt.started_at else None,
            'total': total_price,
            'time_in_prep': time_in_preparation,
            'eta_minutes': eta_minutes,
            'avg_prep_minutes': avg_prep,
            'items': [{
                'id': i.id,
                'name': i.product_name,
                'qty': i.qty,
                'price': i.price,
                'notes': i.notes or '',
                'status': i.kitchen_status,
                'started_at': i.started_at.isoformat() if i.started_at else None,
                'completed_at': i.completed_at.isoformat() if i.completed_at else None
            } for i in o.items]
        })
    return jsonify(result)

@app.route('/api/kitchen/tickets/<int:kid>/advance', methods=['POST'])
@staff_required
def advance_ticket(kid):
    kt = KitchenTicket.query.filter_by(id=kid, tenant_id=get_current_tenant_id()).first_or_404()
    o = kt.order
    access_error = require_branch_access_or_403(o.branch_id)
    if access_error:
        return access_error
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
    item = OrderItem.query.join(Order).filter(
        OrderItem.id == item_id,
        Order.tenant_id == get_current_tenant_id()
    ).first_or_404()
    access_error = require_branch_access_or_403(item.order.branch_id)
    if access_error:
        return access_error
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

# ─── API: Reservations ────────────────────────────────────
@app.route('/api/reservations', methods=['GET'])
@login_required
def get_my_reservations():
    uid = session['user_id']
    role = normalize_role(session.get('user_role'))
    tid = get_current_tenant_id()
    if role == 'customer':
        reservations = Reservation.query.filter_by(customer_id=uid, tenant_id=tid).order_by(Reservation.reserved_at.asc()).all()
    else:
        # Staff/admin see all upcoming reservations
        reservations = Reservation.query.filter(
            Reservation.reserved_at >= datetime.utcnow() - timedelta(hours=2),
            Reservation.tenant_id == tid
        ).order_by(Reservation.reserved_at.asc()).all()
    return jsonify([_serialize_reservation(r) for r in reservations])

def _serialize_reservation(r):
    return {
        'id': r.id,
        'customer_id': r.customer_id,
        'customer_name': r.customer.name if r.customer else 'Guest',
        'table_id': r.table_id,
        'table': r.table.number if r.table else None,
        'reserved_at': r.reserved_at.isoformat(),
        'party_size': r.party_size,
        'status': r.status,
        'notes': r.notes,
        'created_at': r.created_at.isoformat(),
        'items': [{
            'product_id': i.product_id,
            'product_name': i.product_name,
            'qty': i.qty,
            'price': i.price,
            'notes': i.notes or '',
        } for i in r.items]
    }

@app.route('/api/reservations', methods=['POST'])
@login_required
def create_reservation():
    d = request.json or {}
    tid = get_current_tenant_id()
    try:
        dt_str = (d.get('reserved_at') or '').replace('Z', '+00:00')
        reserved_at = datetime.fromisoformat(dt_str)
        # Strip timezone info so we compare as naive UTC
        if reserved_at.tzinfo is not None:
            # Convert to UTC, then make naive
            import datetime as dt_mod
            reserved_at = reserved_at.utctimetuple()
            reserved_at = datetime(*reserved_at[:6])
    except (ValueError, TypeError, AttributeError):
        return jsonify({'error': 'Invalid date/time format'}), 400
    if reserved_at < datetime.utcnow():
        return jsonify({'error': 'Cannot reserve in the past'}), 400
    table_id = d.get('table_id')
    if table_id:
        # Check for conflicting reservation (±90 min window)
        window_start = reserved_at - timedelta(minutes=90)
        window_end = reserved_at + timedelta(minutes=90)
        conflict = Reservation.query.filter(
            Reservation.table_id == table_id,
            Reservation.status.in_(['pending', 'confirmed']),
            Reservation.reserved_at >= window_start,
            Reservation.reserved_at <= window_end,
            Reservation.tenant_id == tid,
        ).first()
        if conflict:
            return jsonify({'error': 'Table already reserved in this time window'}), 409
    r = Reservation(
        customer_id=session['user_id'],
        table_id=table_id,
        reserved_at=reserved_at,
        party_size=int(d.get('party_size', 2)),
        notes=d.get('notes', ''),
        tenant_id=tid,
    )
    db.session.add(r)
    db.session.flush()
    for item in d.get('items', []):
        ri = ReservationItem(
            reservation_id=r.id,
            product_id=item.get('product_id'),
            product_name=item.get('name', ''),
            qty=int(item.get('qty', 1)),
            price=float(item.get('price', 0)),
            notes=item.get('notes', ''),
        )
        db.session.add(ri)
    db.session.commit()
    return jsonify({'ok': True, 'id': r.id, 'reservation': _serialize_reservation(r)})

@app.route('/api/reservations/<int:rid>', methods=['PUT'])
@login_required
def update_reservation(rid):
    r = Reservation.query.get_or_404(rid)
    if r.tenant_id != get_current_tenant_id():
        return jsonify({'error': 'forbidden'}), 403
    uid = session['user_id']
    role = normalize_role(session.get('user_role'))
    if role == 'customer' and r.customer_id != uid:
        return jsonify({'error': 'forbidden'}), 403
    d = request.json or {}
    if 'reserved_at' in d:
        try:
            r.reserved_at = datetime.fromisoformat(d['reserved_at'])
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid date/time'}), 400
    if 'table_id' in d:
        r.table_id = d['table_id']
    if 'party_size' in d:
        r.party_size = int(d['party_size'])
    if 'notes' in d:
        r.notes = d['notes']
    if 'items' in d:
        ReservationItem.query.filter_by(reservation_id=r.id).delete()
        for item in d['items']:
            ri = ReservationItem(
                reservation_id=r.id,
                product_id=item.get('product_id'),
                product_name=item.get('name', ''),
                qty=int(item.get('qty', 1)),
                price=float(item.get('price', 0)),
                notes=item.get('notes', ''),
            )
            db.session.add(ri)
    db.session.commit()
    return jsonify({'ok': True, 'reservation': _serialize_reservation(r)})

@app.route('/api/reservations/<int:rid>', methods=['DELETE'])
@login_required
def cancel_reservation(rid):
    r = Reservation.query.get_or_404(rid)
    if r.tenant_id != get_current_tenant_id():
        return jsonify({'error': 'forbidden'}), 403
    uid = session['user_id']
    role = normalize_role(session.get('user_role'))
    if role == 'customer' and r.customer_id != uid:
        return jsonify({'error': 'forbidden'}), 403
    r.status = 'cancelled'
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/reservations/<int:rid>/seat', methods=['POST'])
@staff_required
def seat_reservation(rid):
    """Staff action: seat the party and auto-convert pre-order to kitchen ticket."""
    r = Reservation.query.get_or_404(rid)
    if r.tenant_id != get_current_tenant_id():
        return jsonify({'error': 'forbidden'}), 403
    r.status = 'seated'
    # Mark table occupied
    if r.table:
        r.table.status = 'occupied'
    # Convert pre-order items to a live Order
    if r.items:
        s = Session.query.filter_by(user_id=session['user_id'], status='open').first()
        if not s:
            s = Session(user_id=session['user_id'])
            db.session.add(s)
            db.session.flush()
        count = Order.query.count() + 1
        order_num = f'ORD-{count:04d}'
        total = sum(i.qty * i.price for i in r.items)
        o = Order(
            order_number=order_num,
            table_id=r.table_id,
            session_id=s.id,
            user_id=session['user_id'],
            branch_id=get_active_branch_id(),
            tenant_id=get_current_tenant_id(),
            total=total,
            status='sent',
            sent_to_kitchen_at=datetime.utcnow(),
        )
        db.session.add(o)
        db.session.flush()
        for ri in r.items:
            oi = OrderItem(
                order_id=o.id,
                product_id=ri.product_id,
                product_name=ri.product_name,
                qty=ri.qty,
                price=ri.price,
                notes=ri.notes or '',
                kitchen_status='to_cook',
            )
            db.session.add(oi)
        kt = KitchenTicket(order_id=o.id, tenant_id=get_current_tenant_id())
        db.session.add(kt)
        db.session.commit()
        ticket_data = {
            'id': kt.id,
            'order_id': o.id,
            'order_number': o.order_number,
            'table': r.table.number if r.table else 'Takeaway',
            'status': 'to_cook',
            'total': total,
            'sent_at': kt.sent_at.isoformat(),
            'items': [{'id': i.id, 'name': i.product_name, 'qty': i.qty, 'price': i.price, 'notes': i.notes or '', 'status': i.kitchen_status} for i in o.items]
        }
        socketio.emit('new_ticket', ticket_data)
    else:
        db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/reservations/<int:rid>/confirm', methods=['POST'])
@staff_required
def confirm_reservation(rid):
    r = Reservation.query.get_or_404(rid)
    if r.tenant_id != get_current_tenant_id():
        return jsonify({'error': 'forbidden'}), 403
    r.status = 'confirmed'
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/reservations/<int:rid>/done', methods=['POST'])
@staff_required
def finish_reservation(rid):
    """Staff action: mark reservation as done and free up the table."""
    r = Reservation.query.get_or_404(rid)
    if r.tenant_id != get_current_tenant_id():
        return jsonify({'error': 'forbidden'}), 403
    r.status = 'completed'
    
    # Mark table as free
    if r.table:
        r.table.status = 'free'
    
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/tables/availability', methods=['GET'])
def table_availability():
    """Return tables available for a given ISO datetime slot."""
    dt_str = request.args.get('datetime', '')
    try:
        dt = datetime.fromisoformat(dt_str)
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid datetime'}), 400
    window_start = dt - timedelta(minutes=90)
    window_end = dt + timedelta(minutes=90)
    busy_table_ids = set(
        r.table_id for r in Reservation.query.filter(
            Reservation.status.in_(['pending', 'confirmed']),
            Reservation.reserved_at >= window_start,
            Reservation.reserved_at <= window_end,
            Reservation.table_id.isnot(None),
        ).all()
    )
    floors = apply_tenant_scope(Floor.query, Floor).all()
    result = []
    for f in floors:
        tables = []
        for t in f.tables:
            if t.active:
                tables.append({
                    'id': t.id,
                    'number': t.number,
                    'seats': t.seats,
                    'status': t.status,
                    'available_for_reservation': t.id not in busy_table_ids,
                })
        result.append({'id': f.id, 'name': f.name, 'tables': tables})
    return jsonify(result)

# ─── API: Self-Order (Customer QR) ────────────────────────
@app.route('/table/<int:table_id>/order')
def self_order_page(table_id):
    t = Table.query.filter_by(id=table_id, tenant_id=get_current_tenant_id()).first_or_404()
    return render_template('self_order.html',
        table_id=table_id,
        table_number=t.number,
        user_name=session.get('user_name'),
        user_role=session.get('user_role'),
        is_logged_in='user_id' in session,
    )

@app.route('/api/self-order', methods=['POST'])
def create_self_order():
    """Customer QR self-order: creates an order and sends directly to kitchen.
    Requires login (customer or any role)."""
    if 'user_id' not in session:
        return jsonify({'error': 'Please log in to place your order'}), 401
    d = request.json or {}
    table_id = d.get('table_id')
    items = d.get('items', [])
    if not items:
        return jsonify({'error': 'No items in order'}), 400
    if not table_id:
        return jsonify({'error': 'Table ID required'}), 400
    t = Table.query.get_or_404(table_id)
    total = sum(item['price'] * item['qty'] for item in items)
    # Use or create a session for this user
    s = Session.query.filter_by(user_id=session['user_id'], status='open').first()
    if not s:
        # Find or create a staff/admin session to attach to
        from sqlalchemy import or_
        staff = User.query.filter(
            User.role.in_(['restaurant', 'cashier', 'manager'])
        ).first()
        if staff:
            s = Session.query.filter_by(user_id=staff.id, status='open').first()
        if not s:
            s = Session(user_id=session['user_id'])
            db.session.add(s)
            db.session.flush()
    count = Order.query.count() + 1
    order_num = f'ORD-{count:04d}'
    tid = get_current_tenant_id()
    o = Order(
        order_number=order_num,
        table_id=table_id,
        session_id=s.id,
        user_id=session['user_id'],
        branch_id=get_active_branch_id() or getattr(get_current_user(), 'branch_id', None),
        tenant_id=tid,
        total=total,
        status='sent',
        sent_to_kitchen_at=datetime.utcnow(),
    )
    db.session.add(o)
    db.session.flush()
    for item in items:
        oi = OrderItem(
            order_id=o.id,
            product_id=item.get('product_id'),
            product_name=item['name'],
            qty=item['qty'],
            price=item['price'],
            notes=item.get('notes', ''),
            kitchen_status='to_cook',
        )
        db.session.add(oi)
    t.status = 'occupied'
    kt = KitchenTicket(order_id=o.id, tenant_id=tid)
    db.session.add(kt)
    db.session.commit()
    ticket_data = {
        'id': kt.id,
        'order_id': o.id,
        'order_number': o.order_number,
        'table': t.number,
        'is_takeaway': False,
        'status': 'to_cook',
        'total': total,
        'sent_at': kt.sent_at.isoformat(),
        'items': [{
            'id': i.id, 'name': i.product_name, 'qty': i.qty,
            'price': i.price, 'notes': i.notes or '', 'status': i.kitchen_status
        } for i in o.items]
    }
    socketio.emit('new_ticket', ticket_data)
    socketio.emit('order_update', {'order_number': o.order_number, 'status': 'to_cook'})
    return jsonify({'ok': True, 'order_id': o.id, 'order_number': o.order_number})

@app.route('/api/self-order/<int:oid>/status', methods=['GET'])
def self_order_status(oid):
    o = Order.query.filter_by(id=oid, tenant_id=get_current_tenant_id()).first_or_404()
    access_error = require_branch_access_or_403(o.branch_id)
    if access_error:
        return access_error
    kt = KitchenTicket.query.filter_by(order_id=oid).order_by(KitchenTicket.sent_at.desc()).first()
    return jsonify({
        'order_id': o.id,
        'order_number': o.order_number,
        'status': kt.status if kt else o.status,
        'table': o.table.number if o.table else 'Takeaway',
        'items': [{'name': i.product_name, 'qty': i.qty, 'notes': i.notes or ''} for i in o.items],
        'total': o.total,
    })

@app.route('/api/qr/table/<int:table_id>')
def table_qr_code(table_id):
    """Generate a QR code for the table's self-order URL."""
    t = Table.query.get_or_404(table_id)
    url = request.host_url.rstrip('/') + f'/table/{table_id}/order'
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()
    return jsonify({'qr': f'data:image/png;base64,{b64}', 'url': url, 'table': t.number})

# ─── API: Push Notifications ──────────────────────────────
@app.route('/api/push/subscribe', methods=['POST'])
@login_required
def push_subscribe():
    d = request.json or {}
    sub = d.get('subscription')
    if not sub:
        return jsonify({'error': 'No subscription data'}), 400
    sub_json = json.dumps(sub)
    # Upsert: replace existing subscription for this user
    existing = PushSubscription.query.filter_by(user_id=session['user_id']).first()
    if existing:
        existing.subscription_json = sub_json
    else:
        ps = PushSubscription(user_id=session['user_id'], subscription_json=sub_json)
        db.session.add(ps)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/push/subscribe/table', methods=['POST'])
def push_subscribe_table():
    """Guest push subscription for a specific table (QR self-order)."""
    d = request.json or {}
    sub = d.get('subscription')
    table_id = d.get('table_id')
    if not sub or not table_id:
        return jsonify({'error': 'Missing data'}), 400
    sub_json = json.dumps(sub)
    existing = PushSubscription.query.filter_by(table_id=table_id, user_id=None).first()
    if existing:
        existing.subscription_json = sub_json
    else:
        ps = PushSubscription(table_id=table_id, subscription_json=sub_json)
        db.session.add(ps)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/push/vapid-public-key', methods=['GET'])
def get_vapid_public_key():
    key = os.getenv('VAPID_PUBLIC_KEY', '')
    return jsonify({'key': key})

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
    orders = apply_tenant_scope(apply_branch_scope(Order.query, Order.branch_id), Order).filter(Order.status=='paid', Order.created_at>=start).all()
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

def parse_report_date(value, default=None):
    value = (value or '').strip()
    if not value:
        return default
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return default

@app.route('/api/branches', methods=['GET'])
@admin_required
def get_branches():
    user = get_current_user()
    tid = get_current_tenant_id()
    if is_superadmin(user):
        branches = Branch.query.filter_by(tenant_id=tid).order_by(Branch.name.asc()).all()
    else:
        branches = Branch.query.filter_by(id=user.branch_id, tenant_id=tid).all()
    return jsonify({
        'branches': [{
            'id': branch.id,
            'name': branch.name,
            'address': branch.address,
            'created_at': branch.created_at.isoformat() if branch.created_at else None,
        } for branch in branches],
        'active_branch_id': get_active_branch_id(user),
        'is_superadmin': is_superadmin(user),
    })

@app.route('/api/branches', methods=['POST'])
@admin_required
def create_branch():
    user = get_current_user()
    if not is_superadmin(user):
        return jsonify({'error': 'Only super-admins can add branches'}), 403
    d = request.json or {}
    name = (d.get('name') or '').strip()
    address = (d.get('address') or '').strip()
    if not name:
        return jsonify({'error': 'Branch name is required'}), 400
    tid = get_current_tenant_id()
    if Branch.query.filter(db.func.lower(Branch.name) == name.lower(), Branch.tenant_id == tid).first():
        return jsonify({'error': 'Branch already exists'}), 400
    branch = Branch(name=name, address=address, tenant_id=tid)
    db.session.add(branch)
    db.session.commit()
    return jsonify({'ok': True, 'id': branch.id, 'name': branch.name})

@app.route('/api/branches/switch', methods=['POST'])
@admin_required
def switch_branch():
    user = get_current_user()
    if not is_superadmin(user):
        return jsonify({'error': 'Only super-admins can switch branches'}), 403
    branch_id = request.json.get('branch_id') if request.json else None
    try:
        branch_id = int(branch_id)
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid branch'}), 400
    branch = Branch.query.filter_by(id=branch_id, tenant_id=get_current_tenant_id()).first_or_404()
    session['active_branch_id'] = branch.id
    return jsonify({'ok': True, 'active_branch_id': branch.id, 'branch_name': branch.name})

@app.route('/api/attendance/status', methods=['GET'])
@staff_required
def attendance_status():
    user = get_current_user()
    open_shift = get_current_shift_start(user.id)
    return jsonify({
        'clocked_in': bool(open_shift),
        'current_shift_started_at': utc_iso(open_shift.timestamp) if open_shift else None,
        'hourly_rate': float(user.hourly_rate or 0),
        'branch_id': get_active_branch_id(user),
        'tenant_id': get_current_tenant_id(),
    })

@app.route('/api/attendance/clock', methods=['POST'])
@staff_required
def toggle_attendance_clock():
    user = get_current_user()
    action = (request.json or {}).get('action', '').strip().lower()
    if action not in ('in', 'out'):
        return jsonify({'error': 'Action must be "in" or "out"'}), 400
    open_shift = get_current_shift_start(user.id)
    if action == 'in' and open_shift:
        return jsonify({'error': 'You are already clocked in'}), 400
    if action == 'out' and not open_shift:
        return jsonify({'error': 'You are not clocked in'}), 400

    event = AttendanceEvent(
        staff_id=user.id,
        branch_id=get_active_branch_id(user),
        tenant_id=get_current_tenant_id(),
        action=action,
        timestamp=datetime.utcnow(),
    )
    db.session.add(event)
    db.session.commit()
    return jsonify({
        'ok': True,
        'action': action,
        'timestamp': utc_iso(event.timestamp),
        'clocked_in': action == 'in',
    })

@app.route('/api/admin/attendance-report', methods=['GET'])
@admin_required
def attendance_report():
    user = get_current_user()
    staff_id = request.args.get('staff_id', '').strip()
    try:
        staff_id = int(staff_id) if staff_id else None
    except ValueError:
        return jsonify({'error': 'Invalid staff filter'}), 400

    start_date = parse_report_date(request.args.get('start_date'))
    end_date = parse_report_date(request.args.get('end_date'))
    attendance_query = apply_tenant_scope(apply_branch_scope(
        AttendanceEvent.query.join(User, User.id == AttendanceEvent.staff_id),
        AttendanceEvent.branch_id,
        include_all_for_superadmin=False,
    ), AttendanceEvent)
    if staff_id:
        attendance_query = attendance_query.filter(AttendanceEvent.staff_id == staff_id)
    events = attendance_query.order_by(AttendanceEvent.timestamp.asc(), AttendanceEvent.id.asc()).all()
    rows = build_attendance_shifts(events, start_date=start_date, end_date=end_date, staff_filter=staff_id)

    staff_query = apply_tenant_scope(apply_branch_scope(User.query, User.branch_id), User)
    staff_options = staff_query.filter(User.role != 'customer').order_by(User.name.asc()).all()
    return jsonify({
        'rows': [{
            'clock_in_event_id': row['clock_in_event_id'],
            'clock_out_event_id': row['clock_out_event_id'],
            'staff_id': row['staff_id'],
            'staff_name': row['staff_name'],
            'date': row['date'],
            'clock_in_time': utc_iso(row['clock_in_at']),
            'clock_out_time': utc_iso(row['clock_out_at']),
            'hours_worked': row['hours_worked'],
            'hourly_rate': row['hourly_rate'],
            'pay': row['pay'],
            'is_open_shift': row['is_open_shift'],
            'branch_id': row['branch_id'],
        } for row in rows],
        'staff': [{
            'id': member.id,
            'name': member.name,
            'hourly_rate': float(member.hourly_rate or 0),
        } for member in staff_options],
    })

@app.route('/api/admin/attendance/shifts/<int:clock_in_event_id>', methods=['PATCH'])
@admin_required
def update_attendance_shift(clock_in_event_id):
    clock_in_event = AttendanceEvent.query.filter_by(
        id=clock_in_event_id,
        tenant_id=get_current_tenant_id()
    ).first_or_404()
    access_error = require_branch_access_or_403(clock_in_event.branch_id)
    if access_error:
        return access_error

    if clock_in_event.action != 'in':
        return jsonify({'error': 'Shift must start with a clock-in event'}), 400

    d = request.json or {}
    clock_out_at = d.get('clock_out_at')
    if not clock_out_at:
        return jsonify({'error': 'clock_out_at is required'}), 400
    try:
        parsed_clock_out = datetime.fromisoformat(clock_out_at)
    except ValueError:
        return jsonify({'error': 'Invalid clock-out timestamp'}), 400
    if parsed_clock_out < clock_in_event.timestamp:
        return jsonify({'error': 'Clock-out cannot be before clock-in'}), 400

    clock_out_event = None
    if d.get('clock_out_event_id'):
        clock_out_event = AttendanceEvent.query.get(int(d['clock_out_event_id']))
    if not clock_out_event:
        clock_out_event = AttendanceEvent.query.filter(
            AttendanceEvent.staff_id == clock_in_event.staff_id,
            AttendanceEvent.action == 'out',
            AttendanceEvent.timestamp >= clock_in_event.timestamp,
        ).order_by(AttendanceEvent.timestamp.asc(), AttendanceEvent.id.asc()).first()

    if clock_out_event and clock_out_event.action != 'out':
        clock_out_event = None

    if clock_out_event:
        clock_out_event.timestamp = parsed_clock_out
    else:
        clock_out_event = AttendanceEvent(
            staff_id=clock_in_event.staff_id,
            branch_id=clock_in_event.branch_id,
            action='out',
            timestamp=parsed_clock_out,
        )
        db.session.add(clock_out_event)
    db.session.commit()
    return jsonify({
        'ok': True,
        'clock_in_event_id': clock_in_event.id,
        'clock_out_event_id': clock_out_event.id,
        'clock_out_time': clock_out_event.timestamp.isoformat(),
    })

@app.route('/api/admin/branches/compare', methods=['GET'])
@admin_required
def compare_branches():
    user = get_current_user()
    tid = get_current_tenant_id()
    start_date = parse_report_date(request.args.get('start_date'))
    end_date = parse_report_date(request.args.get('end_date'))
    start_dt = datetime.combine(start_date, datetime.min.time()) if start_date else None
    end_dt = datetime.combine(end_date, datetime.max.time()) if end_date else None

    branch_query = Branch.query.filter_by(tenant_id=tid).order_by(Branch.name.asc())
    if not is_superadmin(user):
        branch_query = branch_query.filter(Branch.id == user.branch_id)
    branches = branch_query.all()

    cards = []
    for branch in branches:
        order_query = Order.query.filter(
            Order.branch_id == branch.id,
            Order.status == 'paid',
        )
        if start_dt:
            order_query = order_query.filter(Order.created_at >= start_dt)
        if end_dt:
            order_query = order_query.filter(Order.created_at <= end_dt)
        orders = order_query.all()
        total_orders = len(orders)
        total_revenue = round(sum(float(order.total or 0) for order in orders), 2)
        item_totals = {}
        for order in orders:
            for item in order.items:
                item_totals[item.product_name] = item_totals.get(item.product_name, 0) + item.qty
        top_item_name, top_item_qty = ('-', 0)
        if item_totals:
            top_item_name, top_item_qty = max(item_totals.items(), key=lambda entry: entry[1])
        cards.append({
            'branch_id': branch.id,
            'branch_name': branch.name,
            'address': branch.address,
            'total_orders': total_orders,
            'total_revenue': total_revenue,
            'top_selling_item': top_item_name,
            'top_selling_qty': top_item_qty,
        })
    return jsonify({'branches': cards})

# ─── API: Admin / User Management ──────────────────────────
@app.route('/api/users', methods=['GET'])
@staff_required
def get_users():
    user = User.query.get(session['user_id'])
    if not user or (normalize_role(user.role) != 'restaurant' and not user.is_superadmin):
        return jsonify({'error': 'unauthorized'}), 403

    users = apply_tenant_scope(apply_branch_scope(User.query, User.branch_id), User).filter(User.id != session['user_id']).all()
    return jsonify([{
        'id': u.id,
        'name': u.name,
        'email': u.email,
        'role': u.role,
        'created_at': u.created_at.isoformat(),
        'hourly_rate': float(u.hourly_rate or 0),
        'branch_id': u.branch_id,
        'branch_name': u.branch.name if u.branch else '',
        'is_superadmin': bool(u.is_superadmin),
    } for u in users])

@app.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    admin = get_current_user()
    if normalize_role(admin.role) not in ('restaurant', 'manager') and not admin.is_superadmin:
        return jsonify({'error': 'unauthorized'}), 403

    d = request.json or {}
    name = (d.get('name') or '').strip()
    email = (d.get('email') or '').strip()
    password = d.get('password') or ''
    role = normalize_role(d.get('role', 'cashier'))
    hourly_rate = float(d.get('hourly_rate', 0) or 0)
    branch_id = d.get('branch_id') or get_active_branch_id(admin)
    tenant_id = get_current_tenant_id()
    try:
        branch_id = int(branch_id) if branch_id else None
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid branch'}), 400

    if not name or not email or not password:
        return jsonify({'error': 'Name, email, and password are required'}), 400
    if find_user_by_email(email):
        return jsonify({'error': 'Email already exists'}), 400
    password_error = strong_password_error(password, email)
    if password_error:
        return jsonify({'error': password_error}), 400
    if not admin.is_superadmin:
        branch_id = admin.branch_id
    elif branch_id and not Branch.query.get(branch_id):
        return jsonify({'error': 'Branch not found'}), 404

    new_user = User(
        name=name,
        email=email,
        password=generate_password_hash(password, method='scrypt'),
        role=role,
        hourly_rate=hourly_rate,
        branch_id=branch_id,
        tenant_id=tenant_id,
        is_superadmin=bool(d.get('is_superadmin', False)) if admin.is_superadmin else False,
    )
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'ok': True, 'id': new_user.id})

@app.route('/api/users/<int:uid>', methods=['DELETE'])
@staff_required
def delete_user(uid):
    admin = User.query.get(session['user_id'])
    if not admin or (normalize_role(admin.role) != 'restaurant' and not admin.is_superadmin):
        return jsonify({'error': 'unauthorized'}), 403
    
    if uid == admin.id:
        return jsonify({'error': 'Cannot delete yourself'}), 400
    
    user = User.query.filter_by(id=uid, tenant_id=get_current_tenant_id()).first_or_404()
    access_error = require_branch_access_or_403(user.branch_id)
    if access_error:
        return access_error
    db.session.delete(user)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/users/<int:uid>', methods=['PUT'])
@admin_required
def update_user(uid):
    admin = get_current_user()
    user = User.query.filter_by(id=uid, tenant_id=get_current_tenant_id()).first_or_404()
    if uid == admin.id and 'role' in (request.json or {}):
        return jsonify({'error': 'You cannot change your own role'}), 400
    access_error = require_branch_access_or_403(user.branch_id)
    if access_error:
        return access_error

    d = request.json or {}
    name = (d.get('name') or user.name).strip()
    role = normalize_role(d.get('role', user.role))
    hourly_rate = float(d.get('hourly_rate', user.hourly_rate or 0) or 0)
    branch_id = d.get('branch_id', user.branch_id)
    try:
        branch_id = int(branch_id) if branch_id else None
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid branch'}), 400

    if not admin.is_superadmin:
        branch_id = admin.branch_id
    elif branch_id and not Branch.query.get(branch_id):
        return jsonify({'error': 'Branch not found'}), 404

    user.name = name
    user.role = role
    user.hourly_rate = hourly_rate
    user.branch_id = branch_id
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/users/delete-all', methods=['POST'])
@admin_required
def delete_all_users():
    """Delete all staff except the current admin"""
    admin = User.query.get(session['user_id'])
    if not admin or (normalize_role(admin.role) != 'restaurant' and not admin.is_superadmin):
        return jsonify({'error': 'unauthorized'}), 403

    query = apply_branch_scope(User.query, User.branch_id).filter(User.id != admin.id)
    query.delete()
    db.session.commit()
    
    return jsonify({'ok': True, 'message': 'All staff members deleted'})


# ─── API: Inventory & Recipes ─────────────────────────
@app.route('/api/inventory', methods=['GET'])
@admin_required
def get_inventory():
    tid = get_current_tenant_id()
    items = InventoryItem.query.filter_by(tenant_id=tid).all()
    return jsonify([{
        'id': i.id,
        'name': i.name,
        'unit': i.unit,
        'current_stock': i.current_stock,
        'min_threshold': i.min_threshold,
        'unit_cost': i.unit_cost
    } for i in items])

@app.route('/api/inventory', methods=['POST'])
@admin_required
def add_inventory_item():
    try:
        tid = get_current_tenant_id()
        d = request.json or {}
        
        name = d.get('name', '').strip()
        if not name:
            return jsonify({'error': 'Item name is required'}), 400
            
        item = InventoryItem(
            name=name,
            unit=d.get('unit', 'unit').strip(),
            current_stock=float(d.get('current_stock', 0)),
            min_threshold=float(d.get('min_threshold', 0)),
            unit_cost=float(d.get('unit_cost', 0)),
            tenant_id=tid
        )
        db.session.add(item)
        db.session.flush() # Get item.id before commit
        
        # Log initial stock
        log = InventoryLog(
            inventory_item_id=item.id, 
            action='adjustment', 
            quantity=item.current_stock, 
            note='Initial Stock', 
            tenant_id=tid
        )
        db.session.add(log)
        db.session.commit()
        return jsonify({'ok': True, 'id': item.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/inventory/<int:iid>', methods=['PUT', 'DELETE'])
@admin_required
def manage_inventory_item(iid):
    try:
        tid = get_current_tenant_id()
        item = InventoryItem.query.filter_by(id=iid, tenant_id=tid).first_or_404()
        
        if request.method == 'DELETE':
            # Check for existing recipe logs or dependencies if necessary
            ProductRecipe.query.filter_by(inventory_item_id=iid).delete()
            db.session.delete(item)
            db.session.commit()
            return jsonify({'ok': True})
        
        d = request.json or {}
        item.name = d.get('name', item.name)
        item.unit = d.get('unit', item.unit)
        item.min_threshold = float(d.get('min_threshold', item.min_threshold))
        item.unit_cost = float(d.get('unit_cost', item.unit_cost))
        
        if 'stock_adjustment' in d:
            adj = float(d['stock_adjustment'])
            item.current_stock += adj
            log = InventoryLog(
                inventory_item_id=item.id, 
                action='adjustment', 
                quantity=adj, 
                note=d.get('note', ''), 
                tenant_id=tid
            )
            db.session.add(log)
            
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/recipes', methods=['GET'])
@admin_required
def get_all_recipes():
    tid = get_current_tenant_id()
    recipes = ProductRecipe.query.filter_by(tenant_id=tid).all()
    return jsonify([{
        'id': r.id,
        'product_id': r.product_id,
        'inventory_item_id': r.inventory_item_id,
        'quantity': r.quantity
    } for r in recipes])

@app.route('/api/recipes', methods=['POST'])
@admin_required
def save_product_recipe():
    tid = get_current_tenant_id()
    d = request.json or {}
    pid = d.get('product_id')
    items = d.get('items', []) # List of {inventory_item_id, quantity}
    
    # Delete existing recipe for this product
    ProductRecipe.query.filter_by(product_id=pid, tenant_id=tid).delete()
    
    for it in items:
        r = ProductRecipe(
            product_id=pid,
            inventory_item_id=it['inventory_item_id'],
            quantity=float(it['quantity']),
            tenant_id=tid
        )
        db.session.add(r)
    
    db.session.commit()
    return jsonify({'ok': True})

# ─── API: Cafe Settings ─────────────────────────────────
@app.route('/api/cafe-settings', methods=['GET'])
def get_cafe_settings():
    try:
        tid = get_current_tenant_id()
        if not tid:
            # Fallback for logo/name if not logged in or session lost
            return jsonify({'name': 'POS Cafe', 'logo_b64': ''})
            
        settings = CafeSettings.query.filter_by(tenant_id=tid).first()
        if not settings:
            settings = CafeSettings(tenant_id=tid, name='POS Cafe')
            db.session.add(settings)
            db.session.commit()
        
        return jsonify({
            'name': settings.name,
            'phone': settings.phone,
            'email': settings.email,
            'address': settings.address,
            'logo_b64': settings.logo_b64 or '',
            'open_time': getattr(settings, 'open_time', None),
            'close_time': getattr(settings, 'close_time', None),
            'tax_rate': getattr(settings, 'tax_rate', 0.0),
            'gst_no': getattr(settings, 'gst_no', ''),
            'fssai_no': getattr(settings, 'fssai_no', ''),
            'footer_note': getattr(settings, 'footer_note', ''),
            'loyalty_points_per_100': getattr(settings, 'loyalty_points_per_100', 0),
            'points_redemption_value': getattr(settings, 'points_redemption_value', 0)
        })
    except Exception as e:
        app.logger.error(f"Error in get_cafe_settings: {e}")
        return jsonify({'name': 'POS Cafe', 'logo_b64': ''})

@app.route('/api/cafe-settings', methods=['POST'])
@admin_required
def save_cafe_settings():
    tid = get_current_tenant_id()
    settings = CafeSettings.query.filter_by(tenant_id=tid).first() if tid else None
    if not settings:
        settings = CafeSettings(tenant_id=tid)
    
    d = request.json or {}
    settings.name = (d.get('name') or '').strip() or settings.name
    settings.phone = (d.get('phone') or '').strip()
    settings.email = (d.get('email') or '').strip()
    settings.address = (d.get('address') or '').strip()
    if 'logo_b64' in d:
        settings.logo_b64 = (d.get('logo_b64') or '').strip()
    settings.open_time = (d.get('open_time') or '').strip()
    settings.close_time = (d.get('close_time') or '').strip()
    settings.tax_rate = float(d.get('tax_rate', 5.0))
    settings.gst_no = (d.get('gst_no') or '').strip()
    settings.fssai_no = (d.get('fssai_no') or '').strip()
    settings.footer_note = (d.get('footer_note') or '').strip()
    settings.loyalty_points_per_100 = float(d.get('loyalty_points_per_100', 10.0))
    settings.points_redemption_value = float(d.get('points_redemption_value', 0.5))
    
    db.session.add(settings)
    db.session.commit()
    
    return jsonify({'ok': True, 'message': 'Cafe settings saved successfully'})

@app.route('/api/orders/history', methods=['GET'])
@staff_required
def order_history():
    """Return recent paid orders for the POS order history view."""
    limit = min(int(request.args.get('limit', 50)), 200)
    query = apply_tenant_scope(
        apply_branch_scope(Order.query, Order.branch_id),
        Order
    ).filter(Order.status == 'paid').order_by(Order.created_at.desc()).limit(limit)
    orders = query.all()
    return jsonify([{
        'id': o.id,
        'order_number': o.order_number,
        'table': o.table.number if o.table else 'Takeaway',
        'customer_name': o.customer_name or '',
        'total': o.total,
        'tip': o.tip,
        'payment_method': o.payment_method,
        'items': [{'name': i.product_name, 'qty': i.qty, 'price': i.price} for i in o.items],
        'created_at': utc_iso(o.created_at),
    } for o in orders])

# ─── API: Reviews and Tips ─────────────────────────────────
@app.route('/api/orders/<int:oid>/review', methods=['POST'])
def submit_review(oid):
    o = Order.query.filter_by(id=oid, tenant_id=get_current_tenant_id()).first_or_404()
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
    reviews = (
        Review.query
        .join(Order, Order.id == Review.order_id)
        .filter(Order.branch_id == get_active_branch_id(), Order.tenant_id == get_current_tenant_id())
        .order_by(Review.created_at.desc())
        .all()
    )
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

# ─── Receipt Page ─────────────────────────────────────────
@app.route('/receipt/<int:order_id>')
def receipt_page(order_id):
    o = Order.query.filter_by(id=order_id, tenant_id=get_current_tenant_id()).first_or_404()
    settings = CafeSettings.query.filter_by(tenant_id=get_current_tenant_id()).first()
    return render_template('receipt.html', order=o, cafe_settings=settings)

# ─── CSV Export ────────────────────────────────────────────
import csv
from io import StringIO
from flask import Response

@app.route('/api/export/orders')
@staff_required
def export_orders_csv():
    period = request.args.get('period', 'today')
    now = datetime.utcnow()
    if period == 'week':
        start = now - timedelta(days=7)
    elif period == 'month':
        start = now - timedelta(days=30)
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    orders = apply_branch_scope(Order.query, Order.branch_id).filter(Order.status == 'paid', Order.created_at >= start).order_by(Order.created_at.desc()).all()
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['Date', 'Order #', 'Table', 'Customer', 'Items', 'Subtotal', 'Tip', 'Total', 'Payment Method'])
    for o in orders:
        items_str = '; '.join(f'{i.product_name} x{i.qty}' for i in o.items)
        subtotal = sum(i.qty * i.price for i in o.items)
        writer.writerow([
            o.created_at.strftime('%Y-%m-%d %H:%M'),
            o.order_number,
            o.table.number if o.table else 'Takeaway',
            o.customer_name or '',
            items_str,
            round(subtotal, 2),
            round(o.tip or 0, 2),
            round((o.tip or 0) + subtotal, 2),
            o.payment_method or '',
        ])
    output = si.getvalue()
    return Response(
        output,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment;filename=orders_{period}_{now.strftime("%Y%m%d")}.csv'}
    )

# ─── SocketIO ──────────────────────────────────────────────
@socketio.on('connect')
def on_connect():
    emit('connected', {'status':'ok'})

@socketio.on('call_waiter')
def on_call_waiter(data):
    """Relay call-waiter event to all connected staff."""
    emit('call_waiter', data, broadcast=True)

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
    # Get Default Tenant
    default_tenant = Tenant.query.filter_by(slug='default').first()
    if not default_tenant:
        return  # Can't create payment methods without a tenant
    
    defaults = [
        {'name': 'Cash', 'type': 'cash', 'upi_id': ''},
        {'name': 'Card / Bank', 'type': 'digital', 'upi_id': ''},
        {'name': 'UPI / QR', 'type': 'upi', 'upi_id': 'cafe@ybl'},
        {'name': 'Razorpay', 'type': 'razorpay', 'upi_id': ''},
    ]
    changed = False
    for item in defaults:
        method = PaymentMethod.query.filter_by(type=item['type'], tenant_id=default_tenant.id).first()
        if not method:
            db.session.add(PaymentMethod(name=item['name'], type=item['type'], enabled=True, upi_id=item['upi_id'], tenant_id=default_tenant.id))
            changed = True
    if changed:
        db.session.commit()

def ensure_order_table_schema():
    # Older SQLite databases may not have the newer order columns added in code.
    # Add them in-place so existing data stays intact.
    with db.engine.connect() as conn:
        # Order table additions
        rows = conn.exec_driver_sql('PRAGMA table_info("order")').fetchall()
        columns = {row[1] for row in rows}
        if 'tip' not in columns:
            conn.exec_driver_sql('ALTER TABLE "order" ADD COLUMN tip FLOAT DEFAULT 0')
            conn.commit()
        if 'customer_name' not in columns:
            conn.exec_driver_sql('ALTER TABLE "order" ADD COLUMN customer_name VARCHAR(100) DEFAULT NULL')
            conn.commit()
        if 'branch_id' not in columns:
            conn.exec_driver_sql('ALTER TABLE "order" ADD COLUMN branch_id INTEGER')
            conn.commit()
        # OrderItem notes
        rows2 = conn.exec_driver_sql('PRAGMA table_info("order_item")').fetchall()
        cols2 = {row[1] for row in rows2}
        if 'notes' not in cols2:
            conn.exec_driver_sql('ALTER TABLE "order_item" ADD COLUMN notes TEXT DEFAULT ""')
            conn.commit()
        # Product image_b64
        rows3 = conn.exec_driver_sql('PRAGMA table_info("product")').fetchall()
        cols3 = {row[1] for row in rows3}
        if 'image_b64' not in cols3:
            conn.exec_driver_sql('ALTER TABLE "product" ADD COLUMN image_b64 TEXT DEFAULT ""')
            conn.commit()
        if 'branch_id' not in cols3:
            conn.exec_driver_sql('ALTER TABLE "product" ADD COLUMN branch_id INTEGER')
            conn.commit()
        rows4 = conn.exec_driver_sql('PRAGMA table_info("user")').fetchall()
        cols4 = {row[1] for row in rows4}
        if 'hourly_rate' not in cols4:
            conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN hourly_rate FLOAT DEFAULT 0')
            conn.commit()
        if 'is_superadmin' not in cols4:
            conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN is_superadmin BOOLEAN DEFAULT 0')
            conn.commit()
        if 'branch_id' not in cols4:
            conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN branch_id INTEGER')
            conn.commit()

def ensure_branch_schema():
    default_branch = Branch.query.order_by(Branch.id.asc()).first()
    if not default_branch:
        default_branch = Branch(name='Main Branch', address='Primary outlet')
        db.session.add(default_branch)
        db.session.commit()

    changed = False
    for user in User.query.filter(User.branch_id.is_(None)).all():
        user.branch_id = default_branch.id
        changed = True
    for product in Product.query.filter(Product.branch_id.is_(None)).all():
        product.branch_id = default_branch.id
        changed = True
    for order in Order.query.filter(Order.branch_id.is_(None)).all():
        order.branch_id = order.user.branch_id if order.user and order.user.branch_id else default_branch.id
        changed = True
    for event in AttendanceEvent.query.filter(AttendanceEvent.branch_id.is_(None)).all():
        event.branch_id = event.staff.branch_id if event.staff and event.staff.branch_id else default_branch.id
        changed = True
    if changed:
        db.session.commit()

def ensure_demo_catalog():
    # Get Default Tenant
    default_tenant = Tenant.query.filter_by(slug='default').first()
    if not default_tenant:
        return  # Can't create demo catalog without a tenant
    
    demo_catalog = {
        'Food': [
            ('Margherita Pizza', 350),
            ('Cheese Burger', 240),
            ('Paneer Wrap', 180),
            ('Veg Sandwich', 160),
            ('French Fries', 120),
            ('Chicken Burger', 260),
            ('Pasta Alfredo', 290),
            ('Veg Noodles', 220),
        ],
        'Beverages': [
            ('Espresso', 90),
            ('Cappuccino', 120),
            ('Latte', 140),
            ('Mango Shake', 150),
            ('Lemon Soda', 70),
            ('Iced Tea', 110),
        ],
        'Desserts': [
            ('Chocolate Brownie', 130),
            ('Vanilla Ice Cream', 100),
            ('Cheesecake', 180),
            ('Tiramisu', 220),
        ],
        'Snacks': [
            ('Samosa', 40),
            ('Pakora', 60),
            ('Spring Roll', 90),
            ('Garlic Bread', 110),
        ],
    }

    changed = False
    for category_name, items in demo_catalog.items():
        category = Category.query.filter_by(name=category_name, tenant_id=default_tenant.id).first()
        if not category:
            category = Category(name=category_name, tenant_id=default_tenant.id)
            db.session.add(category)
            db.session.flush()
            changed = True

        for product_name, price in items:
            existing = Product.query.filter_by(name=product_name, category_id=category.id, tenant_id=default_tenant.id).first()
            if not existing:
                db.session.add(Product(name=product_name, price=price, category_id=category.id, tenant_id=default_tenant.id))
                changed = True

    if changed:
        db.session.commit()

def ensure_demo_floors_and_tables():
    # Get Default Tenant
    default_tenant = Tenant.query.filter_by(slug='default').first()
    if not default_tenant:
        return  # Can't create demo tables without a tenant
    
    floor_specs = {
        'Ground Floor': ['1', '2', '3', '4', '5', '6'],
        'First Floor': ['7', '8', '9', '10', '11', '12'],
        'Terrace': ['13', '14', '15', '16'],
    }

    changed = False
    for floor_name, table_numbers in floor_specs.items():
        floor = Floor.query.filter_by(name=floor_name, tenant_id=default_tenant.id).first()
        if not floor:
            floor = Floor(name=floor_name, tenant_id=default_tenant.id)
            db.session.add(floor)
            db.session.flush()
            changed = True

        for number in table_numbers:
            existing = Table.query.filter_by(number=number, floor_id=floor.id, tenant_id=default_tenant.id).first()
            if not existing:
                db.session.add(Table(number=number, seats=4 if int(number) <= 8 else 6, floor_id=floor.id, tenant_id=default_tenant.id))
                changed = True

    if changed:
        db.session.commit()

def ensure_demo_paid_orders_and_reviews():
    target_reviews = 12
    if Review.query.count() >= target_reviews and Order.query.filter_by(status='paid').count() >= target_reviews:
        return

    admin = User.query.filter_by(role='restaurant').first() or User.query.first()
    if not admin:
        return

    demo_session = Session.query.filter_by(user_id=admin.id).order_by(Session.id.asc()).first()
    if not demo_session:
        demo_session = Session(
            user_id=admin.id,
            tenant_id=admin.tenant_id,
            status='closed',
            opened_at=datetime.utcnow() - timedelta(days=14),
            closed_at=datetime.utcnow() - timedelta(days=13),
            closing_amount=0,
        )
        db.session.add(demo_session)
        db.session.flush()

    product_lookup = {p.name: p for p in apply_tenant_scope(Product.query, Product).all()}
    table_lookup = {t.number: t for t in apply_tenant_scope(Table.query, Table).all()}
    now = datetime.utcnow()
    demo_orders = [
        {
            'table': '1',
            'method': 'cash',
            'tip': 0,
            'rating': 5,
            'comment': 'Fast service and hot food.',
            'items': [('Espresso', 2), ('Chocolate Brownie', 1)],
        },
        {
            'table': '2',
            'method': 'upi',
            'tip': 10,
            'rating': 4,
            'comment': 'Good taste and quick billing.',
            'items': [('Margherita Pizza', 1), ('Lemon Soda', 2)],
        },
        {
            'table': '3',
            'method': 'digital',
            'tip': 0,
            'rating': 5,
            'comment': 'Friendly staff and fresh food.',
            'items': [('Paneer Wrap', 2), ('Iced Tea', 1)],
        },
        {
            'table': '4',
            'method': 'cash',
            'tip': 15,
            'rating': 3,
            'comment': 'Portion was fine, service could be faster.',
            'items': [('Cheese Burger', 1), ('French Fries', 1), ('Cappuccino', 1)],
        },
        {
            'table': '5',
            'method': 'upi',
            'tip': 5,
            'rating': 5,
            'comment': 'Loved the desserts.',
            'items': [('Cheesecake', 1), ('Vanilla Ice Cream', 2)],
        },
        {
            'table': '6',
            'method': 'digital',
            'tip': 0,
            'rating': 4,
            'comment': 'Clean table and quick checkout.',
            'items': [('Veg Sandwich', 2), ('Mango Shake', 2)],
        },
        {
            'table': '7',
            'method': 'cash',
            'tip': 0,
            'rating': 4,
            'comment': 'Nice ambience.',
            'items': [('Pasta Alfredo', 1), ('Espresso', 1)],
        },
        {
            'table': '8',
            'method': 'upi',
            'tip': 10,
            'rating': 5,
            'comment': 'Best burger in the area.',
            'items': [('Chicken Burger', 2), ('Lemon Soda', 2)],
        },
        {
            'table': '9',
            'method': 'digital',
            'tip': 0,
            'rating': 4,
            'comment': 'Great value for money.',
            'items': [('Veg Noodles', 2), ('Garlic Bread', 1)],
        },
        {
            'table': '10',
            'method': 'cash',
            'tip': 0,
            'rating': 5,
            'comment': 'Desserts were excellent.',
            'items': [('Tiramisu', 1), ('Cappuccino', 2)],
        },
        {
            'table': '11',
            'method': 'upi',
            'tip': 5,
            'rating': 4,
            'comment': 'Smooth ordering experience.',
            'items': [('Spring Roll', 3), ('Iced Tea', 1)],
        },
        {
            'table': '12',
            'method': 'digital',
            'tip': 0,
            'rating': 5,
            'comment': 'Will come again.',
            'items': [('Pakora', 2), ('Mango Shake', 2)],
        },
    ]

    existing_paid = Order.query.filter_by(status='paid').count()
    needed = max(0, target_reviews - existing_paid)
    if needed <= 0:
        return

    max_order_num = Order.query.count()
    created = 0
    for spec in demo_orders:
        if created >= needed:
            break
        table = table_lookup.get(spec['table'])
        items = []
        total = 0
        for product_name, qty in spec['items']:
            product = product_lookup.get(product_name)
            if not product:
                continue
            items.append((product, qty))
            total += float(product.price) * qty

        if not items:
          continue

        max_order_num += 1
        order = Order(
            order_number=f'ORD-{max_order_num:04d}',
            table_id=table.id if table else None,
            session_id=demo_session.id,
            user_id=admin.id,
            branch_id=admin.branch_id,
            status='paid',
            payment_method=spec['method'],
            total=total,
            tip=spec['tip'],
            created_at=now - timedelta(days=created + 1),
            sent_to_kitchen_at=now - timedelta(days=created + 1, minutes=15),
            completed_at=now - timedelta(days=created + 1, minutes=5),
        )
        db.session.add(order)
        db.session.flush()

        for product, qty in items:
            db.session.add(OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                qty=qty,
                price=product.price,
                kitchen_status='completed',
                started_at=now - timedelta(days=created + 1, minutes=12),
                completed_at=now - timedelta(days=created + 1, minutes=5),
            ))

        db.session.add(Review(
            order_id=order.id,
            rating=spec['rating'],
            comment=spec['comment'],
            created_at=now - timedelta(days=created + 1),
        ))
        created += 1

    if created:
        db.session.commit()

def ensure_default_accounts():
    """Create default user accounts. No session dependency."""
    # Get or create Default Tenant (not dependent on session)
    default_tenant = Tenant.query.filter_by(slug='default').first()
    if not default_tenant:
        default_tenant = Tenant(name='Default Tenant', slug='default')
        db.session.add(default_tenant)
        db.session.flush()
    
    # Get or create default branch for this tenant
    default_branch = Branch.query.filter_by(tenant_id=default_tenant.id).first()
    if not default_branch:
        default_branch = Branch(
            name='Main Branch',
            tenant_id=default_tenant.id,
            address=''
        )
        db.session.add(default_branch)
        db.session.flush()
    
    admin_email = 'admin@cafe.com'
    admin = User.query.filter_by(email=admin_email).first()
    if not admin:
        admin = User(
            name='Admin',
            email=admin_email,
            password=generate_password_hash('password'),
            role='restaurant',
            branch_id=default_branch.id,
            tenant_id=default_tenant.id,
            is_superadmin=True,
            hourly_rate=0,
        )
        db.session.add(admin)
    else:
        admin.role = 'restaurant'
        admin.branch_id = default_branch.id
        admin.tenant_id = default_tenant.id
        admin.is_superadmin = True

    customer_email = 'customer@cafe.com'
    customer = User.query.filter_by(email=customer_email).first()
    if not customer:
        customer = User(
            name='Customer',
            email=customer_email,
            password=generate_password_hash('Customer@1234', method='scrypt'),
            role='customer',
            branch_id=default_branch.id,
            tenant_id=default_tenant.id,
        )
        db.session.add(customer)
    else:
        customer.name = 'Customer'
        customer.role = 'customer'
        customer.branch_id = default_branch.id
        customer.tenant_id = default_tenant.id
    db.session.commit()

with app.app_context():
    db.create_all()
    seed_data()
    ensure_payment_methods()
    ensure_order_table_schema()
    ensure_branch_schema()
    ensure_default_accounts()
    ensure_branch_schema()
    ensure_demo_catalog()
    ensure_demo_floors_and_tables()
    # ensure_demo_paid_orders_and_reviews() - Commented out: depends on request context, call from endpoint instead

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    socketio.run(app, host='0.0.0.0', port=port, debug=debug, allow_unsafe_werkzeug=True)
