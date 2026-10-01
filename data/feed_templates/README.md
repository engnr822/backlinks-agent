# Bulk feed templates

One file per platform, containing **only that platform's header row** —
copied from the template the platform gives you, exactly as it wrote it.
`citation_feeds.py --template <name>` reads the header and fills a CSV that
matches it column for column.

## Where each template comes from

| File | Platform | Where to get the header row |
|---|---|---|
| `bing_places.txt` | Bing Places for Business | Dashboard → Manage locations → **Bulk upload** → *Download template*. Handles up to 10,000 locations. |
| `apple_business.txt` | Apple Business Connect | Business Connect → Locations → **Add multiple locations** → download the feed template. |
| `yext.txt` / `uberall.txt` | Aggregators | Their import screen offers a sample CSV. |

`bing_places.txt.example` shows the shape of one of these files. It is
deliberately `.example` and not the real thing — the mapper would happily fill
a header row nobody at Bing ever wrote, and the upload would fail or, worse,
land wrong data. Replace it with the real header before using it.

## How

1. Download the platform's template.
2. Open it, copy the **first line only**.
3. Save it here as `<name>.txt`.
4. `python citation_feeds.py --template <name>`
5. Upload `feeds/<name>.csv`.

Any column the mapper doesn't recognise is left blank and printed, so you
know exactly what still needs a human. Nothing is guessed — a made-up value
in a citation is worse than an empty cell.
