# Mobile Responsiveness Testing Guide

## Quick Desktop Testing (Using DevTools)

1. **Open Chrome/Firefox DevTools** (F12 or Right-click → Inspect)
2. **Enable Device Emulation** (Ctrl+Shift+M or View → Toggle Device Toolbar)
3. **Select Mobile Device** (iPhone 12, Pixel 5, or any 375-768px width)

## Test Checklist

### Bottom Navigation Bar Visibility
- [ ] Load the POS page in mobile view (max-width: 1024px or 768px)
- [ ] Navigate to **Floor View** - See bottom nav with buttons: Floor, Takeaway, Bills, Reservations, History, More
- [ ] Navigate to **Order View** - See bottom nav + floating "View Order" button above it
- [ ] Navigate to **Bills View** - See bottom nav (should be visible)
- [ ] Rotate device (landscape) - Bottom nav should still be visible

### Cart Drawer Functionality
- [ ] In Order View, click a product to add to cart
- [ ] Verify "View Order" button appears above bottom nav
- [ ] Click "View Order" button
- [ ] Cart drawer should slide in from right side (full-width popup on mobile)
- [ ] Click backdrop (semi-transparent area) to close drawer
- [ ] Drawer should slide back out to the right

### Content Overlap Prevention
- [ ] Scroll through any view with multiple items
- [ ] Verify content doesn't disappear behind the 70px bottom navigation bar
- [ ] The last item should be readable with padding below it
- [ ] Bottom nav should remain fixed in position while scrolling

### Touch Target Sizing
- [ ] Navigation buttons should be easily tappable (min 44px height)
- [ ] Product buttons should be easily tappable
- [ ] Form inputs should have minimum 44px height

### Landscape Mode
- [ ] Rotate to landscape (max-width: 600px typically)
- [ ] Bottom nav should still display properly
- [ ] Cart drawer should still work
- [ ] Sidebar should remain hidden

## Browser Console Check

1. Open **DevTools Console** (F12 → Console tab)
2. Look for any red error messages
3. Expected: No JavaScript errors related to `toggleCartDrawer()`, `showView()`, or DOM selectors

## CSS Media Query Verification (DevTools Elements Tab)

1. **Right-click any element** → Select "Inspect"
2. Look at the **Computed Styles** section
3. For `.mobile-bottom-nav`:
   - Should see: `display: flex` on mobile (<1024px)
   - Should see: `display: none` on desktop (>1024px)
4. For `.cart-panel-standard`:
   - Mobile: Should be `position: fixed`, `width: 100%`
   - Desktop: Should be `position: relative`, `width: 300px`

## Breakpoint Testing

Test at these specific widths using DevTools:
- **iPhone SE (375px)** - Small mobile
- **iPhone 12 (390px)** - Standard mobile
- **iPad (768px)** - Tablet
- **Desktop (1440px)** - Full desktop

Bottom nav should:
- ✓ Show at 375px
- ✓ Show at 390px  
- ✓ Show at 768px
- ✗ NOT show at 1440px (should be hidden on desktop)

## Potential Troubleshooting

### Bottom Nav Not Visible
1. Check browser zoom level (should be 100%)
2. Check DevTools device emulation is active
3. Open console and run: `getComputedStyle(document.querySelector('.mobile-bottom-nav')).display`
   - Should return `flex` on mobile
4. Check if width is below 1024px

### Cart Drawer Not Opening
1. Verify you're on Order View
2. Check browser console for JavaScript errors
3. Try clicking the backdrop - does drawer close properly?
4. Run in console: `document.querySelector('.cart-panel-standard')`
   - Should return the cart panel element

### Content Hidden Behind Nav
1. Check the view section has `padding-bottom: 90px`
2. Verify bottom nav height is 70px in CSS
3. Test on multiple browsers (Chrome, Firefox, Safari)

## Performance Notes

- Bottom nav uses `position: fixed` for consistent visibility while scrolling
- Cart drawer uses CSS `transform: translateX()` for smooth animations
- No layout shifts should occur during interactions
- Mobile responsiveness should be smooth without jumps or flickers

## Success Criteria

✓ Bottom navigation visible on all mobile views
✓ Cart drawer opens/closes smoothly
✓ Content doesn't overlap with fixed nav
✓ No console errors
✓ Touch targets are large enough (44px+)
✓ Works in both portrait and landscape
