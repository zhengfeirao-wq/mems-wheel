#!/usr/bin/env python3
"""读取校零档案，查看历史与零点漂移。

用法
----
    python tools/tare_journal.py show                    # 列出全部校零记录
    python tools/tare_journal.py drift 0x0A              # 某块板的零点漂移
    python tools/tare_journal.py drift 0x0A --channel 3  # 只看某通道
    python tools/tare_journal.py latest 0x0A --out t.json   # 导出最新一次，供恢复用
    python tools/tare_journal.py restore raw.csv t.json  # 把 CSV 里的校零值还原成原始值
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tactile500.tare import DEFAULT_JOURNAL, TareJournal, TareResult, restore  # noqa: E402


def cmd_show(args) -> int:
    journal = TareJournal(args.journal)
    hist = journal.history(identity=args.identity)
    if not hist:
        print(f"档案为空：{journal.path}")
        return 1
    print(f"档案：{journal.path}    共 {len(hist)} 条\n")
    print(f"{'时间(UTC)':<22} {'时长':>5} {'记录':<24} 警告")
    for rec in hist:
        ident = " ".join(f"{r}={v}" for r, v in sorted((rec.get("identities") or {}).items()))
        warn = len(rec.get("warnings") or [])
        note = rec.get("note") or rec.get("session") or ""
        print(f"{rec.get('created_iso',''):<22} {rec.get('duration_s',0):>4.1f}s "
              f"{ident:<24} {warn}  {note}")
    return 0


def cmd_drift(args) -> int:
    journal = TareJournal(args.journal)
    rows = journal.drift(identity=args.identity)
    if not rows:
        print(f"没有 {args.identity} 的记录")
        return 1
    ch = args.channel
    if ch is not None:
        print(f"identity {args.identity}  ch{ch} 的零点漂移\n")
        print(f"{'时间(UTC)':<22} {'零点':>12} {'相对上次':>12} {'累计':>12}")
        first = rows[0]["offsets"][ch] if len(rows[0]["offsets"]) > ch else None
        prev = None
        for r in rows:
            if len(r["offsets"]) <= ch:
                continue
            v = r["offsets"][ch]
            step = "" if prev is None else f"{v - prev:+d}"
            total = "" if first is None else f"{v - first:+d}"
            print(f"{r['created_iso']:<22} {v:>12} {step:>12} {total:>12}")
            prev = v
        return 0

    print(f"identity {args.identity}：{len(rows)} 次校零，每通道漂移（末次 - 首次）\n")
    first, last = rows[0]["offsets"], rows[-1]["offsets"]
    n = min(len(first), len(last))
    print(f"{'通道':>4} {'首次零点':>12} {'末次零点':>12} {'漂移':>12}")
    for c in range(n):
        print(f"{c:>4} {first[c]:>12} {last[c]:>12} {last[c] - first[c]:>+12d}")
    if len(rows) > 1:
        print(f"\n时间跨度：{rows[0]['created_iso']}  →  {rows[-1]['created_iso']}")
    return 0


def cmd_latest(args) -> int:
    journal = TareJournal(args.journal)
    result = journal.latest(identity=args.identity) if args.identity else None
    if result is None:
        hist = journal.history()
        result = TareResult.from_json(hist[-1]) if hist else None
    if result is None:
        print("档案为空")
        return 1
    data = result.to_json()
    out = Path(args.out)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已导出：{out}")
    print(result.summary())
    for role, offs in result.offsets.items():
        print(f"  {role:16} {len(offs):2} 通道  前3偏移 {offs[:3]}")
    return 0


def cmd_restore(args) -> int:
    """把一份校零后的 CSV 还原成原始值。

    CSV 需含 output_unix_ns 或 receive_unix_ns 作为时间列，以及 p1..pN 列。
    """
    tare = TareResult.from_json(json.loads(Path(args.tare).read_text(encoding="utf-8")))
    role = args.role
    if role is None:
        role = next(iter(tare.offsets))
    offsets = tare.offsets_for(role)
    if not offsets:
        print(f"该档案里没有 role={role} 的偏移")
        return 1

    src = Path(args.csv)
    dst = Path(args.out) if args.out else src.with_name(src.stem + "_restored.csv")
    with src.open(newline="", encoding="utf-8") as fin, dst.open("w", newline="", encoding="utf-8") as fout:
        reader = csv.reader(fin)
        writer = csv.writer(fout)
        header = next(reader, None)
        if header:
            writer.writerow(header + ["restored"])
        n = 0
        for row in reader:
            try:
                pcol = [i for i, h in enumerate(header or []) if h.startswith("p") and h[1:].isdigit()]
                vals = [int(float(row[i])) for i in pcol]
                if len(vals) != len(offsets):
                    raise ValueError(f"列数 {len(vals)} 与偏移 {len(offsets)} 不符")
                writer.writerow(row + [" ".join(str(v) for v in restore(vals, offsets))])
                n += 1
            except (ValueError, IndexError):
                writer.writerow(row + [""])
    print(f"role={role}  还原 {n} 行  →  {dst}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="校零档案：历史、漂移与还原")
    ap.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("show", help="列出校零记录")
    p.add_argument("--identity", help="只显示含该板的记录，如 0x0A")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("drift", help="查看零点漂移")
    p.add_argument("identity", help="板 identity，如 0x0A")
    p.add_argument("--channel", type=int, help="只看某个通道")
    p.set_defaults(func=cmd_drift)

    p = sub.add_parser("latest", help="导出最新一次校零")
    p.add_argument("identity", nargs="?", help="板 identity（可选）")
    p.add_argument("--out", default="tare_latest.json")
    p.set_defaults(func=cmd_latest)

    p = sub.add_parser("restore", help="把校零后的 CSV 还原成原始值")
    p.add_argument("csv")
    p.add_argument("tare")
    p.add_argument("--role", help="角色名，缺省取档案里第一个")
    p.add_argument("--out", help="输出路径")
    p.set_defaults(func=cmd_restore)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
