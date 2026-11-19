# TravelDesk: AI-Powered Travel & Expense Management

EY AI & Data Capstone, Project 04 (Team 4). The full design is in the [Agile Spec v2.0](docs/agile_spec_link.md).

> README owner: Mradul (M3). Sections marked TODO are filled during S5.

## Architecture

![Architecture](docs/diagrams/04_architecture.png)

React (Employee and Manager views, JWT) -> FastAPI (business API + isolated Vera chat API) -> local PostgreSQL (pgAdmin).
Vera uses only expense-policy RAG and the Open-Meteo weather tool, through a hosted LLM (OpenRouter, Nemotron).

## Setup

1. **Database** (each teammate, once): install PostgreSQL + pgAdmin, then in pgAdmin's Query Tool:
   ```sql
   CREATE DATABASE traveldesk;      ALTER DATABASE traveldesk SET timezone = 'Asia/Kolkata';
   CREATE DATABASE traveldesk_test; ALTER DATABASE traveldesk_test SET timezone = 'Asia/Kolkata';
   ```
2. **Backend**
   ```bash
   cd backend
   python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env                                   # fill in every placeholder
   python scripts/init_db.py
   python scripts/ingest_policy.py
   uvicorn app.main:app --reload --port 8000              # Swagger: http://localhost:8000/docs
   pytest -q
   ```
3. **Frontend**
   ```bash
   cd frontend && npm install && cp .env.example .env && npm run dev   # http://localhost:5173
   ```

## Example requests

TODO (S5): copy from the spec's API specification and the Postman collection.

## Limitations and changes from the brief

TODO (S5): from the spec's "Changes from the assessment brief" and "Risks, assumptions and limitations".

## Demo

TODO (S5): the 14 demo steps from the spec.
