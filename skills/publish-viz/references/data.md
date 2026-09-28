# Data: SQL, lanes and safety

## Write the SQL for the chart

- Aggregate in the warehouse. `GROUP BY` month and region and return
  hundreds of rows, not millions. The chart gets faster and less raw data
  is shared.
- Select only the columns the chart and the dashboard's controls need.
- Name every column with letters, digits and underscores, starting with a
  letter: `AS revenue`, `AS order_count`. Other names fail staging.
- Return dates as `DATE` values and timestamps as `TIMESTAMP` values, not
  strings, so the column is typed `date` or `timestamp` and date controls
  work.
- Keep a category to about eight values; fold the rest into `'Other'`.
- Never select identifiers or free text (emails, names, phone numbers,
  account ids, comments, addresses) unless the user asked for that column by
  name. `viz query` and `viz stage` warn when a column name looks like
  personal data; drop it with `--drop-columns a,b` unless the user asked for
  it.

`viz stage --from <file>` publishes the file as it is. If a file has more rows than the chart draws (for example one row per order), aggregate it before staging so it has one row per point on the chart, and tell the user you did.

## Lanes

The CLI picks the lane from the result size:

| Lane | File | Limit | When |
|---|---|---|---|
| small | `data.json` | 100,000 rows and 20 MB | Almost always. Filters run in the browser. |
| large | `data.parquet` | 200 MB | Only when viewers must filter row-level data that the warehouse cannot pre-aggregate. |

A large-lane chart shares every row with every viewer. `viz validate` and
`viz publish` refuse it unless you pass `--allow-row-level`. Pass it only
after the user has agreed that the row-level data may be shared. Usually the
right fix is a `GROUP BY` that brings the result into the small lane.

## The large-lane aggregate

A large-lane chart needs an `aggregate`: one DuckDB `SELECT` over a table
named `data` that reduces the rows to something drawable. The browser runs
it after applying the dashboard's filters. Example:

```sql
SELECT day, sum(amount) AS amount FROM data GROUP BY day ORDER BY day
```

Rules:

- One `SELECT` statement over `data`. Do not read files or other tables.
- Do not define a CTE named `data`; the site defines `data` itself.
- Name every output column exactly like a declared column (`sum(amount) AS
  amount`), so the spec and the controls can bind to it.
- The browser returns at most 50,000 result rows.

## source: keep it when there is SQL

`viz query` writes a `source` block with the SQL, which lets the chart be
refreshed later and shows readers where the numbers came from. Never delete
it. Use `viz stage --from <file>` only for data that did not come from a
query you ran; those charts are marked static.

## Safety facts

- The deny-list (`VIZ_QUERY_DENY`) stops `viz query` from touching some
  catalogs and schemas by accident. It is not a permission boundary: the
  warehouse's own permissions decide what you can read. Never try to get
  around a deny-list refusal; tell the user.
- `author` is attribution, not authentication. The CLI stamps it; never
  edit it by hand.
- Databricks credentials (`DATABRICKS_HOST`, `DATABRICKS_TOKEN`,
  `DATABRICKS_WAREHOUSE_ID`) belong to the user's environment. Never ask for
  a token in the conversation, and never write one to a file.
