This is DuckDB's parquet extension, self-hosted so it never loads from a third-party origin at runtime.
It is DuckDB v1.4.3, `wasm_eh` build, from https://extensions.duckdb.org/v1.4.3/wasm_eh/parquet.duckdb_extension.wasm (pinned by size and sha256 in `tests/test_web_assets.py`).
It must be re-pinned (new file, updated size/hash) whenever `@duckdb/duckdb-wasm` is upgraded.
