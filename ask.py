#!/usr/bin/env python3
"""Query the local knowledge base (RAG) and answer with a local model.

Usage:
  ./ask.py "your question"
  ./ask.py --model reasoner "your question"   # use deepseek-r1:32b for judgment/analysis
  ./ask.py --model coder "your question"      # use qwen2.5-coder:32b for code/config (default)
  ./ask.py --no-rag "your question"           # skip retrieval, just ask the model directly
"""
import sys
import argparse
import chromadb
import ollama

DB_DIR = "/Users/abchatur/local-ai/chroma_db"
EMBED_MODEL = "nomic-embed-text"
MODELS = {
    "coder": "qwen2.5-coder:32b",
    "reasoner": "deepseek-r1:32b",
}
TOP_K = 6

SYSTEM_PROMPT = """You are a local expert assistant specialized in two domains:
1. BMC Helix / Innovation Studio / HPM (Agility Suite) configuration and API work
2. Pine Script (TradingView) and the user's trading strategies

Answer using the provided context when relevant. If the context doesn't cover
the question, say so plainly rather than guessing at facts about the user's
specific setup. Be concise and technical."""


def retrieve(query, k=TOP_K):
    client = chromadb.PersistentClient(path=DB_DIR)
    collection = client.get_collection("knowledge")
    emb = ollama.embeddings(model=EMBED_MODEL, prompt=query)["embedding"]
    results = collection.query(query_embeddings=[emb], n_results=k)
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    return list(zip(docs, metas))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="+")
    parser.add_argument("--model", choices=["coder", "reasoner"], default="coder")
    parser.add_argument("--no-rag", action="store_true")
    parser.add_argument("-k", type=int, default=TOP_K)
    args = parser.parse_args()

    question = " ".join(args.question)
    model = MODELS[args.model]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if not args.no_rag:
        hits = retrieve(question, args.k)
        context = "\n\n---\n\n".join(
            f"[{m['source']}]\n{d}" for d, m in hits
        )
        messages.append({
            "role": "user",
            "content": f"Context from local knowledge base:\n\n{context}\n\n---\n\nQuestion: {question}",
        })
        print(f"(retrieved {len(hits)} chunks from: {', '.join(sorted(set(m['source'] for _, m in hits)))})\n", file=sys.stderr)
    else:
        messages.append({"role": "user", "content": question})

    print(f"NEDA (model: {model})\n", file=sys.stderr)

    stream = ollama.chat(model=model, messages=messages, stream=True)
    for chunk in stream:
        print(chunk["message"]["content"], end="", flush=True)
    print()


if __name__ == "__main__":
    main()
