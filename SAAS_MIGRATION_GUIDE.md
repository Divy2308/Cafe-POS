# Multi-Tenant SaaS Migration Guide

## ✅ What Has Been Completed

### 1. Database Models Updated
- Added `Tenant` model with:
  - `id` (primary key)
  - `name` (tenant name)
  - `slug` (URL-friendly identifier)
  - `logo_b64` (base64 logo)
  - `plan` (subscription plan)
  - `is_active` (activation status)
  - `owner_id` (tenant owner reference)
  - `created_at` (timestamp)

- Added `tenant_id` foreign key to:
  - `Branch`
  - `User`
  - `Category`
  - `Product`
  - `Floor`
  - `Table`
  - `PaymentMethod`
  - `CafeSettings`
  - `Session`
  - `Order`
  - `KitchenTicket`
  - `Reservation`
  - `PushSubscription`
  - `AttendanceEvent`

### 2. Helper Functions Added
- `get_current_tenant_id()` - Retrieves tenant_id from session
- `get_current_tenant()` - Gets the Tenant object
- `apply_tenant_scope(query, model_class)` - Filters queries by current tenant
- `make_slug(name)` - Converts names to URL-friendly slugs
- `is_platform_admin` field added to User model

### 3. Auth System Updated
- `POST /api/signup` - Stores `tenant_id` in session
- `POST /api/login` - Stores `tenant_id` in session after auth
- `POST /api/quick-login` - Stores `tenant_id` in session for dev access
- `POST /api/register-restaurant` - New endpoint for SaaS onboarding

### 4. API Endpoints Scoped
The following endpoints now include tenant isolation:

#### Products & Inventory
- `GET /api/products` - Tenant-filtered
- `GET /api/products/all` - Tenant-filtered
- `POST /api/products` - Sets tenant_id
- `PUT /api/products/<id>` - Tenant-validated
- `DELETE /api/products/<id>` - Tenant-validated

#### Floors & Tables
- `GET /api/floors` - Tenant-filtered
- `POST /api/floors` - Sets tenant_id
- `POST /api/tables` - Sets tenant_id
- `DELETE /api/tables/<id>` - Tenant-validated
- `PUT /api/tables/<id>/status` - Tenant-validated

#### Payments & Orders
- `GET /api/payment-methods` - Tenant-filtered
- `PUT /api/payment-methods/<id>` - Tenant-validated
- `POST /api/orders` - Sets tenant_id on creation
- `POST /api/orders/<id>/send-kitchen` - Sets KitchenTicket.tenant_id
- `GET /api/kitchen/orders` - Tenant-filtered
- `GET /api/kitchen/tickets` - Tenant-filtered
- `POST /api/kitchen/tickets/<id>/advance` - Tenant-validated

#### Sessions & Bills
- `POST /api/sessions/open` - Sets tenant_id
- `GET /api/bills` - Tenant-filtered (via order)
- `GET /api/bills/table/<id>` - Tenant-filtered (via order)

#### Cafe Settings & Configuration
- `GET /api/cafe-settings` - Tenant-filtered
- `POST /api/cafe-settings` - Tenant-validated

#### Reviews & Feedback
- `GET /api/reviews` - Tenant-filtered
- `POST /api/orders/<id>/review` - Tenant-filtered

#### Branches & Management
- `GET /api/branches` - Tenant-filtered
- `POST /api/branches` - Sets tenant_id
- `POST /api/branches/switch` - Tenant-validated
- `GET /api/admin/branches/compare` - Tenant-filtered

#### Attendance & Staff
- `GET /api/attendance/status` - Returns tenant_id
- `POST /api/attendance/clock` - Sets tenant_id on event
- `GET /api/admin/attendance-report` - Tenant-filtered
- `PATCH /api/admin/attendance/shifts/<id>` - Tenant-validated

#### User Management
- `GET /api/users` - Tenant-filtered
- `POST /api/users` - Sets tenant_id and validates
- `PUT /api/users/<id>` - Tenant-validated
- `DELETE /api/users/<id>` - Tenant-validated

#### Reservations
- `GET /api/reservations` - Tenant-filtered
- `POST /api/reservations` - Sets tenant_id
- `PUT /api/reservations/<id>` - Tenant-validated
- `DELETE /api/reservations/<id>` - Tenant-validated
- `POST /api/reservations/<id>/seat` - Tenant-validated
- `POST /api/reservations/<id>/confirm` - Tenant-validated
- `POST /api/reservations/<id>/done` - Tenant-validated

#### Dashboard & Analytics
- `GET /api/dashboard/stats` - Tenant-filtered

#### Self-Order (Customer QR)
- `POST /api/self-order` - Sets tenant_id on order and kitchen ticket
- `GET /api/self-order/<id>/status` - Tenant-validated

### 5. Database Migration Script Created
- File: `migrate_to_saas.py`
- Automatically creates "Default Tenant"
- Assigns all existing data to the tenant
- Sets first restaurant admin as tenant owner

---

## 🔧 What Still Needs to Be Done

### 1. Run the Migration Script
```bash
# From pos-cafe directory
python migrate_to_saas.py
```

This will:
- Create a "Default Tenant" with slug `default`
- Assign all existing orders, users, products, etc. to that tenant
- Set the first restaurant admin as the tenant owner

### 2. Update Frontend Templates (Optional but Recommended)

#### Add Tenant Name to Dashboard Header (`templates/dashboard.html`)
Insert after the user name display:
```html
<div class="text-xs text-gray-500 mt-2" id="tenant-info"></div>
```

Add JavaScript to fetch and display tenant info:
```javascript
// Add to the JavaScript section
fetch('/api/dashboard/stats')
  .then(r => r.json())
  .then(data => {
    // The tenant name can be fetched from the cafe-settings endpoint
    fetch('/api/cafe-settings')
      .then(r => r.json())
      .then(settings => {
        document.getElementById('tenant-info').textContent = `Business: ${settings.name}`;
      });
  });
```

#### Add Restaurant Registration to Auth Page (`templates/auth.html`)
Add a fourth tab button:
```html
<button class="tab-btn" id="tab-register" onclick="switchTab('register')">Register Restaurant</button>
```

Add a new form panel after the signup form:
```html
<!-- ── REGISTER RESTAURANT ── -->
<div class="form-panel" id="form-register">
  <div class="form-card-head">
    <div class="form-eyebrow">New Restaurant</div>
    <div class="form-title">Start <em>selling.</em></div>
    <div class="form-sub">Set up your restaurant and invite your team.</div>
  </div>
  <div class="form-card-body">
    <div class="alert error" id="register-alert">
      <span>⚠</span><span id="register-alert-msg">Please fill in all fields.</span>
    </div>
    
    <!-- Business Info -->
    <div class="field">
      <label>Restaurant Name</label>
      <input type="text" id="register-name" placeholder="My Awesome Cafe" autocomplete="organization">
    </div>
    
    <div class="field">
      <label>Your Full Name</label>
      <input type="text" id="register-owner-name" placeholder="John Doe" autocomplete="name">
    </div>
    
    <div class="field">
      <label>Email Address</label>
      <input type="email" id="register-email" placeholder="you@restaurant.com" autocomplete="email">
    </div>
    
    <div class="field">
      <label>Password</label>
      <div class="pw-wrap">
        <input type="password" id="register-password" placeholder="Create a strong password" autocomplete="new-password" oninput="renderPasswordPolicy('register')">
        <button type="button" class="pw-toggle" onclick="togglePassword('register-password', this)">Show</button>
      </div>
      <div class="strength-wrap">
        <div class="strength-bars">
          <div class="strength-bar" id="reg-b1"></div>
          <div class="strength-bar" id="reg-b2"></div>
          <div class="strength-bar" id="reg-b3"></div>
          <div class="strength-bar" id="reg-b4"></div>
        </div>
        <div class="strength-meta">
          <span class="strength-label" id="reg-strength-label">Enter a password</span>
        </div>
      </div>
      <div class="policy-grid" id="register-rules"></div>
    </div>
    
    <div class="field">
      <label>Phone Number (Optional)</label>
      <input type="tel" id="register-phone" placeholder="+1 (555) 000-0000">
    </div>
    
    <button class="btn-primary" id="register-btn" onclick="doRegisterRestaurant()" style="margin-top:8px">
      Create Restaurant →
    </button>
    
    <div class="security-note">
      <span class="security-note-icon">🔒</span>
      <span class="security-note-text"><strong>Secure setup:</strong> You'll be logged in as the owner and can invite staff afterward.</span>
    </div>
  </div>
</div>
```

Add JavaScript handler:
```javascript
async function doRegisterRestaurant() {
  const name = document.getElementById('register-name').value.trim();
  const ownerName = document.getElementById('register-owner-name').value.trim();
  const email = document.getElementById('register-email').value.trim();
  const password = document.getElementById('register-password').value;
  const phone = document.getElementById('register-phone').value.trim();

  if (!name || !ownerName || !email || !password) {
    showAlert('register', 'Please fill in all required fields.');
    return;
  }

  const error = strongPasswordError(password, email);
  if (error) {
    showAlert('register', error);
    return;
  }

  const btn = document.getElementById('register-btn');
  btn.disabled = true;
  btn.textContent = 'Setting up...';

  try {
    const res = await fetch('/api/register-restaurant', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        restaurant_name: name,
        owner_name: ownerName,
        email: email,
        password: password,
        phone: phone,
      }),
    });

    const data = await res.json();
    if (!res.ok) {
      showAlert('register', data.error || 'Creation failed');
      return;
    }

    // Show success
    showAlert('register', 'Restaurant created! Logging you in...', 'success');
    setTimeout(() => {
      window.location.href = '/dashboard';
    }, 1500);
  } catch (e) {
    showAlert('register', e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Create Restaurant →';
  }
}
```

### 3. Update Session Handling (Optional Enhancement)
When users log in, they should see their tenant context. The frontend can display:
- Current tenant name
- Available tenants (for multi-tenant access)
- Tenant switcher for admins

### 4. Platform Admin Dashboard (Future)
For platform admins (is_platform_admin=True), you can build:
- Tenant list view
- Billing & plan management
- Usage analytics
- Tenant activation/deactivation

---

## 📋 Verification Checklist

Before deploying to production, verify:

- [ ] Run `python migrate_to_saas.py` ✓ Creates Default Tenant
- [ ] Test login to verify tenant_id stored in session
- [ ] Create a new product and verify it has tenant_id
- [ ] Create a new user and verify tenant assignment
- [ ] Create an order and verify kitchen ticket has tenant_id
- [ ] Test that users only see their tenant's data
- [ ] Test platform admin can see all tenants (if implemented)
- [ ] Test /api/register-restaurant endpoint
- [ ] Verify dashboard stats show only tenant data
- [ ] Test branch isolation per tenant

---

## 🚀 Deployment Steps

1. **Backup Database**
   ```bash
   cp instance/pos.db instance/pos.db.backup
   ```

2. **Run Migration**
   ```bash
   python migrate_to_saas.py
   ```

3. **Test Existing Users**
   - Log in with existing user credentials
   - Verify they see their existing data
   - Verify tenant_id=1 (Default Tenant)

4. **Update Templates** (optional)
   - Add tenant name display to dashboard
   - Add restaurant registration form to auth

5. **Monitor Logs**
   - Watch for any attribute errors
   - Check that queries are properly filtered
   - Verify no unauthorized data access

---

## 🔐 Security Notes

- **Tenant Isolation**: All queries are automatically scoped by `apply_tenant_scope()`
- **Platform Admins**: Set `is_platform_admin=True` to bypass tenant filtering
- **Cross-Tenant Access**: Explicitly checked with `tenant_id != get_current_tenant_id()` → 403 Forbidden
- **Session Tenant ID**: Stored in Flask session, validated on every request
- **Branch Access**: Still enforced via `require_branch_access_or_403()` within tenant scope

---

## 📝 Notes

- All timestamps use UTC (`datetime.utcnow()`)
- Tenant slugs are generated from names (e.g., "My Cafe" → "my-cafe")
- The migration script is idempotent (safe to run multiple times)
- Existing data remains accessible to the Default Tenant
- New restaurants can be created via `/api/register-restaurant`

---

## 🆘 Troubleshooting

### Error: "AttributeError: tenant_id"
- Run the migration script to ensure all tables have the tenant_id column
- Database schema mismatch typically occurs if models.py hasn't been synced

### Users Not Seeing Their Data
- Verify `apply_tenant_scope()` is being called in the endpoint
- Check that `get_current_tenant_id()` returns a valid value in the session
- Ensure `tenant_id` is being set on record creation

### Missing Tenant ID on New Records
- Verify the endpoint calls `get_current_tenant_id()`
- Ensure session has valid `tenant_id` after login
- Check auth routes are setting tenant_id in session properly

---

## 📚 API Examples

### Register a New Restaurant
```bash
curl -X POST http://localhost:5000/api/register-restaurant \
  -H "Content-Type: application/json" \
  -d '{
    "restaurant_name": "Pizza Palace",
    "owner_name": "John Smith",
    "email": "john@pizzapalace.com",
    "password": "SecurePass123!"
  }'
```

### Get Dashboard Stats (Tenant-Filtered)
```bash
curl -X GET http://localhost:5000/api/dashboard/stats?period=today \
  -H "Cookie: session=<session_token>"
```

### Create a Product (Sets Tenant ID)
```bash
curl -X POST http://localhost:5000/api/products \
  -H "Content-Type: application/json" \
  -H "Cookie: session=<session_token>" \
  -d '{
    "name": "Espresso",
    "price": 2.50,
    "category_id": 1
  }'
```

---

Last Updated: April 2026
Version: 1.0 (Multi-Tenant SaaS Ready)
