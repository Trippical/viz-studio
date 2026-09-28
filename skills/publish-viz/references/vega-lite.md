# Writing Vega-Lite for viz-site

viz-site renders every chart with Vega-Lite v6, except headline numbers,
which use the site's own `stat` tile (see the end of this file). You write
only the `spec` part of `chart.json`. The site injects the rows.

## The skeleton

```json
{
  "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
  "data": {"name": "data"},
  "mark": "bar",
  "encoding": {
    "x": {"field": "region", "type": "nominal", "title": "Region"},
    "y": {"field": "revenue", "aggregate": "sum", "type": "quantitative", "title": "Revenue"}
  }
}
```

Every `field` must be a column declared in `data.columns` of the same
`chart.json`, or a field created by a transform in the spec.

## Rules that fail validation

`viz validate` rejects the chart, and the browser refuses to draw it, if the
spec breaks any of these:

- `data` is exactly `{"name": "data"}`. Any `data` key anywhere else in the
  spec, including inside a layer, must also be exactly `{"name": "data"}`.
- No `values`, `url`, `datasets`, `href` or `usermeta` key anywhere. There
  is no way to put data in the spec, load a file, or make a mark a link.
- No `image` marks.

Expressions (`calculate`, `filter`, conditional encodings) are allowed. The
site runs them in a sandboxed interpreter, not with `eval`.

## Sizing

Do not set `width` or `height` on a single chart or a layered chart. The
site sizes the chart to its dashboard tile.

Faceted and repeated charts (`facet`, `repeat`, `concat`) are the exception:
the tile cannot size each panel, so set a numeric `width` and `height` for
one panel. A half-width tile (`"w": 6`) is about 560 px wide and a row unit
(`"h": 1`) is 120 px, so two columns of `"width": 200, "height": 80` fit a
`w: 6, h: 3` tile. Also add `"autosize": {"type": "pad", "resize": true}` to a faceted, repeated or concatenated chart, or its canvas keeps the size it had before the rows arrived (see `examples/small-multiples.json`).

## Dates: always use UTC time units

`date` columns arrive as `"2025-10-01"` strings, which Vega-Lite reads as
midnight UTC. A local time unit such as `yearmonth` would move that value to
30 September for anyone west of UTC. Always use the `utc` variants:
`utcyear`, `utcyearmonth`, `utcmonth`, `utcyearmonthdate`. Put the same
`timeUnit` on the tooltip field. Use `"type": "temporal"` for a continuous
time axis and `"type": "ordinal"` for discrete periods (years as bars,
months of the year as heatmap columns). For data that is already one row per week or per day, use `utcyearmonthdate`, so each point keeps the date the period starts on.

## Aggregate in the encoding, not only in SQL

Dashboard filters remove rows before the chart sees them. If the SQL
already returns one row per month and region, still write
`"aggregate": "sum"` on the measure when the chart does not split by every
column; then a total over regions stays correct when the viewer filters to
two regions. Use `sum` for additive measures, `mean` only for measures that
are averages of equal-weight rows.

## Formats

Numbers use d3-format strings in `axis.format`, `legend.format` and tooltip
`format`:

| Format | Shows |
|---|---|
| `",.0f"` | 12,345 |
| `"$,.0f"` | $12,345 |
| `"$.2s"` | $12k, $1.2M (short axis labels) |
| `".1%"` | 12.3% (for values between 0 and 1) |
| `".0%"` | 12% |

`s` formats use SI prefixes, so a billion shows as `G`, not `B`. Use them on
axes, and full `"$,.0f"` numbers in tooltips.

Axis and legend formats must end in a type letter (`f`, `s`, `%`). A bare `","` on an axis lets Vega choose its own precision and prints `4.5e+4`.

## Tooltips

Always add a `tooltip` list: every field a viewer would ask about, each with
a `title` and a `format`. Tooltips are the only way to read exact values.

## Colour

Leave the default colour scheme for categories. For one measure shown as
colour (heatmaps), use a single-hue scheme such as `"scale": {"scheme":
"blues"}`. Keep categories to about eight; group the rest into `Other` in
the SQL. Give a series the same field and colour on every chart of a
dashboard so it keeps its colour.

## Pick the form from the question

Start from the closest example and change the fields. Each example binds the
columns `month` (date), `region` (string), `revenue` (number) and `orders`
(integer).

When a question fits both a line and a grouped bar ("weekly orders by channel"), use the line for six or more periods and the grouped bar for fewer, where comparing categories inside each period is the point.

| The question | Form | Example file |
|---|---|---|
| How did a measure change over time, per category? | Line | `examples/line-by-category.json` |
| Which category is biggest? | Sorted horizontal bar | `examples/bar-ranking.json` |
| How did the total change, and what made it up? | Stacked area | `examples/stacked-area.json` |
| How did the mix between categories shift? | 100% stacked bar | `examples/stacked-bar-share.json` |
| How do categories compare within each period? | Grouped bar | `examples/grouped-bar.json` |
| Do two measures move together? | Scatter | `examples/scatter.json` |
| Where are the highs and lows across two categories? | Heatmap | `examples/heatmap.json` |
| How are values spread out? | Histogram | `examples/histogram.json` |
| Is the value above or below a target? | Line with reference line | `examples/line-with-target.json` |
| Same chart for each category, compared | Small multiples | `examples/small-multiples.json` |
| What is the one headline number? | Stat tile | `examples/kpi-stat.json` |

Reference lines and labels (`examples/line-with-target.json`) use `datum`
for the fixed value and aggregate their layer to one row, so they draw once.
They cannot use `values` for this.

## Do not

- Do not put two measures with different units on one chart with two y
  axes. Make two charts.
- Do not use pie or donut charts for more than three slices. Use a sorted
  bar.
- Do not plot thousands of individual points or bars when a GROUP BY would
  answer the question.
- Do not set `width` or `height` on a single chart.
- Do not use local time units on date fields.

## The stat tile

For a single headline number set `"renderer": "stat"` and this `spec`:

```json
{"value": "revenue", "agg": "sum", "format": "$,.0f", "compare": {"column": "orders", "agg": "sum"}}
```

`value` and `compare.column` are declared columns. `agg` is one of `sum`,
`avg`, `min`, `max`, `count`, `last`. `format` is a d3-format string.
`compare` is optional and shows a second, smaller number under the first.
