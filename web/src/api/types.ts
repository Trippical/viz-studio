// Shapes of the documents the server returns. They mirror
// schemas/chart.schema.json, schemas/dashboard.schema.json and the tree built
// by viz/server/tree.py. Everything here is untrusted input.

export type ColumnType = 'string' | 'number' | 'integer' | 'boolean' | 'date' | 'timestamp';

export interface Column {
  name: string;
  type: ColumnType;
}

export type Row = Record<string, unknown>;

export type Renderer = 'vega-lite' | 'stat';

export interface ChartData {
  format: 'json' | 'parquet';
  lane: 'small' | 'large';
  rows: number;
  bytes: number;
  columns: Column[];
}

export interface ChartSource {
  kind: 'databricks-sql';
  sql?: string;
  warehouse_id?: string;
  schedule?: string;
  show_sql?: boolean;
}

export interface Chart {
  schema_version: 1;
  id: string;
  title: string;
  description?: string;
  tags?: string[];
  author?: string;
  created_at?: string;
  updated_at?: string;
  renderer: Renderer;
  spec: unknown;
  data: ChartData;
  aggregate?: string | null;
  source?: ChartSource;
}

export interface DateRangeControl {
  id: string;
  type: 'date-range';
  label: string;
  column: string;
  default?: null | { last: string } | { from: string; to: string };
}

export interface SelectControl {
  id: string;
  type: 'select';
  label: string;
  column: string;
  multi?: boolean;
  default?: null | string | string[];
}

export interface NumberRangeControl {
  id: string;
  type: 'number-range';
  label: string;
  column: string;
  default?: null | { min?: number; max?: number };
}

export type Control = DateRangeControl | SelectControl | NumberRangeControl;

export interface ChartTileSpec {
  chart: string;
  w: number;
  h: number;
}

export interface MarkdownTileSpec {
  markdown: string;
  w: number;
  h: number;
}

export type Tile = ChartTileSpec | MarkdownTileSpec;

export interface Dashboard {
  schema_version: 1;
  id: string;
  title: string;
  description?: string;
  tags?: string[];
  author?: string;
  created_at?: string;
  updated_at?: string;
  controls?: Control[];
  layout: Tile[];
}

export interface TreeChartItem {
  type: 'chart';
  id: string;
  title?: string;
  description?: string | null;
  tags?: string[];
  renderer?: Renderer;
  lane?: 'small' | 'large';
  static?: boolean;
  updated_at?: string | null;
  error?: string;
}

export interface TreeDashboardItem {
  type: 'dashboard';
  id: string;
  title?: string;
  description?: string | null;
  tags?: string[];
  controls?: Control[];
  updated_at?: string | null;
  error?: string;
}

export type TreeItem = TreeChartItem | TreeDashboardItem;

export interface TreeFolder {
  type: 'folder';
  path: string;
  name: string;
  title: string | null;
  description: string | null;
  order: number | null;
  error: string | null;
  folders: TreeFolder[];
  items: TreeItem[];
}

export interface Tree {
  charts: TreeFolder;
  dashboards: TreeFolder;
  built_at: string;
}
