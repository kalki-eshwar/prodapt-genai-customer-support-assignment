# AI-Assisted Customer Support Response Generator

This project implements a simple business-ready support drafting assistant using:
- Local policy dataset (JSON)
- BM25 retrieval (`rank_bm25`)
- Sarvam AI API for response generation
- React + Vite frontend
- Python Flask backend

It is intentionally lightweight and avoids embeddings/vector databases.

## Features

- Accepts a customer complaint from a UI
- Retrieves top 3 relevant policy documents using BM25
- Runs in **Strict mode only**:
  - `temperature=0.2`, `max_tokens=150`
- Fallback when no good BM25 match:
  - Returns: `Please escalate this issue to a human support agent.`
- Returns generated response plus retrieved policy sources
- Retrieved sources now display full structured fields:
  - `trouble`
  - `category`
  - `solution`
  - `alternate_solution`
  - `company_response`
- Logs every request with query, docs, prompt, and parameters

## Project Structure

```text
customer_support/
  backend/
    data/support_records.json
    data/policies.json
    logs/support_queries.log
    src/app.py
    requirements.txt
    .env.example
  frontend/
    src/App.jsx
    src/App.css
    src/index.css
    .env.example
```

## Backend Setup (Python Environment)

From the project root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` and set:

```env
SARVAM_API_KEY=your_real_key
SARVAM_BASE_URL=https://api.sarvam.ai/v1/chat/completions
SARVAM_MODEL=sarvam-m
BM25_FALLBACK_THRESHOLD=0.3
TOP_K=3
FLASK_PORT=8000
```

Run backend:

```bash
source .venv/bin/activate
python src/app.py
```

Backend endpoints:
- `GET /health`
- `POST /api/respond`

Example payload:

```json
{
  "query": "My product arrived late and damaged. Can I get a refund?",
  "mode": "strict"
}

Note: even if another mode is sent, backend enforces strict mode.
```

## Frontend Setup (Vite)

In a new terminal:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev -- --host 0.0.0.0 --port 5173
```

Frontend env:

```env
VITE_API_URL=http://localhost:8000
```

Open: `http://localhost:5173`

## Prompt Mode

### Strict Policy Mode (Always On)
Prompt behavior:
- Uses only policy context
- Avoids assumptions
- Clear concise response

Parameters:
- `temperature = 0.2`
- `max_tokens = 150`

### Fallback Mode (No Good Match)
When BM25 best score is below threshold (`BM25_FALLBACK_THRESHOLD`), system returns:

`Please escalate this issue to a human support agent.`

## Logging

The backend logs each request to:

`backend/logs/support_queries.log`

Each log entry contains:
- Query
- Retrieved docs and scores
- Prompt used
- Parameters (`temperature`, `max_tokens`, threshold, top_k)
- Response text

## Testing Performed

### API Tests
- Health check works (`/health`)
- Strict mode returns top docs + strict parameters
- No-match query triggers fallback response
- Retrieval accuracy validated on policy-grounded cases:
  - late + damaged query ranks **Refund Policy** first
  - post-shipment cancellation query ranks **Cancellation Policy** first
  - personal care non-damaged return query ranks **Return Policy** first
- Generation quality guard validated:
  - if model output is empty, truncated, or reasoning-style, backend returns concise policy-grounded fallback text

## Notes

- If `SARVAM_API_KEY` is not configured, backend returns a clear configuration message instead of LLM output.
- Backend strips hidden reasoning tags and applies a response-quality check before returning final text.
- Replace `backend/data/policies.json` with your company policies to use real business content.
- The active retrieval dataset is `backend/data/support_records.json`.
- To expand your support knowledge base, add more objects in the same five-field format.
- If you get `source: no such file or directory: .venv/bin/activate`, first run `cd backend` and then activate the environment.
