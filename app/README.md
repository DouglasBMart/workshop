# FastAPI CSV API for Databricks / Databricks Apps

Projeto exemplo para expor CSVs (Northwind-like) como API REST usando FastAPI.

## Endpoints principais
- `GET /api/v1/healthcheck`
- `GET /api/v1/tables`
- `GET /api/v1/table/{table}?limit=20&offset=0&q=abc`
- `GET /api/v1/table/{table}/{id}`
- `GET /api/v1/orders/{order_id}/details`
- `GET /api/v1/customers/{customer_id}/orders`
- `GET /api/v1/analytics/top-products`
- `POST /api/v1/reload`

## Estrutura de dados esperada
Coloque os arquivos CSV em uma pasta (DBFS/Volume) com nomes:
`categories.csv`, `customers.csv`, `employee_territories.csv`, `order_details.csv`, `orders.csv`, `products.csv`, `region.csv`, `shippers.csv`, `suppliers.csv`, `territories.csv`, `us_states.csv`.

## Databricks Apps
- `requirements.txt` define dependências Python
- `app.yaml` define o comando e variáveis de ambiente
- Use prefixo `/api` nas rotas para auth via bearer token (Databricks Apps)
