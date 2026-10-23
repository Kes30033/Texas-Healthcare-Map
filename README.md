# Texas Hospital & Surgery Center Construction Map

An interactive map of every acute care hospital and ambulatory surgery center (ASC) in Texas, and the
construction at each one: renovations and expansions, projects under construction, and new hospitals and
surgery centers that are filed with the state or announced but haven't broken ground.

- **Website:** https://kes30033.github.io/Texas-Healthcare-Map/
- **Spreadsheet:** [data/Texas_Hospital_Construction.xlsx](data/Texas_Hospital_Construction.xlsx) (click it, then "Download raw file").
  Sheets: every project, every facility with its project totals, and notes on sources.

## What you can do on the website

- **Quick views** (top of the panel):
  - **Renovating / expanding**: existing hospitals and surgery centers with an active renovation, addition or new building.
  - **Under construction**: every project whose filed start date has passed, at existing facilities and new ones.
  - **In the works**: new hospitals and surgery centers that aren't under construction yet, either filed with the
    state (permits filed, design firm under contract) or announced in the news.
  - **Everything**: all facilities, with rings on the ones that have projects.
- **Filters** for facility type, construction stage, kind of project and minimum project cost.
- **Search** for a hospital or surgery center, a **health system** (Baylor Scott & White, HCA, Texas Health
  Resources, Memorial Hermann, CHRISTUS...), an **architect**, a **builder**, a project **owner**, or a city,
  county or ZIP code. Suggestions appear as you type, grouped by kind; picking an architect, builder or owner
  shows only that firm's projects. Names in a project's details (owner, architect, builder, health system) are
  links that run the same search.
- Click any place for its details and every project there: cost, estimated start and finish, square footage,
  owner, architect, builder (when reported), a link to the state filing and news sources.
- **Download this list (CSV)** saves what's in the list with your filters.
- Map styles: Streets, Satellite and Simple (top-left of the map).

### How to read the map

| Mark | Meaning |
|---|---|
| Blue dot | Hospital (acute care, critical access, children's, VA, military) |
| Green dot | Ambulatory surgery center |
| Orange ring | Has a project under construction |
| Purple ring | Has a project filed with the state that hasn't started |
| Dashed gold ring | Has a project announced in the news, with no state filing yet |
| White circle with a colored center | A new hospital or surgery center that isn't open yet (ring color = its stage) |

## Where the data comes from

| What | Source |
|---|---|
| Hospitals | [CMS Provider of Services file](https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/provider-of-services-file-hospital-non-hospital-facilities) (every Medicare-certified short-term acute care, critical access and children's hospital active in the latest quarter), plus VA and military hospitals from [CMS Care Compare](https://data.cms.gov/provider-data/dataset/xubh-q36u) |
| Hospital campuses | CMS lists some multi-campus hospitals under one number and one address (for example Methodist Hospital in San Antonio, Memorial Hermann, Baptist, CHRISTUS Spohn). Their other campuses are added from [OpenStreetMap](https://www.openstreetmap.org/copyright) and listed in [data/campuses.csv](data/campuses.csv) |
| Surgery centers | [CMS Provider of Services file, iQIES](https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/provider-of-services-file-internet-quality-improvement-and-evaluation-system) (every certified ASC) |
| Corrections | [data/facility_fixes.csv](data/facility_fixes.csv): CMS records checked by hand, each with its source: out-of-date addresses, legal names in place of the names hospitals use, positions geocoders can't find, and hospitals that have closed but are still listed |
| Construction projects | [TDLR Texas Architectural Barriers (TABS) project registry](https://www.tdlr.texas.gov/TABS/Search). Texas requires every building project costing $50,000 or more to be registered there before construction, with owner, design firm, address, estimated cost, type of work, scope and estimated start and completion dates |
| Announced projects and project details | News reports and health system announcements, listed with links in [data/research/news_projects.csv](data/research/news_projects.csv) |
| Map positions | OpenStreetMap buildings and address points (Nominatim), the U.S. Census geocoder and OpenStreetMap hospitals; see [How dots are placed](#how-dots-are-placed) |
| Counties, highways (Simple map) | U.S. Census Bureau cartographic boundary and TIGER files |
| Street and satellite maps | Esri World Street Map and World Imagery |

## How dots are placed

Each facility's dot comes from the first of these that has it:

1. **Pinned**: hospital campuses from OpenStreetMap, and the hand-checked positions in data/facility_fixes.csv.
2. **The building**: OpenStreetMap's building or address point for the street address (same house number on the same
   street, in the same town), found with Nominatim or Photon.
3. **The street address**: the U.S. Census geocoder. Its answers are thrown out when it had to change the address to match it,
   such as a different street, the opposite direction ("2000 N Mays" for "2000 S Mays", "Loop 1604 E" for "Loop 1604 W")
   or a different street type ("Houston Hwy" for "Houston St").
4. **OpenStreetMap** found by the address or by the facility's name.
5. **Approximate**: a similar street the Census geocoder matched, the middle of the street, or the center of the ZIP code.
   These dots say so in their details, and the spreadsheet's "Map position" column says where every dot came from.

Hospitals are also checked against OpenStreetMap's hospitals: when OpenStreetMap has the same hospital (same name and street
number, or the same distinctive name in the same city) more than 150 m from the dot, the dot moves to it. A facility's county
is the county its dot is in when that's clearly a different county than CMS lists. New hospitals and surgery centers are placed
from their state filing's address, or from news reports; "X Rd & Y Rd" or an area named in the news counts as approximate.

## How projects are classified

1. **Found**: TABS was searched by the street address of every facility and by hospital and surgery words
   ("hospital", "surgery center", "ASC", "patient tower"...) and health system names, for filings since 2021.
2. **Active**: the filing isn't closed or inspected, and its estimated completion is no more than 150 days past
   (projects often run past the date in their filing).
3. **Linked to a facility** when the filing's address is the facility's street address, or it's within 600 m and
   shares a distinctive name, or it's within 250 m of a hospital (or on its block of the same street) and is medical work
   for the hospital itself: a neighbor's filing doesn't count when its owner or tenant is someone else, such as a
   clinic in a medical office building next door. Surgery centers also need surgery-related wording, since they share
   buildings with other tenants. Street and neighborhood names ("Fannin", "Sonterra") don't count as shared names.
   A project registered twice (same name, address and about the same cost) counts once.
4. **Kind**: *New* (a hospital or surgery center that isn't open yet, including build-outs of new ASCs inside existing
   buildings), *Expansion* (new construction or an addition at an existing facility) or *Renovation* (work inside one).
5. **Stage**: *Filed, not started* when the filing's estimated start date is still ahead; *Under construction* when
   it has passed; *Announced* for projects found only in the news.

Filings that were found but left off the map are listed with the reason in [data/review.csv](data/review.csv)
(for example psychiatric, rehab and long-term care hospitals, clinics, medical office buildings and animal hospitals).

### Things to know

- **Dates in filings are estimates** made when the project was registered. A project marked "under construction"
  may have slipped, and some marked "filed" may have started early. A filing can also stay open after a project
  stops: the Wadley Regional replacement hospital in Texarkana, halted in 2024, is left off for that reason
  (data/research/news_projects.csv marks such projects "skip").
- **CMS lists lag behind closures and sales.** Hospitals were checked in October 2026 against news reports: closed
  hospitals CMS still lists, stale OpenStreetMap campuses and legal names are corrected in data/facility_fixes.csv
  and data/campuses.csv. Surgery centers weren't checked one by one.
- **Costs are the filer's estimate** of construction cost, not the total project budget news reports often quote.
- **Builders aren't in state filings.** TABS lists the owner and the architect but not the contractor, so builders
  come only from news reports and contractor announcements (in data/research/news_projects.csv) and cover a
  handful of the largest projects.
- **Health systems are matched by name** (and by town, for names like "Methodist" that several systems use), so a
  facility whose name doesn't show its system may be missing from that system's list.
- **Federal projects** (VA, military) don't file with TDLR, so they appear only if reported in the news.
- **Medical office buildings and clinics on hospital campuses** count as hospital projects when they're on the
  hospital's address or right next to it.
- **Facility lists cover Medicare-certified facilities.** A hospital or surgery center licensed by Texas but not
  certified by Medicare isn't included unless it's one of the campuses in data/campuses.csv.
- Psychiatric, rehabilitation and long-term acute care hospitals, and freestanding emergency rooms, are left out
  on purpose; small-format "emergency hospitals" that are licensed as general hospitals are included.

## What's in this repository

```
docs/                       the website (published by GitHub Pages)
data/
  Texas_Hospital_Construction.xlsx   the spreadsheet
  facilities.csv            every facility (CMS + campuses)
  projects.csv              every project shown on the map
  review.csv                filings found but left off, with the reason
  campuses.csv              hospital campuses added from OpenStreetMap
  facility_fixes.csv        hand-checked corrections to CMS records, with sources
  research/news_projects.csv   news-researched projects and sources
  raw/                      CMS downloads (Texas rows)
  tabs/search/              TABS search results; tabs/details/: one file per filing
  geocode/                  map positions, saved by address (cache.json: geocoders; osm_address.json: OpenStreetMap buildings)
  osm/hospitals.json        Texas hospitals from OpenStreetMap
  basemap/basemap.json      counties and highways for the Simple map
scripts/                    the steps that build everything (below)
site/index.template.html    the website's page, before data is added
```

## Updating the data

Needs Python 3.10+ and `pip install -r requirements.txt`. Run from the repository folder:

```
python scripts/download_cms.py               # ~1 min: newest CMS hospital and ASC files
python scripts/build_facilities.py data/raw  # facility list (+ campuses)
python scripts/tabs_harvest.py keywords FacilityName   # TABS searches; each takes a while and can run side by side
python scripts/tabs_harvest.py keywords ProjectName
python scripts/tabs_harvest.py addresses
python scripts/tabs_candidates.py            # which filings could be active
python scripts/tabs_details.py data/tabs/candidates.txt   # detail page of each (skips ones already saved)
python scripts/build_projects.py             # place facilities, classify and link every project (new addresses
                                             # wait on OpenStreetMap's one-request-a-second limit; answers are saved)
python scripts/build_site.py                 # website in docs/ and the spreadsheet
```

The TABS searches remember finished queries (`data/tabs/search/*.done`); delete those files to search again
from scratch. `python scripts/suggest_news_matches.py` lists TABS filings that may match the news projects in
data/research/news_projects.csv, so their filing numbers can be added to its `tabs` column. A row's `builder`
is credited to the first filing in `tabs` only, unless `builder_tabs` lists the filings the builder's source covers.
