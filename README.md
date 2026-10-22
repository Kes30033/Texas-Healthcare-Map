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
- **Search** by name, city, county, ZIP code, project name or owner.
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
| Construction projects | [TDLR Texas Architectural Barriers (TABS) project registry](https://www.tdlr.texas.gov/TABS/Search). Texas requires every building project costing $50,000 or more to be registered there before construction, with owner, design firm, address, estimated cost, type of work, scope and estimated start and completion dates |
| Announced projects and project details | News reports and health system announcements, listed with links in [data/research/news_projects.csv](data/research/news_projects.csv) |
| Map positions | U.S. Census geocoder, then OpenStreetMap Nominatim; hospital positions are checked against OpenStreetMap |
| Counties, highways (Simple map) | U.S. Census Bureau cartographic boundary and TIGER files |
| Street and satellite maps | Esri World Street Map and World Imagery |

## How projects are classified

1. **Found**: TABS was searched by the street address of every facility and by hospital and surgery words
   ("hospital", "surgery center", "ASC", "patient tower"...) and health system names, for filings since 2021.
2. **Active**: the filing isn't closed or inspected, and its estimated completion is no more than 150 days past
   (projects often run past the date in their filing).
3. **Linked to a facility** when the filing's address is the facility's street address, or it's within 600 m and
   shares a distinctive name, or it's within 150 m of a hospital and is medical work. Surgery centers also need
   surgery-related wording, since they share buildings with other tenants.
4. **Kind**: *New* (a hospital or surgery center that isn't open yet, including build-outs of new ASCs inside existing
   buildings), *Expansion* (new construction or an addition at an existing facility) or *Renovation* (work inside one).
5. **Stage**: *Filed, not started* when the filing's estimated start date is still ahead; *Under construction* when
   it has passed; *Announced* for projects found only in the news.

Filings that were found but left off the map are listed with the reason in [data/review.csv](data/review.csv)
(for example psychiatric, rehab and long-term care hospitals, clinics, medical office buildings and animal hospitals).

### Things to know

- **Dates in filings are estimates** made when the project was registered. A project marked "under construction"
  may have slipped, and some marked "filed" may have started early.
- **Costs are the filer's estimate** of construction cost, not the total project budget news reports often quote.
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
  research/news_projects.csv   news-researched projects and sources
  raw/                      CMS downloads (Texas rows)
  tabs/search/              TABS search results; tabs/details/: one file per filing
  geocode/                  map positions, saved by address
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
python scripts/build_projects.py             # classify, link and place every project
python scripts/build_site.py                 # website in docs/ and the spreadsheet
```

The TABS searches remember finished queries (`data/tabs/search/*.done`); delete those files to search again
from scratch. `python scripts/suggest_news_matches.py` lists TABS filings that may match the news projects in
data/research/news_projects.csv, so their filing numbers can be added to its `tabs` column.
