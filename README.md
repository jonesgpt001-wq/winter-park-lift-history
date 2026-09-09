# Winter Park Lift History

Hourly tracking of every Winter Park Resort lift's open/closed status, with a spotlight on Panoramic Express ("Pano") so you can tell after a storm day whether Parsenn Bowl opened or the powder is still sitting there.

**Live site:** https://jonesgpt001-wq.github.io/winter-park-lift-history/

## How it works

- `update.py` fetches the resort's official status feed (the same JSON that powers the mountain report on winterparkresort.com), appends one snapshot per hour to `data/history.jsonl`, and regenerates `index.html`.
- The site shows: Pano's current status and last-observed-open time, a day-by-day Pano table next to 24h new snow, every lift's current status by territory, and a log of status changes.
- Lift statuses are the resort's reported values (observation). Any "powder read" on the page is labeled inference.

## Editing

`index.html` is a self-contained static page - edit and commit, GitHub Pages republishes automatically. `data/history.jsonl` is the raw record: one JSON snapshot per line.

## Notes

- One snapshot per hour; a lift that opens and closes between checks can be missed.
- Snow numbers come from the resort's snow report (base/mid/summit stations), shown as reported.
