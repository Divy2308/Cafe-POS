# Testing Guide - Kitchen & Customer Display Features

## Prerequisites

1. Delete the old database to ensure new schema:
   ```bash
   rm instance/pos.db
   ```

2. Start the Flask app:
   ```bash
   python app.py
   ```

The app will automatically:
- Create new database with timestamp fields
- Seed demo data
- Initialize all tables

---

## Step-by-Step Testing

### Part 1: Setup (5 minutes)

1. **Open three browser windows/tabs:**
   - **Window 1:** POS Terminal - `http://localhost:5000/pos`
   - **Window 2:** Kitchen Display - `http://localhost:5000/kitchen`
   - **Window 3:** Customer Display - `http://localhost:5000/customer`

2. **Login to POS:**
   - Auto-creates demo user on first signup
   - Use: `admin@restaurant.com` / (password shown on screen)
   - Or create new account

3. **Open Session:**
   - Click "Register" on POS
   - Click "Open Session" button
   - Confirm session opened

---

### Part 2: Create & Send Order (5 minutes)

1. **Create Order:**
   - Click table (e.g., Table 1)
   - Add products: Pizza (×1), Coffee (×1)
   - Review order with totals
   - Confirm

2. **Send to Kitchen:**
   - Click "Send to Kitchen" button
   - **Channel Window 2** (Kitchen) - New ticket appears in "To Cook" column
   - **Verify:**
     - Order number visible
     - Table number shown
     - Pizza ₹350 + Coffee ₹80 = ₹430 total
     - "5s ago" timestamp
     - Status indicator

3. **Customer Display:**
   - **Window 3** should show order received
   - 📋 Received (completed)
   - 👨‍🍳 Preparing (active/orange)
   - ✓ Ready (pending/gray)

---

### Part 3: Kitchen Operations (3 minutes)

1. **Start Preparing:**
   - In Kitchen Display (Window 2), click the ticket card
   - Card moves to "Preparing" column
   - **Verify:**
     - Time updated: "X prep" now shows
     - Status indicator changes
     - All items marked as "preparing"
     - Timestamp captured

2. **Mark Items Done:**
   - Click individual items in ticket
   - Items show strikethrough (✓)
   - **Verify in POS:**
     - Item status updates in backend

3. **Complete Order:**
   - When all items done, click ticket again
   - Moves to "Completed" column in Kitchen
   - Kitchen staff say order is ready to serve

---

### Part 4: Verify Customer Display (3 minutes)

**Window 3 (Customer Display) should show:**

1. **After sending to kitchen:**
   - Order number: "001" (large, prominent)
   - Status badge: Orange "Preparing"
   - Progress bar: 📋 → 👨‍🍳 (active)
   - Items listed:
     - Pizza Margherita ₹350 × 1
     - Coffee ₹80 × 1
   - Total: ₹430
   - Message: "Your order is being prepared..."
   - Time elapsed: "2 mins ago"

2. **When kitchen marks as preparing:**
   - Badge stays "Preparing"
   - Progress shows preparing stage active
   - Time counter updates

3. **When kitchen marks as complete:**
   - Badge changes to "Ready!" (Green)
   - Progress bar: Both ✓ active
   - Message: "Your order is ready! Pick it up from the counter."
   - Card background turns green

---

### Part 5: Payment & Completion (3 minutes)

1. **Proceed to Payment:**
   - In POS, click "Complete Order" or "Payment"
   - Select payment method (Cash/UPI/Digital)
   - Confirm payment

2. **Complete Transaction:**
   - Payment marked as complete
   - Order status becomes "Paid"

3. **Verify Customer Display:**
   - Badge shows "Paid" (Green)
   - Message: "Order complete! Thank you for ordering."
   - All progress stages completed

---

## ✅ Verification Checklist

### Kitchen Display Checks
- [ ] New order appears immediately in "To Cook" column
- [ ] Order shows: number, table, items with prices, total
- [ ] Time "X mins ago" updates every second
- [ ] Clicking ticket moves to "Preparing"
- [ ] "X min prep" timer starts
- [ ] Clicking items shows/hides strikethrough
- [ ] All items done → moves to "Completed"
- [ ] Completed orders fade out
- [ ] Real-time updates (no page refresh needed)

### Customer Display Checks
- [ ] Idle state shows initially
- [ ] Order appears immediately after kitchen send
- [ ] Progress bar shows 3 stages (Received, Preparing, Ready)
- [ ] Status badge shows correct color:
  - Blue (Pending)
  - Orange (Preparing)
  - Green (Ready/Paid)
- [ ] Items display with name, price, quantity
- [ ] Total calculates correctly
- [ ] Time elapsed updates every second
- [ ] Progress bar animate when status changes
- [ ] Message updates based on status
- [ ] Real-time: no manual refresh needed

### Backend/API Checks
- [ ] Kitchen endpoint returns: `total`, `sent_at`, `started_at`, `time_in_prep`
- [ ] Each item includes: `price`, `status`, `started_at`, `completed_at`
- [ ] Timestamps are ISO 8601 format
- [ ] WebSocket events emit correctly:
  - `ticket_update` when ticket status changes
  - `order_update` when order completes
  - `item_update` when items marked done

---

## 🚨 Common Issues & Solutions

### Issue: Database not updating
**Solution:** 
```bash
rm instance/pos.db
python app.py  # Recreate
```

### Issue: Kitchen display not showing full details
**Solution:**
- Verify API response includes `total` and `price`
- Check browser console for JavaScript errors
- Reload kitchen display page

### Issue: Customer display not updating
**Solution:**
- Ensure SocketIO connected (check console)
- Verify order was sent to kitchen (appears in kitchen)
- Check timestamp fields are populated

### Issue: Real-time updates not working
**Solution:**
- Check both windows have same `http://localhost:5000`
- Verify Flask SocketIO initialized
- Check browser allows WebSockets
- Look at console for connection errors

---

## 📊 Data to Verify

After completing test, check database:

```sql
-- SQLite query to verify order data
SELECT 
  o.id,
  o.order_number,
  o.created_at,
  o.sent_to_kitchen_at,
  o.started_at,
  o.completed_at,
  o.total
FROM "order" o;

-- Check items
SELECT 
  oi.id,
  oi.product_name,
  oi.qty,
  oi.price,
  oi.kitchen_status,
  oi.started_at,
  oi.completed_at
FROM order_item oi;

-- Check kitchen tickets
SELECT 
  kt.id,
  kt.order_id,
  kt.status,
  kt.sent_at,
  kt.started_at,
  kt.completed_at
FROM kitchen_ticket kt;
```

---

## 🎯 Performance Testing

To test with multiple orders:

1. Create 5 orders quickly:
   - Table 1, 2, 3, 4, 5
   - Different items each

2. Kitchen display should:
   - Show all 5 in "To Cook"
   - Handle rapid status changes
   - Update times smoothly

3. Customer display:
   - Should work with any active order
   - Switch between windows to see sync

---

## 📸 Expected Screenshots

### Kitchen Display Expected Layout:
```
┌─ To Cook ────────┐  ┌─ Preparing ───────┐  ┌─ Completed ─────┐
│ #001  Table 1    │  │ (empty)           │  │ (empty)         │
│ ₹430    5s ago   │  │                   │  │                 │
│ Pizza ₹350       │  │                   │  │                 │
│ Coffee ₹80       │  │                   │  │                 │
│ 🔴 To Cook       │  │                   │  │                 │
└──────────────────┘  └───────────────────┘  └─────────────────┘
```

### Customer Display Expected Layout:
```
      POS Cafe
   #001
   Order Received     5 mins ago

   📋───→👨‍🍳───→✓
   Received Preparing Ready

   Your Items
   Pizza Margherita ₹350 × 1
   Coffee           ₹80  × 1

   Total: ₹430

   "Your order is being prepared..."
```

---

## 📝 Test Report Template

```
Date: ____
Tester: ____

✓ Database migration successful
✓ Kitchen display shows full order details
✓ Customer display shows progress
✓ Real-time updates working
✓ Timestamps captured correctly
✓ Status indicators working
✓ Color coding correct
✓ Time elapsed updating
✓ All items showing with prices
✓ Mobile/responsive working

Issues Found:
- (none or list)

Notes:
- (any observations)
```

---

## Next Steps for Full Feature Testing

After confirming basic functionality:

1. **Test with mobile kitchen display** (iPad/tablet at counter)
2. **Test with external customer display** (separate monitor)
3. **Test with multiple concurrent orders**
4. **Test payment integration with all methods**
5. **Performance test with 20+ orders**

---

## Rollback Instructions

If issues occur and need to revert:

```bash
# 1. Stop the Flask app
# 2. Delete database
rm instance/pos.db

# 3. Checkout previous version (if using git)
git checkout HEAD -- app.py templates/

# 4. Restart
python app.py
```

---

Done! You should now have a fully functional kitchen and customer display with real-time order tracking. 🚀
