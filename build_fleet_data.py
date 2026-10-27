"""Vetting_Test_Data_v1/data/*.csv + data/arrivals.csv -> fleet-data.js (window.FLEET)

index.html loads fleet-data.js with a <script> tag so the app keeps working when
opened straight from disk (fetching CSVs is blocked on file://).

data/arrivals.csv is the arrival schedule submitted by suppliers (one row per port call).
If it does not exist, a synthetic sample is generated from the vessel list (ETAs spread
over the next 45 days) so the app can be tried out; replace it with real submissions.

Usage (from the project root):  python tools/build_fleet_data.py [data_dir]
"""
import csv, json, sys, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "Vetting_Test_Data_v1" / "data"
ARRIVALS = ROOT / "data" / "arrivals.csv"
ARR_FIELDS = ["arrival_id", "imo", "vessel_name", "eta", "berth", "cargo", "supplier", "agent", "submitted_at", "synthetic"]
# must match the <option> text of the review form's 입항 부두 / 작업 구분 selects
RAW_CARGO = ["원료 양하 – 철광석", "원료 양하 – 석탄"]
PRODUCT_CARGO = ["제품 적하 – 열연/냉연 코일", "제품 적하 – 후판", "제품 적하 – 형강/철근"]
AGENTS = ["Dangjin Marine Agency", "Seohae Shipping Agency", "Korea Port Services"]   # fictional
IMG_DIR = "Vetting_Test_Data_v1/images/"   # relative to index.html
NUM = {"dwt", "built_year", "duration_hours", "deficiencies", "risk_score", "age_factor", "vetting_factor", "psc_factor"}
BOOL = {"repeat_finding", "synthetic"}


def norm_imo(v):
    """'9300015.0' (Excel export), ' IMO 9300015 ' -> '9300015'"""
    v = (v or "").strip().upper().removeprefix("IMO").strip()
    return v[:-2] if v.endswith(".0") else v


def to_num(v):
    """'65,000' -> 65000; '', 'N/A', '-' -> None"""
    try:
        n = float(v.replace(",", ""))
    except ValueError:
        return None
    return int(n) if n.is_integer() else n


def load(name):
    with open(DATA / f"{name}.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k, v in r.items():
            v = (v or "").strip()
            if k in NUM:
                v = to_num(v)
            elif k in BOOL:
                v = v.lower() == "true"
            elif k == "imo":
                v = norm_imo(v)
            r[k] = v
    return rows


def sample_arrivals(vessels):
    today = datetime.date.today()
    rows = []
    for v in vessels:
        if not v["imo"].isdigit():
            continue
        n = int(v["imo"])
        eta = today + datetime.timedelta(days=1 + (n * 7919) % 45)
        raw = (v["dwt"] or 0) >= 65000
        rows.append({
            "arrival_id": f"ARR-{eta:%Y%m%d}-{v['imo']}", "imo": v["imo"], "vessel_name": v["vessel_name"],
            "eta": eta.isoformat(), "berth": "당진 원료부두" if raw else "당진 제품부두",
            "cargo": (RAW_CARGO if raw else PRODUCT_CARGO)[n % (2 if raw else 3)],
            "supplier": v["operator"], "agent": AGENTS[n % len(AGENTS)],
            "submitted_at": (eta - datetime.timedelta(days=10)).isoformat(), "synthetic": "True"})
    rows.sort(key=lambda r: r["eta"])
    ARRIVALS.parent.mkdir(exist_ok=True)
    with open(ARRIVALS, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ARR_FIELDS)
        w.writeheader(); w.writerows(rows)
    print(f"{ARRIVALS.relative_to(ROOT)} not found - wrote {len(rows)} synthetic arrivals")


def load_arrivals():
    """Validate supplier rows; bad rows are skipped with a message rather than reaching the app."""
    with open(ARRIVALS, encoding="utf-8-sig", newline="") as f:
        raw = [{k: (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(f)]
    rows, seen, no_id = [], set(), 0
    for line, r in enumerate(raw, start=2):
        r["imo"] = norm_imo(r.get("imo"))
        if not r["imo"]:
            print(f"skip {ARRIVALS.name}:{line}: missing imo"); continue
        try:   # the app does date math on ETA; only ISO dates (YYYY-MM-DD) are safe
            r["eta"] = datetime.date.fromisoformat(r.get("eta", "")).isoformat()
        except ValueError:
            print(f"skip {ARRIVALS.name}:{line}: invalid eta {r.get('eta')!r} (use YYYY-MM-DD)"); continue
        if r.get("submitted_at"):
            try:
                r["submitted_at"] = datetime.date.fromisoformat(r["submitted_at"]).isoformat()
            except ValueError:
                print(f"warning {ARRIVALS.name}:{line}: invalid submitted_at {r['submitted_at']!r} - cleared"); r["submitted_at"] = ""
        if not r.get("arrival_id"):
            # review records are linked by arrival_id; one derived from the ETA breaks if the ETA is resubmitted
            no_id += 1
            r["arrival_id"] = f"ARR-{r['eta'].replace('-', '')}-{r['imo']}"
        if r["arrival_id"] in seen:
            print(f"skip {ARRIVALS.name}:{line}: duplicate arrival_id {r['arrival_id']}"); continue
        seen.add(r["arrival_id"])
        r["synthetic"] = r.get("synthetic", "").lower() == "true"
        r.setdefault("vessel_name", "")
        rows.append(r)
    if no_id:
        print(f"warning: {no_id} arrivals have no arrival_id - generated from IMO+ETA; "
              "give each port call a fixed arrival_id so an ETA change keeps its review")
    return rows


def main():
    findings = load("findings")
    actions = {a["finding_id"]: a for a in load("corrective_actions")}
    for f in findings:
        a = actions.get(f["finding_id"])
        f["action"] = {k: a[k] for k in ("corrective_action", "owner", "target_date", "status")} if a else None
    images = load("image_metadata")
    for i in images:
        i["src"] = IMG_DIR + i["filename"]
    vessels = load("vessels")
    if not ARRIVALS.exists():
        sample_arrivals(vessels)
    arrivals = load_arrivals()
    known = {v["imo"] for v in vessels}
    unknown = [a["imo"] for a in arrivals if a["imo"] not in known]
    if unknown:
        print(f"warning: {len(unknown)} arrivals reference IMOs not in vessels.csv: {', '.join(unknown[:10])}")
    fleet = {
        "source": DATA.parent.name,
        "generatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
        "arrivals": arrivals,
        "vessels": vessels,
        "risk": load("risk_scores"),
        "inspections": load("inspections"),
        "findings": findings,
        "psc": load("psc"),
        "certificates": load("certificates"),
        "incidents": load("incidents"),
        "images": images,
    }
    out = ROOT / "fleet-data.js"
    out.write_text("/* generated by tools/build_fleet_data.py - do not edit */\nwindow.FLEET = "
                   + json.dumps(fleet, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"{out.name}: " + ", ".join(f"{k} {len(v)}" for k, v in fleet.items() if isinstance(v, list)))


if __name__ == "__main__":
    main()
