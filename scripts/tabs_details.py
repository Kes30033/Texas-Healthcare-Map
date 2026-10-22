"""Fetch the TABS detail page of each candidate project: address, scope of work, square footage,
owner, tenant and design firm.

  python scripts/tabs_details.py PROJECT_NUMBERS.txt

Saves one JSON file per project in data/tabs/details/ and skips projects already saved.
"""
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "tabs" / "details"
PAGE = "https://www.tdlr.texas.gov/TABS/Search/Project/{}"
UA = "Mozilla/5.0 (compatible; Texas-Healthcare-Map; github.com/Kes30033/Texas-Healthcare-Map)"
SECTIONS = {"project-details-project": "", "project-details-owner": "Owner ", "project-details-tenant": "Tenant ",
            "project-details-designer": "Design Firm ", "project-details-contact": "Filer "}


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def parse(page):
    """Label -> value for every <dt>/<dd> pair; an address spans two <dd> lines, joined with ', '."""
    out = {}
    for cls, prefix in SECTIONS.items():
        m = re.search(rf'<div class="{cls}">(.*?)</div><!--/\.{cls}-->', page, re.S)
        if not m:
            continue
        label = None
        for tag, body in re.findall(r"<(dt|dd)[^>]*>(.*?)</\1>", m[1], re.S):
            if tag == "dt":
                label = text(body).rstrip(":")
                if prefix and not label.startswith(prefix):   # "Contact Name" -> "Owner Contact Name"
                    label = prefix + label
            elif label:
                out[label] = f"{out[label]}, {text(body)}" if label in out else text(body)
    m = re.search(r"Registration Date:\s*([\d/]+)", page)
    if m:
        out["Registration Date"] = m[1]
    return out


def fetch(num, tries=4):
    for t in range(tries):
        try:
            req = urllib.request.Request(PAGE.format(num), headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            print("  retry", num, t + 1, e, flush=True)
            time.sleep(5 * (t + 1))
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    nums = [n.strip() for n in open(sys.argv[1], encoding="utf-8") if n.strip()]
    todo = [n for n in nums if not (OUT / f"{n}.json").exists()]
    print(f"{len(nums)} projects, {len(todo)} to fetch", flush=True)
    for i, num in enumerate(todo):
        page = fetch(num)
        if page and "Project Number:" in page:
            (OUT / f"{num}.json").write_text(json.dumps(parse(page), indent=1), encoding="utf-8")
        else:
            print("  no detail page for", num, flush=True)
        if i % 50 == 49:
            print(f"  {i + 1}/{len(todo)}", flush=True)
        time.sleep(0.4)


if __name__ == "__main__":
    main()
