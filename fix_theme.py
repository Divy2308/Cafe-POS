import os

templates_dir = 'templates'
replacements = [
    ('bg-[#0a0a0a]', 'bg-surface'),
    ('bg-[#1a1a1a]', 'bg-card'),
    ('bg-[#0f0f0f]', 'bg-gray-50'),
    ('border-[#2a2a2a]', 'border-border'),
    ('text-[#f97316]', 'text-brand-600'),
    ('bg-[#f97316]', 'bg-brand-600'),
    ('hover:bg-[#ea580c]', 'hover:bg-brand-700'),
    ('text-gray-400', 'text-gray-500'),
    ('text-gray-300', 'text-gray-600'),
    ('bg-gradient-to-br from-[#f97316] to-[#ea580c]', 'brand-gradient text-white'),
    ('text-white', 'text-gray-900'),
    ('bg-[#f97316]/20', 'bg-brand-100'),
    ('bg-orange-600', 'bg-brand-600')
]

for filename in os.listdir(templates_dir):
    if not filename.endswith('.html'): continue
    filepath = os.path.join(templates_dir, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content
    for old, new in replacements:
        if old == 'text-white':
            # don't replace text-white if it's right after brand-gradient or in a btn-primary
            # we will just replace all, and then fix buttons
            content = content.replace(old, new)
        else:
            content = content.replace(old, new)
            
    # Fix buttons that should remain white text (since bg-brand-600 is dark purple)
    content = content.replace('bg-brand-600 hover:bg-brand-700 text-gray-900', 'bg-brand-600 hover:bg-brand-700 text-white')
    content = content.replace('brand-gradient text-gray-900', 'brand-gradient text-white')
    
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {filename}")
