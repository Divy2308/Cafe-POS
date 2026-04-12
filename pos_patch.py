import re
with open('templates/pos.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Add lookup timeout
html = re.sub(r'(let isTakeaway = false;)', r'\1\n  let lookupTimeout = null;', html)

# 2. Modify setOrderType to not hide CRM
target1 = "document.getElementById('takeaway-name-wrap').classList.toggle('hidden', !isTakeaway);"
html = html.replace(target1, "// global crm enabled")

# 3. Add JS functions
js_funcs = """
  async function checkCustomerPhone(phone) {
    if(phone.length < 10) return;
    clearTimeout(lookupTimeout);
    const icon = document.getElementById('crm-status-icon');
    icon.classList.remove('hidden');
    lookupTimeout = setTimeout(async () => {
      try {
        const r = await api('/api/customer/lookup?phone=' + encodeURIComponent(phone));
        if (r && r.found && r.name) {
            const nameEl = document.getElementById('customer-name');
            nameEl.value = r.name;
            // toast('Found: ' + r.name, 'success');
        }
      } catch(e) {}
      icon.classList.add('hidden');
    }, 500);
  }

  function printLastBill(e) {
    e.stopPropagation();
    if(lastPaidOrder && lastPaidOrder.id) {
       const printWindow = window.open('/receipt/' + lastPaidOrder.id, '_blank', 'width=400,height=600');
       if(printWindow) {
         printWindow.onload = () => { setTimeout(() => printWindow.print(), 500); };
       }
    }
  }
"""
html = html.replace('function setOrderType() {', js_funcs + '\n  function setOrderType() {')

# 4. Modify createOrUpdateOrder
html = html.replace("const customerName = (document.getElementById('takeaway-customer-name')?.value || '').trim();",
                    "const customerName = (document.getElementById('customer-name')?.value || '').trim();\n    const customerPhone = (document.getElementById('customer-phone')?.value || '').trim();")

html = html.replace("customer_name: customerName,", "customer_name: customerName,\n      customer_phone: customerPhone,")

# 5. Add Print button 
html = html.replace('<p class="text-xs text-gray-600">Tap anywhere to continue</p>',
'''<button id="btn-print-bill" class="btn-primary mt-4 py-3 px-6 rounded-xl font-medium" style="background:#f97316;color:white;width:100%" onclick="printLastBill(event)">🖨 Print Bill</button>
        <p class="text-xs text-gray-600 mt-4">Tap anywhere to continue</p>''')

with open('templates/pos.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('Done pos.html')
