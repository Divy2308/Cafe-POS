# POS Cafe - Complete User Flow & Features Documentation

## 📍 Overview
POS Cafe is a multi-role Point of Sale system designed for cafes/restaurants. It supports multiple user types with different access levels and features.

---

## 🌍 User Types & Roles

1. **Customer** - Self-ordering via QR code
2. **Cashier/Staff** - POS system, table management, payments
3. **Kitchen Staff** - Order preparation and management
4. **Manager** - Staff oversight, inventory basics
5. **Owner/Admin/Restaurant** - Full dashboard, settings, analytics, staff management

---

# 🔄 COMPLETE APPLICATION FLOW

## Phase 1: Landing Page (`/`)
**When:** New user arrives at the application
**What they see:**
- Hero section with POS Cafe branding
- Feature highlights (15+ sections describing cafe benefits)
- Call-to-action buttons: "Get Started" (launches auth modal)
- Service highlights (payment processing, inventory, analytics, etc.)

---

## Phase 2: Authentication Page (`/auth`)
**When:** User clicks "Get Started" or visits `/auth`
**Available Actions:**
1. **Sign Up (New User)**
   - Role selection: Cashier, Kitchen Staff, Manager, Owner
   - Name, Email, Password (strong password validation)
   - Optional: Hourly Rate (for staff)
   - Creates new account → Auto logsin → Redirects to role home

2. **Login (Existing User)**
   - Email + Password
   - On success → System checks role → Redirects to appropriate page

3. **Password Reset**
   - Request: User enters email
   - System sends reset code (via SMTP or Resend email service)
   - User validates code + creates new password

---

# 👥 ROLE-BASED FLOWS

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 1️⃣ CUSTOMER FLOW (Self-Ordering via QR)
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### Entry Point: QR Code → `/table/<table_id>/order`

**Step 1: Scan QR Code or Direct Link**
- Customer scans QR code at table
- Gets redirected to self-order page with table ID

**Step 2: View Menu** (`/customer` or `/table/<id>/order`)
- See all products organized by categories
- View prices, descriptions, images
- See tax info

**Step 3: Build Order**
- Add items to cart
- Adjust quantities
- See real-time total with tax calculation
- Special instructions/notes (optional)

**Step 4: Place Order**
- Submit order with table number
- Order goes to kitchen + POS system
- Get order confirmation with order ID

**Step 5: Track Status** 
- Real-time order status updates
- See: Pending → In Kitchen → Ready for Pickup
- Get notified when order is ready

**Step 6: View Receipt** (Optional)
- Digital receipt with item breakdown
- Tax + total
- Order timestamp

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 2️⃣ CASHIER/STAFF FLOOR FLOW
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### Entry Point: Login → `/pos`

**Dashboard - Table View**
- Visual representation of all restaurant tables
- Color-coded status:
  - ⚪ Empty/Available
  - 🔵 Occupied/Has Order
  - 🟢 Ready for Payment
  - 🟡 Pending Order

### Features Available:

#### A) Take Order
1. **Click on table** → Opens order creation
2. **Add items:**
   - Browse products by category
   - Set quantities
   - Add special instructions
   - Multi-items support
3. **Save to table** → Order appears in table status
4. **Send to Kitchen** → Notifies kitchen staff

#### B) Manage Orders
- View all open orders on current table
- Add items to existing order
- Modify quantities
- Delete/remove items
- View order subtotal with tax

#### C) Process Payment
1. **Click "Pay"** on table with completed order
2. **Payment Method Selection:**
   - Cash
   - UPI (mobile payment)
   - Card (Razorpay integration)
3. **For Card Payment:**
   - System generates Razorpay order
   - Customer scans payment QR
   - Real-time payment status check
   - Auto-confirmation on success
4. **Generate Receipt:**
   - Itemized bill
   - Tax breakdown
   - Payment method shown
   - Print or digital

#### D) Real-Time Updates
- Live kitchen order status
- Stock availability
- Other staff activities (SocketIO real-time sync)

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 3️⃣ KITCHEN STAFF FLOW
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### Entry Point: Login → `/kitchen`

**Kitchen Display System (KDS)**

#### Display View:
- Show all incoming orders in queue
- Order details:
  - Table number
  - Items to prepare (with quantities)
  - Special instructions/notes
  - Time order was placed
  - Preparation time elapsed

#### Order Status Management:
1. **Pending** - Just received from server
2. **In Progress** - Mark "Start Cooking"
3. **Ready** - Mark "Ready" when plated
4. **Served** - Order complete (removed from queue)

#### Features:
- **Audio Alerts** - New order notification sounds
- **Filter View** - View pending vs. in-progress orders
- **Item Checkboxes** - Track which items are done per order
- **Timer** - Shows how long order has been waiting
- **Print Order Ticket** - For reference

#### Real-Time Sync:
- Updates instantly when new orders come
- Syncs with all kitchen screens
- Cashier can see kitchen status on POS

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 4️⃣ MANAGER FLOW
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### Entry Point: Login → `/pos` (Can access some staff features)

**Features:**
- Access all Cashier features (POS, Table Management, Payments)
- Review orders and sales

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 5️⃣ OWNER/ADMIN/RESTAURANT FLOW
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### Entry Point: Login → `/dashboard`

**Main Dashboard - 5 Major Tabs:**

### TAB 1: 📊 ANALYTICS (Reports & Insights)
**View By Period:** Today / Week / Month

**Key Metrics Displayed:**
- 💰 **Total Sales** (paid orders only)
- 📦 **Total Orders** (completed)
- 📈 **Avg. Order Value** (per transaction)

**Charts & Breakdowns:**
- **Payment Methods Pie Chart** 
  - Cash, UPI, Card distribution
  - Visual breakdown by method
- **Top Products Bar Chart**
  - Most ordered items
  - Quantities sold
- **Payment Breakdown** (Detailed)
  - Cash transactions
  - UPI transactions
  - Card transactions
  - Individual amounts + counts
- **Customer Reviews Section**
  - Latest feedback from orders
  - Star ratings
  - Auto-loads/reload button
  - Empty state message

**Export Feature:**
- CSV export of all analytics data
- Download button with icon

### TAB 2: 👥 STAFF MANAGEMENT
**Left Side Panel: Staff List**
- Name, Email, Role, Branch

**Actions Available:**
- **+ Add Staff** button
  - Modal form:
    - Full Name
    - Email
    - Password (required for new)
    - Role (Cashier, Kitchen, Manager, Admin)
    - Hourly Rate (for payroll)
    - Branch (if multi-branch)
  - Auto-saves to database
  
- **Edit Staff**
  - Click on staff member
  - Same modal opens with pre-filled data
  - Update any field
  - Save changes
  
- **Delete Staff**
  - Remove from system

**Staff Details:**
- List view with Name, Email, Role columns
- Sortable/filterable
- Real-time updates

### TAB 3: ⏱️ ATTENDANCE TRACKING
**Table View:**
- Staff Name
- Date
- Clock In Time
- Clock Out Time
- Total Hours Worked
- Calculated Pay
- Manual Edit Option (for corrections)

**Features:**
- Real-time attendance data
- Hourly rate × hours = Pay calculation
- Can manually adjust times if punch errors
- Export attendance for payroll

### TAB 4: 🏢 BRANCHES/COMPARE (Multi-location Management)
**Available if Multi-branch Setup:**

**Date Range Selection:**
- Start Date picker
- End Date picker
- Compare button

**Branch Comparison Card View:**
- Each branch shows:
  - Branch Name
  - Total Sales (for range)
  - Total Orders
  - Top Products
  - Payment breakdown
  - Avg Order Value

**Use Case:** Compare performance across locations

### TAB 5: ⚙️ CAFE SETTINGS
**Left: Settings Form**
- **Logo Upload**
  - Preview current logo (or ☕ default)
  - Upload PNG/JPG (max 500KB)
  - Remove button
  
- **Cafe Information:**
  - Cafe Name
  - Phone Number
  - Email Address
  - Address (full)
  
- **Operating Hours:**
  - Open Time (time picker)
  - Close Time (time picker)
  
- **Tax Configuration:**
  - Default Tax Rate (%)

**Right: Actions Panel**
- Save Changes button
- Persists to database
- Updates immediately across system

---

## 🔗 BACKEND CONFIGURATION PAGE (`/backend`)

**Access:** Owner only

**Features:**
- Advanced system configuration
- Database management (if enabled)
- API settings
- Integrations setup
- System diagnostics

---

# 🎯 KEY FEATURES SUMMARY

## 1. Authentication & Security
- Multi-role login system
- Password reset via email (SMTP or Resend)
- Session management
- Secure password hashing (scrypt)
- Email validation

## 2. Point of Sale (POS)
- Table-based ordering
- Real-time order management
- Multiple payment methods:
  - Cash
  - UPI integration
  - Card (Razorpay)
- Receipt generation & printing
- Order history

## 3. Kitchen Management
- Real-time order queue
- Status tracking (Pending → In Progress → Ready)
- Audio/visual alerts
- Order tickets
- Multi-kitchen support

## 4. Customer Self-Service
- QR-code based ordering
- Real-time order status tracking
- Digital menu browsing
- Order placement & confirmation

## 5. Staff & Attendance
- Add/Edit/Delete staff members
- Role-based access control
- Hourly rate tracking
- Clock In/Clock Out
- Automatic payroll calculation
- Attendance reports

## 6. Analytics & Reporting
- Sales metrics (by period)
- Payment method breakdown
- Top products analysis
- Customer reviews
- Export to CSV
- Multi-branch comparison

## 7. Settings Management
- Logo upload
- Cafe information management
- Operating hours configuration
- Tax rate settings
- Email/communication setup

## 8. Multi-Branch Support (if enabled)
- Branch-specific data isolation
- Cross-branch analytics
- Branch selection for operations
- Branch staff management

---

# 📱 DEVICE SUPPORT

- **Desktop:** Full dashboard, analytics, settings
- **Tablet:** Table management, kitchen display (optimized)
- **Mobile:** POS reduced view, customer ordering, staff clock-in
- **Responsive Design:** All views adapt to screen size
- **Touch Optimized:** Min 44px tap targets, gestures supported

---

# 🔐 Role-Based Access Control

| Feature | Customer | Cashier | Kitchen | Manager | Owner |
|---------|----------|---------|---------|---------|-------|
| Self-Order | ✅ | ❌ | ❌ | ❌ | ❌ |
| POS/Tables | ❌ | ✅ | ❌ | ✅ | ✅ |
| Payments | ❌ | ✅ | ❌ | ✅ | ✅ |
| Kitchen View | ❌ | ❌ | ✅ | ❌ | ✅ |
| Analytics | ❌ | ❌ | ❌ | ❌ | ✅ |
| Staff Management | ❌ | ❌ | ❌ | ❌ | ✅ |
| Attendance | ❌ | ❌ | ❌ | ❌ | ✅ |
| Settings | ❌ | ❌ | ❌ | ❌ | ✅ |

---

# 🔄 Data Flow

```
Customer QR Scan
    ↓
Self-Order Page (/table/id/order)
    ↓
Place Order (POST /api/self-order)
    ↓
→ Kitchen Queue (/kitchen display)
→ POS System (Table status update)
→ Order in DB
    ↓
Kitchen Marks Ready
    ↓
Cashier Processes Payment
    ↓
Receipt Generated
    ↓
Order Completed
```

```
Staff Login
    ↓
Role Check
    ├→ Chef: /kitchen
    ├→ Cashier: /pos
    ├→ Owner: /dashboard
    └→ Customer: /customer
    ↓
Role-Specific Features
    ↓
Real-Time Updates via SocketIO
```

---

# 📋 API ENDPOINTS OVERVIEW

## Authentication
- `POST /api/signup` - Register new user
- `POST /api/login` - User login
- `POST /api/logout` - User logout
- `POST /api/password-reset/request` - Request password reset
- `POST /api/password-reset/complete` - Complete reset

## Orders
- `POST /api/orders` - Create order
- `GET /api/orders/all` - Get all orders
- `GET /api/orders/table/<id>` - Get table orders
- `POST /api/orders/<id>/pay` - Process payment
- `POST /api/orders/<id>/send-kitchen` - Send to kitchen
- `DELETE /api/orders/<id>` - Delete order

## Products
- `GET /api/products` - Get menu items
- `POST /api/products` - Add product
- `PUT /api/products/<id>` - Update product
- `DELETE /api/products/<id>` - Delete product

## Kitchen
- `GET /api/kitchen/orders` - Get pending kitchen orders
- `POST /api/orders/<id>/send-kitchen` - Send order to kitchen

## Staff
- `POST /api/admin/staff` - Add staff member
- `PUT /api/admin/staff/<id>` - Update staff
- `DELETE /api/admin/staff/<id>` - Remove staff

## Attendance
- `POST /api/attendance/clock` - Clock in/out
- `GET /api/admin/attendance-report` - Attendance history

## Payments
- `POST /api/razorpay/order` - Create Razorpay order
- `GET /api/orders/<id>/payment-status` - Check payment status

## Settings
- `GET /api/cafe-settings` - Get cafe info
- `PUT /api/cafe-settings` - Update cafe settings

---

# ✨ Notable Features

1. **Real-Time Sync** - Uses SocketIO for live updates
2. **Multi-Tenant Ready** - Cafe data isolation
3. **Payment Integration** - Razorpay (cards), UPI, Cash
4. **Email Notifications** - SMTP or Resend integration
5. **Responsive Design** - Mobile, tablet, desktop
6. **Dark Theme** - Eye-friendly interface
7. **Batch Operations** - Process multiple orders
8. **Export Capability** - CSV data export
9. **Touch Optimized** - 44px minimum tap targets
10. **QR Code Generation** - For table orders

---

**Document Version:** 1.0 | **Last Updated:** April 2026
