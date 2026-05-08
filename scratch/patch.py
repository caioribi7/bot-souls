import os

shop_path = "cogs/shop.py"
new_views_path = "scratch/new_views.py"

with open(shop_path, "r", encoding="utf-8") as f:
    content = f.read()

with open(new_views_path, "r", encoding="utf-8") as f:
    new_views_content = f.read()

start_marker = "# ── Shop Panel View ───────────────────────────────────────────────────────────\n\nclass ShopPanelView"
end_marker = "# ── Shop Cog ──────────────────────────────────────────────────────────────────\n\nclass Shop"

start_idx = content.find(start_marker)
if start_idx == -1:
    print("Start marker not found.")
    exit(1)

end_idx = content.find(end_marker, start_idx)
if end_idx == -1:
    print("End marker not found.")
    exit(1)

new_content = content[:start_idx] + new_views_content + "\n\n" + content[end_idx:]

with open(shop_path, "w", encoding="utf-8") as f:
    f.write(new_content)

print("Patched successfully.")
