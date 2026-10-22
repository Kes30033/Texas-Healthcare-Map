"""Pick the TABS search results that could be active construction, for scripts/tabs_details.py.

  python scripts/tabs_candidates.py      -> data/tabs/candidates.txt (one project number per line)

Keeps projects that aren't closed or inspected and whose estimated completion is no more than
WINDOW_DAYS in the past (projects often run past the date in their filing).
"""
import datetime
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEARCH = ROOT / "data" / "tabs" / "search"
TODAY = datetime.date.today()
WINDOW_DAYS = 150
DONE = {3001, 3007}   # Inspection Complete, Project Closed
STATUS = {3001: "Inspection completed", 3002: "Inspection in process", 3003: "Inspection scheduled",
          3004: "Preliminary plan review", 3005: "Miscellaneous", 3006: "Preliminary review pending",
          3007: "Project closed", 3008: "Project registered", 3009: "Plan review complete", 3010: "Plan review pending"}
WORK = {9001: "New construction", 9002: "Renovation/alteration", 9003: "Addition to existing building",
        9004: "Historic preservation", 9005: "Public right of way"}


def load_search():
    """ProjectNumber -> search row (with the list of queries that found it)."""
    rows = {}
    for f in sorted(SEARCH.glob("*.jsonl")):
        for line in open(f, encoding="utf-8"):
            r = json.loads(line)
            rec = rows.setdefault(r["ProjectNumber"], dict(r, queries=set()))
            rec["queries"].add(r.pop("query", f.stem))
    return rows


def active(r):
    if r["ProjectStatus"] in DONE or r["TypeOfWork"] == 9005:
        return False
    end = (r.get("EstimatedEndDate") or "")[:10]
    return not end or end >= (TODAY - datetime.timedelta(days=WINDOW_DAYS)).isoformat()


# Keyword searches ("Baptist", "Methodist", "health"...) also find churches, schools and gyms; projects
# found by searching a facility's own street address are kept regardless.
MEDICAL = re.compile(r"hospital|medical|med ctr|surg|health|clinic|emergency|\bE\.?R\.?\b|\bASC\b|patient|\bN?ICU\b|"
                     r"\bcath|\bOR\b|operating|imaging|radiolog|\bMRI\b|\bCT\b|oncolog|cancer|cardi|heart|ortho|spine|"
                     r"endoscop|infusion|pharmacy|lab\b|laborator|\bMOB\b|tower|pavilion|campus|nurs|L&D|labor and|"
                     r"maternity|women|neonat|pediatric|children|trauma|sterile|\bSPD\b|dialysis|wound|sleep|"
                     r"physician|doctor|care|wellness|chw|bed|unit|floor|level|wing|methodist|hermann|baylor|scott & white|"
                     r"christus|texas health|medical city|st\.? david|seton|ascension|covenant|parkland|\bJPS\b|UTMB|"
                     r"UTSW|southwestern|anderson|harris health|hendrick|providence|driscoll|\bDHR\b|knapp|spohn|"
                     r"urolog|vascular|gastro|dermatolog|ophthalm|\beye\b|\bENT\b|neuro|\bpain\b|bariatric|"
                     r"hospital district|university medical", re.I)
NOT_MEDICAL = re.compile(r"church|chapel|fellowship|ministr|parish|worship|sanctuary|"
                         r"united methodist|baptist church|\bISD\b|elementary|middle school|high school|preschool|"
                         r"academy|daycare|day care|childcare|kindergarten|apartment|residences|senior living|"
                         r"assisted living|memory care|animal|veterinar|\bvet\b|\bpets?\b(?!/| ?ct| scan)|kennel|equine|dental|dentist|"
                         r"orthodont|fitness|gym\b|restaurant|retail|bank\b|hotel|car wash|warehouse|storage", re.I)


def relevant(r):
    if any(not q.split(":")[0] in FIELDS for q in r["queries"]):   # found at a facility's address
        return True
    text = f'{r["ProjectName"]} | {r["FacilityName"]}'
    return bool(MEDICAL.search(text)) and not NOT_MEDICAL.search(text)


FIELDS = {"FacilityName", "ProjectName", "OwnerName"}


def main():
    rows = load_search()
    keep = sorted(n for n, r in rows.items() if active(r) and relevant(r))
    (ROOT / "data" / "tabs" / "candidates.txt").write_text("\n".join(keep) + "\n", encoding="utf-8")
    print(f"{len(rows)} projects found, {len(keep)} possibly active")
    print(Counter(STATUS.get(rows[n]["ProjectStatus"]) for n in keep))
    print(Counter(WORK.get(rows[n]["TypeOfWork"]) for n in keep))


if __name__ == "__main__":
    main()
