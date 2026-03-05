from pathlib import Path
import os

import pandas as pd
from fastapi import FastAPI, HTTPException, Query

app = FastAPI()

# Caminho base do app no runtime do Databricks Apps
BASE_DIR = Path(__file__).resolve().parent

# Se app.yaml definir DATA_DIR, usa ele. Senão, usa ./data
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))


@app.get("/")
def root():
    return {
        "message": "CSV API ok",
        "base_dir": str(BASE_DIR),
        "data_dir": str(DATA_DIR),
        "example_routes": [
            "/api/health",
            "/api/files",
            "/api/csv/customers",
            "/api/csv/orders?limit=20"
        ]
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "base_dir": str(BASE_DIR),
        "data_dir": str(DATA_DIR),
        "exists": DATA_DIR.exists(),
        "is_dir": DATA_DIR.is_dir() if DATA_DIR.exists() else False
    }


@app.get("/api/files")
def files():
    if not DATA_DIR.exists():
        return {
            "status": "error",
            "data_dir": str(DATA_DIR),
            "exists": False,
            "files": []
        }

    try:
        file_list = sorted([p.name for p in DATA_DIR.iterdir() if p.is_file()])
        return {
            "status": "ok",
            "data_dir": str(DATA_DIR),
            "exists": True,
            "files": file_list,
            "count": len(file_list)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/csv/{file_name}")
def get_csv(file_name: str, limit: int = Query(100, ge=1, le=5000)):
    """
    Exemplos:
    /api/csv/customers
    /api/csv/orders?limit=20
    /api/csv/products.csv?limit=50
    """
    if not file_name.endswith(".csv"):
        file_name = f"{file_name}.csv"

    file_path = DATA_DIR / file_name

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Arquivo não encontrado: {file_name}")

    try:
        # leitura simples (sem "inventar moda")
        df = pd.read_csv(file_path)
        df = df.head(limit)

        # NaN -> None para serializar em JSON
        data = df.where(pd.notnull(df), None).to_dict(orient="records")

        return {
            "file": file_name,
            "path": str(file_path),
            "rows": len(data),
            "columns": list(df.columns),
            "data": data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))