import os
from pathlib import Path
from functools import lru_cache
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query

APP_TITLE = "Northwind CSV API (Databricks + FastAPI)"
APP_VERSION = "1.0.0"

# Use /api prefix for Databricks Apps token-protected endpoints.
app = FastAPI(title=APP_TITLE, version=APP_VERSION)

# ====== CONFIG ======
# In Databricks Apps, point DATA_DIR to a Volume or workspace path with your CSVs.
# Example: /Volumes/main/default/northwind_csv
DATA_DIR = os.getenv("DATA_DIR", "/tmp/northwind_csv")

# Map logical table names to files.
TABLE_FILES = {
    "categories": "categories.csv",
    "customers": "customers.csv",
    "employee_territories": "employee_territories.csv",
    "order_details": "order_details.csv",
    "orders": "orders.csv",
    "products": "products.csv",
    "region": "region.csv",
    "shippers": "shippers.csv",
    "suppliers": "suppliers.csv",
    "territories": "territories.csv",
    "us_states": "us_states.csv",
}

# Primary-key hints (used by /table/{table}/{id}).
PK_HINTS = {
    "categories": "category_id",
    "customers": "customer_id",
    "orders": "order_id",
    "products": "product_id",
    "region": "region_id",
    "shippers": "shipper_id",
    "suppliers": "supplier_id",
    "territories": "territory_id",
    "us_states": "state_id",
}

DATE_COLUMNS = {
    "orders": ["order_date", "required_date", "shipped_date"],
}


def _safe_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    # Convert NaN/NaT to None for JSON serialization
    return df.where(pd.notnull(df), None).to_dict(orient="records")


@lru_cache(maxsize=1)
def load_all_tables() -> Dict[str, pd.DataFrame]:
    base = Path(DATA_DIR)
    if not base.exists():
        raise FileNotFoundError(f"DATA_DIR not found: {DATA_DIR}")

    tables: Dict[str, pd.DataFrame] = {}
    for table, fname in TABLE_FILES.items():
        p = base / fname
        if not p.exists():
            # Skip missing files to keep app usable in class demos
            continue
        df = pd.read_csv(p)

        # Light typing fixes
        for col in DATE_COLUMNS.get(table, []):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")

        tables[table] = df
    return tables


def get_table_or_404(table: str) -> pd.DataFrame:
    tables = load_all_tables()
    if table not in tables:
        available = sorted(tables.keys())
        raise HTTPException(status_code=404, detail={"error": f"Table '{table}' not found", "available_tables": available})
    return tables[table]


@app.get("/")
def root():
    return {
        "name": APP_TITLE,
        "version": APP_VERSION,
        "docs": "/docs",
        "api_docs": "/docs (for local) | /api/v1/... endpoints for data",
        "data_dir": DATA_DIR,
    }


@app.get("/api/v1/healthcheck")
def healthcheck():
    try:
        tables = load_all_tables()
        return {
            "status": "ok",
            "tables_loaded": len(tables),
            "tables": sorted(tables.keys()),
            "data_dir": DATA_DIR,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/reload")
def reload_tables():
    load_all_tables.cache_clear()
    tables = load_all_tables()
    return {"status": "reloaded", "tables_loaded": len(tables)}


@app.get("/api/v1/tables")
def list_tables():
    tables = load_all_tables()
    meta = {}
    for name, df in tables.items():
        meta[name] = {
            "rows": int(len(df)),
            "columns": list(df.columns),
        }
    return meta


@app.get("/api/v1/table/{table}")
def get_table_rows(
    table: str,
    limit: int = Query(20, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    columns: Optional[str] = None,
    q: Optional[str] = None,
):
    """
    Generic table endpoint with simple pagination and filtering.
    - columns=col1,col2
    - q=texto  (search across string columns)
    """
    df = get_table_or_404(table).copy()

    if q:
        mask = pd.Series(False, index=df.index)
        for col in df.columns:
            if pd.api.types.is_string_dtype(df[col]) or df[col].dtype == object:
                mask = mask | df[col].astype(str).str.contains(q, case=False, na=False)
        df = df[mask]

    selected_cols = None
    if columns:
        selected_cols = [c.strip() for c in columns.split(",") if c.strip()]
        missing = [c for c in selected_cols if c not in df.columns]
        if missing:
            raise HTTPException(status_code=400, detail={"error": "Invalid columns", "missing": missing})
        df = df[selected_cols]

    total = len(df)
    page = df.iloc[offset: offset + limit]
    return {
        "table": table,
        "total": int(total),
        "offset": offset,
        "limit": limit,
        "returned": int(len(page)),
        "columns": list(page.columns),
        "data": _safe_records(page),
    }


@app.get("/api/v1/table/{table}/{item_id}")
def get_row_by_id(table: str, item_id: str):
    df = get_table_or_404(table).copy()
    pk = PK_HINTS.get(table)
    if not pk or pk not in df.columns:
        raise HTTPException(status_code=400, detail=f"No primary key configured for table '{table}'")

    # string compare to support both numeric and text IDs
    match = df[df[pk].astype(str) == str(item_id)]
    if match.empty:
        raise HTTPException(status_code=404, detail=f"{table} id '{item_id}' not found")
    return _safe_records(match.iloc[:1])[0]


@app.get("/api/v1/orders/{order_id}/details")
def order_with_details(order_id: int):
    tables = load_all_tables()
    required = ["orders", "order_details", "products"]
    for t in required:
        if t not in tables:
            raise HTTPException(status_code=500, detail=f"Missing required table: {t}")

    orders = tables["orders"]
    od = tables["order_details"]
    products = tables["products"][["product_id", "product_name", "category_id", "supplier_id"]].copy()

    order_row = orders[orders["order_id"] == order_id]
    if order_row.empty:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    items = od[od["order_id"] == order_id].copy()
    if items.empty:
        return {"order": _safe_records(order_row)[0], "items": [], "totals": {"items": 0, "gross": 0.0}}

    items = items.merge(products, on="product_id", how="left")
    items["line_total"] = items["unit_price"] * items["quantity"] * (1 - items["discount"].fillna(0))

    return {
        "order": _safe_records(order_row)[0],
        "items": _safe_records(items),
        "totals": {
            "items": int(len(items)),
            "gross": round(float(items["line_total"].sum()), 2),
        },
    }


@app.get("/api/v1/customers/{customer_id}/orders")
def customer_orders(customer_id: str, limit: int = Query(20, ge=1, le=500)):
    tables = load_all_tables()
    if "customers" not in tables or "orders" not in tables:
        raise HTTPException(status_code=500, detail="Missing customers/orders tables")

    customers = tables["customers"]
    orders = tables["orders"].copy()

    cust = customers[customers["customer_id"].astype(str) == str(customer_id)]
    if cust.empty:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")

    rows = orders[orders["customer_id"].astype(str) == str(customer_id)].copy()
    if "order_date" in rows.columns:
        rows = rows.sort_values("order_date", ascending=False, na_position="last")

    return {
        "customer": _safe_records(cust.iloc[:1])[0],
        "orders_count": int(len(rows)),
        "orders": _safe_records(rows.head(limit)),
    }


@app.get("/api/v1/analytics/top-products")
def top_products(limit: int = Query(10, ge=1, le=100)):
    tables = load_all_tables()
    if "order_details" not in tables or "products" not in tables:
        raise HTTPException(status_code=500, detail="Missing order_details/products tables")

    od = tables["order_details"].copy()
    products = tables["products"][["product_id", "product_name"]].copy()

    od["line_total"] = od["unit_price"] * od["quantity"] * (1 - od["discount"].fillna(0))
    agg = (
        od.groupby("product_id", as_index=False)
        .agg(
            total_qty=("quantity", "sum"),
            total_revenue=("line_total", "sum"),
            order_lines=("order_id", "count"),
        )
        .merge(products, on="product_id", how="left")
        .sort_values(["total_revenue", "total_qty"], ascending=False)
        .head(limit)
    )
    agg["total_revenue"] = agg["total_revenue"].round(2)
    return {"limit": limit, "data": _safe_records(agg)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)
