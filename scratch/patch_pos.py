import os

file_path = r'c:\Users\Shrey\OneDrive\Desktop\pos-cafe\templates\pos.html'
modal_html = """
<!-- ═══ MORE ACTIONS MODAL ═══ -->
<div id="more-actions-modal" class="hidden fixed inset-0 z-[110] flex items-end sm:items-center justify-center p-4 modal-bg">
  <div class="modal-content w-full max-w-sm bg-card border border-border rounded-2xl shadow-2xl overflow-hidden">
    <div class="p-4 border-b border-border flex items-center justify-between">
      <h3 class="font-700">More Actions</h3>
      <button onclick="closeMoreActions()" class="p-2 text-gray-500">&times;</button>
    </div>
    <div class="p-4 space-y-3">
      <button id="attendance-btn" onclick="handleAttendance()" class="w-full flex items-center gap-3 p-4 rounded-xl border border-border hover:bg-white/5 transition">
        <span class="text-xl">📅</span>
        <div class="text-left">
          <div id="attendance-label" class="font-700 text-sm">Clock In</div>
          <div class="text-[10px] text-gray-500 uppercase">Staff Duty Status</div>
        </div>
      </button>
      
      <a href="/backend" class="w-full flex items-center gap-3 p-4 rounded-xl border border-border hover:bg-white/5 transition">
        <span class="text-xl">🟧</span>
        <div class="text-left">
          <div class="font-700 text-sm">Open Backend</div>
          <div class="text-[10px] text-gray-500 uppercase">Manage Products & Settings</div>
        </div>
      </a>

      <button onclick="closeSession()" class="w-full flex items-center gap-3 p-4 rounded-xl border border-border hover:bg-white/5 transition">
        <span class="text-xl">💰</span>
        <div class="text-left">
          <div class="font-700 text-sm">Close Register</div>
          <div class="text-[10px] text-gray-500 uppercase">Finalize Today's Session</div>
        </div>
      </button>

      <div class="pt-4 border-t border-border">
        <button onclick="logout()" class="w-full flex items-center justify-center gap-2 p-3 rounded-xl bg-red-500/10 text-red-500 font-700 text-sm border border-red-500/20 hover:bg-red-500/20 transition">
          ↩ Logout Account
        </button>
      </div>
    </div>
  </div>
</div>
"""

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the last {% endblock %}
target_idx = -1
for i in range(len(lines) - 1, -1, -1):
    if '{% endblock %}' in lines[i]:
        target_idx = i
        break

if target_idx != -1:
    lines.insert(target_idx, modal_html + '\n')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print("Success: Modal inserted.")
else:
    print("Error: Could not find endblock.")
