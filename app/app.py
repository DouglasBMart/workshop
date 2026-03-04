from pathlib import Path
import os

import pandas as pd
from fastapi import FastAPI, HTTPException, Query

app = FastAPI()

# pasta data dentro do app (ou sobrescreve via app.yaml com DATA_DIR)
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))

@app.get("/")
def root():
    return {
        "message": "CSV API ok",
        "data_dir": str(DATA_DIR),
        "example": "/api/csv/customers"
    }

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "data_dir": str(DATA_DIR),
        "exists": DATA_DIR.exists()
    }

@app.get("/api/csv/{file_name}")
def get_csv(file_name: str, limit: int = Query(100, ge=1, le=5000)):
    """
    Exemplo:
    /api/csv/customers
    /api/csv/orders?limit=50
    """
    # aceita com ou sem .csv
    if not file_name.endswith(".csv"):
        file_name = f"{file_name}.csv"

    file_path = DATA_DIR / file_name

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Arquivo não encontrado: {file_name}")

    try:
        df = pd.read_csv(file_path)
        df = df.head(limit)

        # NaN -> None para JSON
        data = df.where(pd.notnull(df), None).to_dict(orient="records")

        return {
            "file": file_name,
            "rows": len(data),
            "columns": list(df.columns),
            "data": data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))