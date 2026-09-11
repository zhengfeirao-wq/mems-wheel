"""校验仓库内所有 Markdown 相对链接与图片引用是否指向真实文件。"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LINK = re.compile(r'\[[^\]]*\]\(([^)]+)\)')
SKIP_SCHEMES = ('http://', 'https://', 'mailto:', '#', 'tel:')

broken = []
checked = 0

for md in sorted(ROOT.rglob('*.md')):
    if '.git' in md.parts:
        continue
    text = md.read_text(encoding='utf-8', errors='replace')
    for m in LINK.finditer(text):
        target = m.group(1).strip()
        if not target or target.startswith(SKIP_SCHEMES):
            continue
        target = target.split('#')[0].strip()      # 去掉锚点
        if not target:
            continue
        checked += 1
        resolved = (md.parent / target).resolve()
        if not resolved.exists():
            broken.append((md.relative_to(ROOT), target))

print(f"检查了 {checked} 个相对链接，涉及 {len(list(ROOT.rglob('*.md')))} 个 Markdown 文件")
if broken:
    print(f"\n失效链接 {len(broken)} 个：")
    for src, tgt in broken:
        print(f"  {src}\n      -> {tgt}")
    sys.exit(1)
print("\n全部链接有效 ✓")
