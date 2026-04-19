import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from rank_bm25 import BM25Okapi

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_PATH = BASE_DIR / "data" / "support_records.json"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / "support_queries.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()],
)
logger = logging.getLogger("support-generator")


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


class PolicyRetriever:
    def __init__(self, dataset_path: Path):
        with dataset_path.open("r", encoding="utf-8") as file:
            self.documents = json.load(file)

        corpus = [
            (
                f"{doc.get('trouble', '')} "
                f"{doc.get('category', '')} "
                f"{doc.get('solution', '')} "
                f"{doc.get('alternate_solution', '')} "
                f"{doc.get('company_response', '')}"
            ).strip()
            for doc in self.documents
        ]
        tokenized_corpus = [tokenize(doc) for doc in corpus]
        self.bm25 = BM25Okapi(tokenized_corpus)

    def search(self, query: str, top_k: int = 3):
        tokenized_query = tokenize(query)
        scores = self.bm25.get_scores(tokenized_query)

        scored_docs = [
            {
                "trouble": self.documents[idx].get("trouble", ""),
                "category": self.documents[idx].get("category", ""),
                "solution": self.documents[idx].get("solution", ""),
                "alternate_solution": self.documents[idx].get("alternate_solution", ""),
                "company_response": self.documents[idx].get("company_response", ""),
                "score": float(score),
            }
            for idx, score in enumerate(scores)
        ]
        scored_docs.sort(key=lambda item: item["score"], reverse=True)
        return scored_docs[:top_k]


def build_prompt(mode: str, docs: list[dict], query: str):
    docs_text = "\n\n".join(
        [
            (
                f"Trouble: {doc.get('trouble', '')}\n"
                f"Category: {doc.get('category', '')}\n"
                f"Solution: {doc.get('solution', '')}\n"
                f"Alternate Solution: {doc.get('alternate_solution', '')}\n"
                f"Company Response: {doc.get('company_response', '')}"
            )
            for doc in docs
        ]
    )

    if mode == "strict":
        return (
            "You are a professional customer support assistant.\n\n"
            "Use ONLY the provided policy context.\n"
            "Do not add extra assumptions.\n\n"
            f"Context:\n{docs_text}\n\n"
            f"Customer Issue:\n{query}\n\n"
            "Give a clear and concise response in 2-4 sentences.\n"
            "Return only the final customer-facing answer.\n"
            "Do not include reasoning, analysis, or tags like <think>."
        ), 0.2, 150

    if mode == "balanced":
        return (
            "You are a helpful customer support assistant.\n\n"
            "Use the policy context and provide a neutral, practical response.\n\n"
            f"Context:\n{docs_text}\n\n"
            f"Customer Issue:\n{query}\n\n"
            "Respond clearly in 4-6 lines.\n"
            "Return only the final customer-facing answer.\n"
            "Do not include reasoning, analysis, or tags like <think>."
        ), 0.5, 180

    return (
        "You are a polite and empathetic support agent.\n\n"
        "Use the policy context but respond in a friendly tone.\n\n"
        f"Context:\n{docs_text}\n\n"
        f"Customer Issue:\n{query}\n\n"
        "Return only the final customer-facing answer.\n"
        "Do not include reasoning, analysis, or tags like <think>."
    ), 0.7, 200


def sanitize_model_response(text: str) -> str:
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = cleaned.strip()
    return cleaned


def summarize_policy_content(content: str, max_sentences: int = 2) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", content.strip())
    sentences = [sentence.strip() for sentence in sentences if sentence.strip()]
    summary = " ".join(sentences[:max_sentences])
    return summary or content.strip()


def response_needs_fallback(answer: str) -> bool:
    if not answer.strip() or len(answer.strip()) < 30:
        return True
    if re.search(r"\b(okay,\s*let's|i need to|first,\s*i need to)\b", answer.lower()):
        return True
    if answer.strip()[-1] not in ".!?":
        return True
    return False


def fallback_from_docs(docs: list[dict], mode: str) -> str:
    top_doc = docs[0] if docs else {}
    trouble = top_doc.get("trouble", "this issue")
    solution = top_doc.get("solution", "please contact support with your order ID")
    company_response = top_doc.get("company_response", "")
    response_seed = company_response or f"For {trouble}, the suggested resolution is: {solution}."
    content = summarize_policy_content(response_seed, max_sentences=3)
    if mode == "friendly":
        return (
            f"Thanks for reaching out. Based on our support policy, {content} "
            "Please share your order ID with support so we can process this quickly."
        )
    return f"According to our support policy, {content}"


def call_sarvam(prompt: str, temperature: float, max_tokens: int):
    api_key = os.getenv("SARVAM_API_KEY", "")
    base_url = os.getenv("SARVAM_BASE_URL", "https://api.sarvam.ai/v1/chat/completions")
    model = os.getenv("SARVAM_MODEL", "sarvam-m")

    if not api_key:
        return "Sarvam API key is not configured. Please set SARVAM_API_KEY in backend/.env."

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        response = requests.post(base_url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        if "choices" in data and data["choices"]:
            raw_text = data["choices"][0].get("message", {}).get("content", "")
            return sanitize_model_response(raw_text)

        return "No response generated by Sarvam API."
    except requests.RequestException as error:
        return f"Sarvam API request failed: {error}"


app = Flask(__name__)
CORS(app)
retriever = PolicyRetriever(DATASET_PATH)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/api/respond")
def respond():
    payload = request.get_json(silent=True) or {}
    query = (payload.get("query") or "").strip()
    mode = "strict"
    top_k = int(os.getenv("TOP_K", "3"))
    threshold = float(os.getenv("BM25_FALLBACK_THRESHOLD", "0.3"))

    if not query:
        return jsonify({"error": "query is required"}), 400

    docs = retriever.search(query, top_k=top_k)
    best_score = docs[0]["score"] if docs else 0.0

    if best_score < threshold:
        answer = "Please escalate this issue to a human support agent."
        prompt = (
            "No relevant policy found.\n\n"
            "Respond with:\n"
            '"Please escalate this issue to a human support agent."'
        )
        temperature = 0.0
        max_tokens = 30
    else:
        prompt, temperature, max_tokens = build_prompt(mode, docs, query)
        answer = call_sarvam(prompt, temperature, max_tokens)
        if response_needs_fallback(answer):
            answer = fallback_from_docs(docs, mode)

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "mode": mode,
        "retrieved_docs": docs,
        "prompt": prompt,
        "parameters": {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "threshold": threshold,
            "top_k": top_k,
        },
        "best_score": best_score,
        "response": answer,
    }
    logger.info(json.dumps(log_entry, ensure_ascii=True))

    return jsonify(
        {
            "response": answer,
            "documents": docs,
            "best_score": best_score,
            "used_mode": mode,
            "parameters": {
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        }
    )


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)
