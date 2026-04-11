import os

auth_path = 'templates/auth.html'
if os.path.exists(auth_path):
    with open(auth_path, 'r', encoding='utf-8') as f:
        content = f.read()

    new_root = """:root {
  --ink:    #f9fafb;
  --ink2:   #ffffff;
  --ink3:   #f3f4f6;
  --ink4:   #e5e7eb;
  --ember:  #714b67;
  --ember2: #875a7b;
  --ember3: #5c3d53;
  --cream:  #111827;
  --muted:  #4b5563;
  --muted2: #6b7280;
  --white:  #111827;
  --border: rgba(0,0,0,0.1);
  --border-e: rgba(113,75,103,0.18);
}"""

    import re
    content = re.sub(r':root\s*\{[^}]+\}', new_root, content)

    # Convert dark specific colors in auth.html
    content = content.replace('rgba(255,255,255,.03)', 'rgba(0,0,0,.03)')
    content = content.replace('rgba(255,255,255,.04)', 'rgba(0,0,0,.04)')
    content = content.replace('rgba(255,255,255,.05)', 'rgba(0,0,0,.05)')
    content = content.replace('rgba(255,255,255,.07)', 'rgba(0,0,0,.07)')
    content = content.replace('rgba(255,255,255,.09)', 'rgba(0,0,0,.09)')
    content = content.replace('rgba(255,255,255,.1)', 'rgba(0,0,0,.1)')
    content = content.replace('rgba(255,255,255,.12)', 'rgba(0,0,0,.12)')
    content = content.replace('rgba(255,255,255,.15)', 'rgba(0,0,0,.15)')
    content = content.replace('rgba(255,249,242,.5)', 'var(--muted)')
    content = content.replace('rgba(255,249,242,.65)', 'var(--muted)')
    content = content.replace('rgba(255,249,242,.7)', 'var(--muted)')

    # Embers
    content = content.replace('249,115,22', '113,75,103')
    content = content.replace('234,88,12', '113,75,103')

    # Remove grain by setting opacity to 0
    content = content.replace('opacity:.45; animation: grainShift', 'opacity: 0; animation: grainShift')

    with open(auth_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed auth.html")
    
landing_path = 'templates/landing.html'
if os.path.exists(landing_path):
    with open(landing_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Dark colors -> Light
    content = content.replace('linear-gradient(135deg, #0a0a0a 0%, #1a0f0a 100%)', '#f9fafb')
    content = content.replace('color: #f0f0f0;', 'color: #111827;')
    content = content.replace('linear-gradient(135deg, #f97316, #ea580c)', '#714B67')
    content = content.replace('linear-gradient(135deg, rgba(249, 115, 22, 0.1), rgba(234, 88, 12, 0.05))', 'linear-gradient(135deg, rgba(113, 75, 103, 0.1), rgba(113, 75, 103, 0.05))')
    content = content.replace('color: #f97316', 'color: #714b67')
    content = content.replace('border-color: #f97316', 'border-color: #714b67')
    content = content.replace('rgba(255, 255, 255, 0.06)', 'rgba(0, 0, 0, 0.05)')
    content = content.replace('rgba(255, 255, 255, 0.1)', 'rgba(0, 0, 0, 0.1)')
    content = content.replace('rgba(26, 26, 26, 0.8)', 'rgba(255, 255, 255, 0.8)')
    content = content.replace('rgba(26, 26, 26, 0.6)', '#ffffff')
    content = content.replace('rgba(255, 255, 255, 0.08)', 'rgba(0, 0, 0, 0.08)')
    content = content.replace('bg-black/40', 'bg-white/80')
    content = content.replace('text-gray-900', 'text-gray-900') 
    content = content.replace('text-orange-500', 'text-brand-600')
    content = content.replace('hover:text-orange-500', 'hover:text-brand-600')
    content = content.replace('bg-[#111]', 'bg-white')
    content = content.replace('border-[rgba(255,255,255,0.08)]', 'border-border')
    content = content.replace('text-white', 'text-white') # just leave button white text

    with open(landing_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed landing.html")
    
customer_path = 'templates/customer.html'
if os.path.exists(customer_path):
    with open(customer_path, 'r', encoding='utf-8') as f:
        content = f.read()

    content = content.replace('bg-[#0f0f0f]', 'bg-surface')
    content = content.replace('bg-[#1a1a1a]', 'bg-card')
    content = content.replace('border-[#2a2a2a]', 'border-border')
    content = content.replace('text-white', 'text-gray-900')
    content = content.replace('text-gray-400', 'text-gray-500')
    content = content.replace('bg-gray-800', 'bg-gray-100')
    content = content.replace('bg-[#f97316]', 'bg-brand-600')
    content = content.replace('text-[#f97316]', 'text-brand-600')
    content = content.replace('hover:bg-[#ea580c]', 'hover:bg-brand-700')
    
    with open(customer_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed customer.html")
