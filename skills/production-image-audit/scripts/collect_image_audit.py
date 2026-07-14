#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import shlex
import subprocess
import tarfile
from pathlib import Path


DEFAULT_SERVER = "root@47.251.185.234"
DEFAULT_SSH_KEY = "/Users/chenzhiyuan/.ssh/id_ed25519_wanmeixiangsu_server_20260608"
DEFAULT_REMOTE_BACKEND = "/data/decoration-assistant/backend"
DEFAULT_REMOTE_DATA = "/data/decoration-assistant-data"


REMOTE_SCRIPT = r'''
import json
import math
import re
import sqlite3
import tarfile
from pathlib import Path
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFont

cfg = json.loads("""__CFG_JSON__""")
data_dir = Path(cfg["remote_data_dir"])
workspaces = data_dir / "workspaces"
out = Path(cfg["remote_out"])
out.mkdir(parents=True, exist_ok=True)

con = sqlite3.connect(data_dir / "data.db")
con.row_factory = sqlite3.Row
since = datetime.utcnow() - timedelta(hours=float(cfg["hours"]))
rows = con.execute(
    """
    select s.id session_id, s.role, t.id turn_id, t.status, t.created_at, t.completed_at,
           t.prompt, t.attachments, t.output_image, t.output_images, t.error_code, t.error
    from turns t join sessions s on s.id=t.session_id
    where s.role = ?
      and t.created_at >= ?
    order by t.created_at asc
    """,
    (cfg["role"], since.isoformat()),
).fetchall()

max_items = int(cfg.get("max_items") or 0)
if max_items > 0:
    rows = rows[-max_items:]

font_candidates = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def load_font(size):
    for path in font_candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


font = load_font(20)
small = load_font(16)
manifest = [
    "\t".join(
        [
            "idx",
            "session_id",
            "turn_id",
            "created_cst",
            "status",
            "role",
            "room_type",
            "style",
            "input_rel",
            "output_rel",
            "error_code",
            "prompt",
        ]
    )
]
items = []

for idx, row in enumerate(rows, 1):
    prompt = row["prompt"] or ""
    room = (re.search(r"房间类型:\s*([^\n|]+)", prompt) or [None, ""])[1].strip()
    style = (re.search(r"装修风格:\s*([^\n|]+)", prompt) or [None, ""])[1].strip()
    attachments = []
    if row["attachments"]:
        try:
            attachments = json.loads(row["attachments"])
        except Exception:
            attachments = []
    input_rel = attachments[0] if attachments else ""
    output_rel = row["output_image"] or ""
    created_cst = (
        datetime.fromisoformat(row["created_at"])
        .replace(tzinfo=timezone.utc)
        .astimezone(timezone(timedelta(hours=8)))
        .strftime("%H:%M:%S")
    )
    manifest.append(
        "\t".join(
            [
                str(idx),
                row["session_id"],
                row["turn_id"],
                created_cst,
                row["status"],
                row["role"],
                room,
                style,
                input_rel,
                output_rel,
                row["error_code"] or "",
                prompt.replace("\n", " | ").replace("\t", " ")[:800],
            ]
        )
    )
    input_path = workspaces / input_rel if input_rel else None
    output_path = workspaces / output_rel if output_rel else None
    if input_path and output_path and input_path.exists() and output_path.exists():
        items.append((idx, row["session_id"], created_cst, row["status"], room, style, input_path, output_path))

(out / "manifest.tsv").write_text("\n".join(manifest) + "\n", encoding="utf-8")


def fit_image(path, box_w, box_h):
    im = Image.open(path).convert("RGB")
    im.thumbnail((box_w, box_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (box_w, box_h), "white")
    canvas.paste(im, ((box_w - im.width) // 2, (box_h - im.height) // 2))
    return canvas


pair_w = int(cfg["pair_width"])
pair_h = int(cfg["pair_height"])
label_h = 56
img_w = (pair_w - 38) // 2
img_h = pair_h - label_h - 14
cols = int(cfg["cols"])
rows_per_sheet = int(cfg["rows_per_sheet"])
per_sheet = cols * rows_per_sheet

for sheet_idx in range(math.ceil(len(items) / per_sheet) if items else 0):
    sheet = Image.new("RGB", (cols * pair_w, rows_per_sheet * pair_h), (245, 245, 245))
    draw = ImageDraw.Draw(sheet)
    chunk = items[sheet_idx * per_sheet : (sheet_idx + 1) * per_sheet]
    for j, item in enumerate(chunk):
        idx, sid, created, status, room, style, input_path, output_path = item
        col = j % cols
        row = j // cols
        x = col * pair_w
        y = row * pair_h
        draw.rectangle([x + 5, y + 5, x + pair_w - 5, y + pair_h - 5], fill="white", outline=(180, 180, 180), width=2)
        label = f"{idx:02d} {created} {status} sid={sid}"
        draw.text((x + 14, y + 12), label, fill=(0, 0, 0), font=small)
        draw.text((x + 14, y + 31), "room/style/prompt: see manifest.tsv", fill=(90, 90, 90), font=small)
        draw.text((x + 70, y + label_h - 20), "INPUT", fill=(80, 80, 80), font=small)
        draw.text((x + img_w + 95, y + label_h - 20), "OUTPUT", fill=(80, 80, 80), font=small)
        sheet.paste(fit_image(input_path, img_w, img_h), (x + 14, y + label_h))
        sheet.paste(fit_image(output_path, img_w, img_h), (x + 24 + img_w, y + label_h))
    sheet.save(out / f"sheet_{sheet_idx + 1}.jpg", quality=86, optimize=True)

(out / "audit_notes.md").write_text(
    "# Production Image Audit Notes\n\n"
    "## Overall\n\n"
    "- Window:\n"
    "- Count/status:\n"
    "- Overall judgment:\n\n"
    "## Per-Sample Findings\n\n"
    "- 01:\n\n"
    "## Reusable Optimizations\n\n"
    "- Prompt/skill/SCL:\n\n"
    "## Coverage Gaps\n\n"
    "- \n",
    encoding="utf-8",
)

tar_path = Path(str(out) + ".tar.gz")
with tarfile.open(tar_path, "w:gz") as tar:
    tar.add(out, arcname=out.name)

print(json.dumps({"rows": len(rows), "items": len(items), "remote_dir": str(out), "remote_tar": str(tar_path)}, ensure_ascii=False))
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect production image-generation input/output comparison sheets.")
    parser.add_argument("--hours", type=float, default=2.0, help="Lookback window in hours.")
    parser.add_argument("--role", default="interior_renovation_rendering", help="Session role to audit.")
    parser.add_argument("--server", default=DEFAULT_SERVER, help="SSH target, e.g. root@host.")
    parser.add_argument("--ssh-key", default=DEFAULT_SSH_KEY, help="SSH private key path.")
    parser.add_argument("--remote-backend", default=DEFAULT_REMOTE_BACKEND, help="Remote backend directory with .venv.")
    parser.add_argument("--remote-data-dir", default=DEFAULT_REMOTE_DATA, help="Remote data directory containing data.db and workspaces.")
    parser.add_argument("--out", default="", help="Local output directory. Defaults to /tmp/production-image-audit-<timestamp>.")
    parser.add_argument("--max-items", type=int, default=0, help="Keep only the most recent N rows; 0 means all rows in window.")
    parser.add_argument("--cols", type=int, default=2, help="Comparison cards per sheet row.")
    parser.add_argument("--rows-per-sheet", type=int, default=2, help="Comparison card rows per sheet.")
    parser.add_argument("--pair-width", type=int, default=760, help="Width of one input/output card.")
    parser.add_argument("--pair-height", type=int, default=560, help="Height of one input/output card.")
    return parser.parse_args()


def safe_extract(tar_path: Path, destination: Path) -> None:
    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar.getmembers():
            target = destination / member.name
            if not target.resolve().is_relative_to(destination.resolve()):
                raise RuntimeError(f"unsafe tar member: {member.name}")
        tar.extractall(destination)


def main() -> int:
    args = parse_args()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out or f"/tmp/production-image-audit-{stamp}").expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    remote_out = f"/tmp/production-image-audit-{stamp}"
    cfg = {
        "hours": args.hours,
        "role": args.role,
        "remote_data_dir": args.remote_data_dir,
        "remote_out": remote_out,
        "max_items": args.max_items,
        "cols": args.cols,
        "rows_per_sheet": args.rows_per_sheet,
        "pair_width": args.pair_width,
        "pair_height": args.pair_height,
    }
    remote_script = REMOTE_SCRIPT.replace("__CFG_JSON__", json.dumps(cfg, ensure_ascii=False).replace("\\", "\\\\").replace('"', '\\"'))
    ssh_cmd = [
        "ssh",
        "-i",
        args.ssh_key,
        args.server,
        f"cd {shlex.quote(args.remote_backend)} && .venv/bin/python -",
    ]
    result = subprocess.run(ssh_cmd, input=remote_script, text=True, capture_output=True, check=True)
    print(result.stdout.strip())
    remote_tar = f"{remote_out}.tar.gz"
    local_tar = out_dir / "audit.tar.gz"
    subprocess.run(
        ["scp", "-i", args.ssh_key, f"{args.server}:{remote_tar}", str(local_tar)],
        check=True,
    )
    safe_extract(local_tar, out_dir)
    extracted = out_dir / Path(remote_out).name
    print(f"local_dir={extracted}")
    print(f"manifest={extracted / 'manifest.tsv'}")
    for sheet in sorted(extracted.glob("sheet_*.jpg")):
        print(f"sheet={sheet}")
    print(f"notes={extracted / 'audit_notes.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
