# POS CAFE - SYSTEM BRIEF & DEVELOPMENT PROMPT

## Quick System Overview

**POS Cafe** is a full-stack Point of Sale and Restaurant Management System built with Flask + SQLAlchemy + SocketIO. It supports 5 user roles (Customer, Cashier, Kitchen, Manager, Owner) with real-time order management, multi-branch support, payment integration (Razorpay), and analytics dashboard.

---

## 🚀 COMPLETE USER FLOW PROMPT

### *Use this when onboarding developers, creating feature specs, or documenting requirements:*

---

### **PHASE 1: Public Landing Page**
**Route:** `/` (Landing)
**User:** Anonymous/New visitors
**Features:**
- Marketing hero section
- Feature highlights (15+ benefits)
- Call-to-action "Get Started" button
- No login required

---

### **PHASE 2: Authentication System**
**Route:** `/auth` (Authentication Hub)
**User:** All users
**Available Actions:**

1. **SIGN UP (New Account)**
   - Fields: Name, Email, Password (strong validation), Role (Cashier/Kitchen/Manager/Owner), Hourly Rate (optional)
   - Validates: Email uniqueness, password strength
   - On Success: Creates user, auto-login, redirect to role homepage
   - Response: User name, role, redirect URL

2. **LOGIN (Existing Account)**
   - Fields: Email, Password
   - Validates: Credentials against database
   - On Success: Create session, redirect to role homepage
   - Role Mapping:
     - Role "customer" → `/customer`
     - Role "cashier/kitchen/manager" → `/pos` or `/kitchen`
     - Role "restaurant" → `/dashboard`
   - Response: User details, role, active branch

3. **PASSWORD RESET**
   - Request: User enters email
   - System: Generates reset code, sends via email (SMTP or Resend API)
   - Complete: User validates code, sets new password
   - Workflow: Request → Email sent → Code validated → Password updated

---

## **ROLE 1: CUSTOMER** (Self-Service Ordering)
**Entry:** QR code scan → `/table/<table_id>/order`
**Features:**

1. **View Menu**
   - All products organized by category
   - Display: Item name, price, description, image, tax info
   - Responsive grid layout (mobile-optimized)
   - Search/filter by category

2. **Build Order**
   - Add items with quantity selectors
   - View running subtotal + tax calculation
   - Modify quantities before submit
   - Add special instructions/notes
   - Multiple items support

3. **Place Order**
   - Submit order with table ID
   - Order saved to database
   - Visible to: POS system + Kitchen queue
   - Customer gets: Order ID + confirmation

4. **Track Status (Real-time)**
   - Order status states: Pending → In Kitchen → Ready → Served
   - Real-time updates via SocketIO
   - Visual indicators/colors
   - Notification when ready

5. **View Receipt**
   - Itemized breakdown
   - Tax calculation
   - Total amount
   - Timestamp
   - (Optional) Print or digital

---

## **ROLE 2: CASHIER/STAFF** (POS & Table Management)
**Entry:** Login → `/pos`
**Features:**

### **A) Table Management (Dashboard)**
- Visual table grid/list view
- Table statuses (color-coded):
  - ⚪ Empty (Available)
  - 🔵 Occupied (Has open order)
  - 🟢 Ready for payment (Closed order)
  - 🟡 Pending (Order in kitchen)
- Click table → Open order management

### **B) Order Operations**

**Create Order:**
- Click table → New order form
- Browse products by category
- Add items (quantity adjustment)
- Add special notes
- Save to table

**Modify Order:**
- Add items to existing order
- Change quantities
- Remove items
- View real-time subtotal with tax

**Send to Kitchen:**
- Mark items for kitchen
- Auto-notification to kitchen display
- Kitchen sees order instantly
- Status tracking

**View Kitchen Status:**
- See which orders are in kitchen
- See estimated prep time
- Priority ordering available

### **C) Payment Processing**

**Initiate Payment:** Click "Pay" button on order

**Payment Methods:**
1. **Cash**
   - Amount received (manual entry)
   - Change calculation
   - Complete immediately

2. **UPI**
   - Customer scans UPI QR
   - Direct transfer
   - Real-time confirmation
   - Auto-mark as paid

3. **Card (Razorpay)**
   - Generate Razorpay order ID
   - Customer scans payment QR
   - Poll payment status (real-time)
   - Auto-complete on success
   - Handle decline/timeout

**Receipt Generation:**
- Itemized bill with quantities
- Tax breakdown
- Subtotal + Total
- Payment method shown
- Print or digital format
- Email option

### **D) Real-Time Features**
- Live order status updates from kitchen
- Stock availability alerts
- See other staff activity
- SocketIO updates (no page refresh needed)

---

## **ROLE 3: KITCHEN STAFF** (Order Preparation)
**Entry:** Login → `/kitchen`
**Features:**

### **Kitchen Display System (KDS)**

**Order Queue:**
- Display all incoming orders
- Sorted by: Time received (FIFO)
- Color-coded by status

**Order Details Card:**
- Table number
- All items to prepare
- Quantities per item
- Special instructions/notes
- Time elapsed since order
- Timer showing wait time

**Status Management:**
- **Pending** (New) → Click "Start Cooking"
- **In Progress** → Mark items as completed
- **Ready** → Mark order complete
- **Served** → Remove from queue

**Features:**
- Audio alerts on new orders
- Print order tickets
- Filter: Show pending only / Show all
- Item checkboxes per item
- Auto-sound notification settings
- Batch ready (multiple orders)
- Reject/request clarification

**Real-Time Sync:**
- Instant updates when new orders arrive
- Updates visible to all kitchen screens
- Cashier sees kitchen status on POS
- No manual refresh needed

---

## **ROLE 4: MANAGER** (Oversight & Coordination)
**Entry:** Login → `/pos`
**Features:**
- Full Cashier access (POS, tables, payments)
- Order history review
- Staff activity monitoring
- Basic inventory checks
- (May have additional reporting)

---

## **ROLE 5: OWNER/ADMIN** (Full Analytics & Management)
**Entry:** Login → `/dashboard`

### **TAB 1: Analytics (Reports & Business Intelligence)**

**Period Selection:** Today / Week / Month

**Key Metrics:**
- 💰 **Total Sales** (sum of completed paid orders)
- 📦 **Total Orders** (count of completed orders)
- 📈 **Avg Order Value** (total sales / total orders)

**Data Visualizations:**
1. **Payment Methods Pie Chart**
   - Cash: percentage & amount
   - UPI: percentage & amount
   - Card: percentage & amount

2. **Top 5 Products Bar Chart**
   - Product name
   - Quantity sold
   - Revenue per product

3. **Payment Breakdown Cards**
   - Cash: Total transactions + count + amount
   - UPI: Total transactions + count + amount
   - Card: Total transactions + count + amount

4. **Customer Reviews Section**
   - Display latest customer feedback
   - Show order context
   - Star ratings / sentiment
   - Auto-refresh / Manual reload
   - Empty state if no reviews

**Export:**
- CSV download button
- Includes all: Sales, orders, products, payments
- Timestamped filename

---

### **TAB 2: Staff Management (Team)**

**Staff List Section:**
- Table view: Name | Email | Role | Branch | Actions

**Add Staff Button:**
- Modal form with:
  - Full Name (text)
  - Email (email input, validated)
  - Password (text, required for new staff)
  - Role dropdown (Cashier, Kitchen, Manager, Owner)
  - Hourly Rate (number, for payroll)
  - Branch (dropdown, if multi-branch)
  - Save button

**Edit Staff:**
- Click on staff member
- Pre-fill modal with current data
- Update any field
- Save changes
- Re-confirm password if changed

**Delete Staff:**
- Remove from system
- Confirm action

**Staff Visibility:**
- Only staff in same branch (unless superadmin)
- All staff shows for owner

---

### **TAB 3: Attendance (Payroll)**

**Attendance Table:**
- Columns: Staff Name | Date | Clock In | Clock Out | Hours | Pay | Actions

**Data:**
- Real-time updates
- Clock in/out times
- Calculated hours worked
- Hourly rate × hours = Pay
- Link to daily attendance

**Manual Adjustments:**
- Edit clock in/out times (for corrections)
- Recalculate hours automatically
- Manual notes/reasons

**Features:**
- View by date range
- Filter by staff member
- Export to CSV for payroll
- Monthly summary view

---

### **TAB 4: Branches (Multi-Location)**

**Available if:** System has multiple branches configured

**Compare Tools:**
- Date range selection (start/end)
- Select branches to compare
- Compare button

**Branch Card Display** (for each):
- Branch Name
- Total Sales (for selected period)
- Total Orders (for period)
- Avg Order Value
- Top Products (for branch)
- Payment breakdown
- Revenue by product

**Use Cases:**
- Compare locations performance
- Identify top/bottom performers
- Seasonal trends
- Staff training by location

---

### **TAB 5: Settings (Configuration)**

**Left Panel: Settings Form**

**Cafe Information:**
- Cafe Name (text field)
- Phone Number (tel field with whatsapp icon)
- Email Address (email field)
- Full Address (textarea)

**Logo Management:**
- Current logo preview (60x60px)
- Upload button (PNG/JPG, max 500KB)
- Remove button
- File size validator
- Image preview on select

**Operating Hours:**
- Open Time (time picker)
- Close Time (time picker)
- Display format in 24hr

**Taxation:**
- Default Tax Rate (%) input
- Number field with decimal support (e.g., 5.5%)
- Applied to all orders by default

**Right Panel: Actions**
- Save Changes button (primary action)
- Success notification
- Error handling
- Persists to database
- Updates reflected: Landing page, receipts, settings everywhere

---

## **BACKGROUND PAGE: Backend Config** (`/backend`)
**Access:** Owner only
**Features:**
- System configuration
- Database management (advanced)
- API settings
- Integration configuration
- System health/diagnostics
- (Advanced features)

---

# 🔐 Authentication & Security
- **Sessions:** Flask session-based (user_id, user_role, tenant_id, active_branch_id)
- **Password Hashing:** Scrypt algorithm
- **Role Validation:** Every route checks role before rendering
- **Email Verification:** (Optional, for password reset)
- **CORS:** Enabled for API access
- **CSRF:** Base template includes CSRF token

---

# 🔗 Key Data Relationships
```
Tenant (1) ──→ (Many) User
Tenant (1) ──→ (Many) Branch
Branch (1) ──→ (Many) User (staff)
Branch (1) ──→ (Many) Table
Branch (1) ──→ (Many) Product
Category (1) ──→ (Many) Product
Order (1) ──→ (Many) OrderItem
OrderItem → ProductUser (staff) ──→ Clock In/Out Events
```

---

# 🛠️ Tech Stack
- **Backend:** Flask (Python)
- **Database:** SQLite with SQLAlchemy ORM
- **Real-Time:** SocketIO (WebSocket)
- **Frontend:** HTML/CSS/JavaScript (Tailwind CSS)
- **Payments:** Razorpay API
- **Email:** SMTP or Resend API
- **QR Codes:** Python qrcode library
- **Charts:** Chart.js

---

# 📱 Responsive Behavior
- **Desktop (≥1024px):** Sidebar nav + full content
- **Tablet (768px-1024px):** Responsive grid, side nav hidden
- **Mobile (<768px):** Full-width, bottom navigation bar, touch-optimized buttons (min 44px)
- **Safe Area Support:** iOS notch/home indicator aware

---

# 🎯 Testing Scenarios

## Happy Path - Customer Order
1. Customer scans QR → Lands on menu
2. Adds items → Places order
3. Kitchen receives → Prepares
4. Cashier processes payment → Receipt generated
5. Order marked complete

## Happy Path - Staff POS
1. Staff login → See tables
2. Click table → Create order
3. Add items → Send to kitchen
4. Kitchen marks ready
5. Process payment → Receipt

## Happy Path - Owner Analytics
1. Owner login → Dashboard
2. View today's sales metrics
3. Check top products
4. Review payment breakdown
5. Export CSV for records

---

# ⚠️ Error Handling
- Invalid credentials → Show error message
- Strong password required → Validation feedback
- Email already exists → Prevent duplicate signups
- Payment failures → Retry options
- Network errors → Graceful fallback
- Missing data → Form validation before submit

---

# 📊 Sample Database Structure

```sql
-- Users
CREATE TABLE user (
  id INTEGER PRIMARY KEY,
  name TEXT,
  email TEXT UNIQUE,
  password TEXT,
  role TEXT (customer|cashier|kitchen|manager|restaurant),
  hourly_rate FLOAT,
  branch_id INTEGER FK,
  tenant_id INTEGER FK,
  is_superadmin BOOLEAN
);

-- Orders
CREATE TABLE order (
  id INTEGER PRIMARY KEY,
  table_id INTEGER FK,
  status TEXT (pending|in_kitchen|ready|served|cancelled),
  subtotal FLOAT,
  tax FLOAT,
  total FLOAT,
  payment_method TEXT,
  created_at DATETIME,
  tenant_id INTEGER FK
);

-- Order Items
CREATE TABLE order_item (
  id INTEGER PRIMARY KEY,
  order_id INTEGER FK,
  product_id INTEGER FK,
  quantity INTEGER,
  unit_price FLOAT
);

-- Products
CREATE TABLE product (
  id INTEGER PRIMARY KEY,
  name TEXT,
  price FLOAT,
  category_id INTEGER FK,
  tax FLOAT,
  active BOOLEAN,
  image_b64 TEXT,
  branch_id INTEGER FK,
  tenant_id INTEGER FK
);

-- Attendance
CREATE TABLE clock_in_event (
  id INTEGER PRIMARY KEY,
  user_id INTEGER FK,
  clock_in_time DATETIME,
  clock_out_time DATETIME,
  date DATE,
  hourly_rate FLOAT,
  hours_worked FLOAT
);
```

---

# 🚀 Common Development Tasks

**Adding a new feature:**
1. Update database models (models.py or app.py)
2. Add API route (@app.route)
3. Create/update template (HTML)
4. Add client-side JavaScript if needed
5. Add role checks if restricted
6. Test across device sizes

**Adding new user role:**
1. Add role to signup/login role list
2. Create role_home() redirect mapping
3. Create new page template
4. Add @page_login_required(allowed_roles=(...)) decorator
5. Implement features for that role

**Adding product feature:**
1. Add field to Product model
2. Update product API endpoints (GET/POST/PUT)
3. Update product form in UI
4. Update product display (POS or menu)
5. Store/retrieve from database

---

# 🎓 Quick Commands

```bash
# Run application
python app.py

# Database migration (if needed)
python migrate.py

# Test email sending
# (Check app.py email functions)

# View logs
# Check Flask console output
```

---

**Version:** 1.0 | **Last Updated:** April 2026 | **Status:** Production-Ready

---

## 📋 Use This Prompt When:
- ✅ Onboarding new developers
- ✅ Creating feature specifications  
- ✅ Documenting requirements for stakeholders
- ✅ Planning sprints or milestones
- ✅ Writing test cases/QA scenarios
- ✅ Creating API documentation
- ✅ Planning database changes
- ✅ Designing UI mockups
- ✅ Briefing clients on functionality
