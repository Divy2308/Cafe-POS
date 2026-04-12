import re

with open('templates/pos.html', 'r', encoding='utf-8') as f:
    html = f.read()

target = r'<!-- Customer name \(shown only for takeaway\) -->.*?<div id="takeaway-name-wrap"[^>]*>.*?<input type="text" id="takeaway-customer-name"[^>]*>.*?</div>'
replacement = """
          <!-- Customer CRM -->
          <div id="customer-crm-wrap" class="space-y-2 mt-2">
            <div class="relative">
              <input type="text" id="customer-phone" placeholder="Customer Phone" maxlength="15"
                class="text-xs w-full px-3 py-2 bg-gray-900 border border-border rounded-lg text-white pr-8"
                oninput="checkCustomerPhone(this.value)" />
              <div id="crm-status-icon" class="absolute right-2 top-1.5 text-gray-500 hidden">
                <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
              </div>
            </div>
            <input type="text" id="customer-name" placeholder="Customer Name (optional)"
              class="text-xs w-full px-3 py-2 bg-gray-900 border border-border rounded-lg text-white" />
          </div>
"""

new_html = re.sub(target, replacement, html, flags=re.DOTALL)

with open('templates/pos.html', 'w', encoding='utf-8') as f:
    f.write(new_html)
print("Done")
