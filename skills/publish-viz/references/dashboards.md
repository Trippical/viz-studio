# Dashboards

A dashboard is one JSON file that places published charts on a 12-column
grid and adds filter controls. It holds no data.

## Start the file with the CLI

Never write a dashboard file from nothing: `author` must equal the identity
the CLI resolves, and the CLI stamps it for you.

- New dashboard: `viz new-dashboard sales/emea/overview --chart sales/emea/revenue --chart sales/emea/total-revenue --title "EMEA overview"`
  writes `.viz-staging/dashboards/sales/emea/overview.json` with one
  `w: 6, h: 4` tile per chart.
- Change a published dashboard: `viz pull-dashboard sales/emea/overview`
  copies it into staging with your identity and a new `updated_at`.

Both refuse to replace a staged file you may have edited. Add `--force` only
when you mean to discard the staged copy.

## The file

```json
{
  "schema_version": 1,
  "id": "sales/emea/overview",
  "title": "EMEA overview",
  "description": "Revenue and orders for EMEA. Markdown, optional.",
  "tags": ["sales"],
  "author": "stamped by the CLI",
  "created_at": "stamped by the CLI",
  "updated_at": "stamped by the CLI",
  "controls": [
    {"id": "period", "type": "date-range", "label": "Period", "column": "month", "default": {"last": "12m"}},
    {"id": "region", "type": "select", "label": "Region", "column": "region", "multi": true, "default": null},
    {"id": "revenue", "type": "number-range", "label": "Revenue", "column": "revenue", "default": null}
  ],
  "layout": [
    {"chart": "sales/emea/revenue", "w": 8, "h": 4},
    {"chart": "sales/emea/total-revenue", "w": 4, "h": 2},
    {"markdown": "Source: the finance warehouse, refreshed daily.", "w": 12, "h": 1}
  ]
}
```

Only edit `title`, `description`, `tags`, `controls` and `layout`.

## Controls

A control filters every chart on the page whose data has a column with the
control's `column` name. Charts without that column are not filtered. So
give the same thing the same column name in every chart's SQL (`month`,
`region`), and a control reaches all of them.

| `type` | Column type | `default` |
|---|---|---|
| `date-range` | `date` or `timestamp` | `null`, `{"last": "12m"}` (a number of `d`, `w`, `m` or `y`), or `{"from": "2025-01-01", "to": "2025-12-31"}` |
| `select` | any; options are the distinct values across the page's charts | `null`, one value, or a list of values; set `"multi": true` to allow several |
| `number-range` | `number` or `integer` | `null` or `{"min": 0, "max": 100}` |

`id` is a lowercase slug, unique on the page. `label` is what the viewer
reads. At most 20 controls; three or four is usually right.

For a filter on a category (region, channel, product), use a `select` with `"multi": true` and `"default": null`, so viewers start with everything and can narrow to one or several values.

## Layout

The grid has 12 columns. Each tile has a width `w` from 1 to 12 and a
height `h` from 1 to 12 in row units of 120 px. Tiles flow left to right and
wrap. Useful sizes: a main chart `w: 8, h: 4` beside a stat tile
`w: 4, h: 2`; two charts side by side at `w: 6, h: 4`; a full-width chart
`w: 12, h: 4`. A dashboard with a single chart uses `w: 12, h: 4`.

Markdown tiles (`{"markdown": "...", "w": 12, "h": 1}`) are for short notes:
the source, a definition, what to look at. Raw HTML is ignored; links must
be `https://`, `http://` or `mailto:`. At most 8 KB.

## Publish order

Publish every chart first; `viz validate` on a dashboard fails if a tile
names a chart that is not published. Then:

```
viz validate .viz-staging/dashboards/sales/emea/overview.json
viz publish .viz-staging/dashboards/sales/emea/overview.json
```

If the dashboard already exists, `viz publish` refuses and prints its
current author and `updated_at`. Tell the user and ask before adding
`--force`.

The published dashboard is at `/d/<id>` on the site, for example
`/d/sales/emea/overview`. A chart is at `/c/<id>`.
