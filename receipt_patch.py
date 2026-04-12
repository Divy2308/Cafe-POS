import re
with open('templates/receipt.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Logo
html = re.sub(
    r'<div class="r-logo">LOGO</div>',
    '''{% if cafe_settings and cafe_settings.logo_b64 %}
    <div style="text-align:center;margin: 0 auto 10px;">
      <img src="{{ cafe_settings.logo_b64 }}" style="max-width: 60px; max-height: 60px; object-fit: contain;">
    </div>
    {% else %}
    <div class="r-logo">LOGO</div>
    {% endif %}''',
    html
)

# 2. Shop Header
shop_header = r'''    <!-- Shop Header -->
    <div class="r-shop-name">{{ cafe_settings.name if cafe_settings else 'POS Cafe' }}</div>
    {% if cafe_settings and cafe_settings.address %}
    <div class="r-center r-small" style="max-width:200px;margin:0 auto;">{{ cafe_settings.address }}</div>
    {% endif %}
    {% if cafe_settings and cafe_settings.phone %}
    <div class="r-center r-small">Contact: {{ cafe_settings.phone }}</div>
    {% endif %}'''
html = re.sub(r'<!-- Shop Header -->.*?<hr class="r-rule-solid" style="margin-top:12px">', shop_header + '\n\n    <hr class="r-rule-solid" style="margin-top:12px">', html, flags=re.DOTALL)


# 3. Customer Info
cust_info = r'''    <!-- Customer Info -->
    {% if order.customer_name or order.customer_phone %}
    <div class="r-row">
      <span>Name: <strong>{{ order.customer_name or 'Walk-in' }}</strong></span>
      {% if order.customer_phone %}
      <span class="r-muted">M: {{ order.customer_phone }}</span>
      {% endif %}
    </div>
    <hr class="r-rule">
    {% endif %}'''
html = re.sub(r'<!-- Customer Info -->.*?<!-- Order Meta -->', cust_info + '\n\n    <!-- Order Meta -->', html, flags=re.DOTALL)


# 4. Math for Subtotal / Taxes / Tips
tax_logic = r'''      <div class="r-total-row">
        <span class="r-muted">Sub Total</span>
        <span>₹{{ "%.2f"|format(order.subtotal or subtotal_val.v) }}</span>
      </div>
      {% if order.tax_amount and order.tax_amount > 0 %}
      <div class="r-total-row">
        <span class="r-muted">CGST ({{ (cafe_settings.tax_rate/2) if cafe_settings else '2.5' }}%)</span>
        <span>₹{{ "%.2f"|format(order.tax_amount / 2) }}</span>
      </div>
      <div class="r-total-row">
        <span class="r-muted">SGST ({{ (cafe_settings.tax_rate/2) if cafe_settings else '2.5' }}%)</span>
        <span>₹{{ "%.2f"|format(order.tax_amount / 2) }}</span>
      </div>
      {% endif %}
      {% if order.tip and order.tip > 0 %}'''

html = re.sub(r'      <div class="r-total-row">\s*<span class="r-muted">Sub Total</span>\s*<span>.*?</span>\s*</div>\s*(?=\{%\s*if\s*order\.tip)', tax_logic, html, flags=re.DOTALL)


with open('templates/receipt.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('Done!')
