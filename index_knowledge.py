#!/usr/bin/env python3
"""Index memory files + Pine scripts into a local Chroma vector store for RAG."""
import os
import re
import glob
import chromadb
import ollama

MEMORY_DIR = os.path.expanduser("~/.claude/projects/-Users-abchatur/memory")
PINE_DIR = os.path.expanduser("~/pine-scripts")
LEARNED_DIR = os.path.expanduser("~/local-ai/learned")
DB_DIR = os.path.expanduser("~/local-ai/chroma_db")
EMBED_MODEL = "nomic-embed-text"
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start = end - overlap
    return [c for c in chunks if c.strip()]


def collect_sources():
    sources = []
    for path in glob.glob(os.path.join(MEMORY_DIR, "*.md")):
        if os.path.basename(path) == "MEMORY.md":
            continue
        sources.append((path, "memory"))
    for path in glob.glob(os.path.join(PINE_DIR, "*.pine")):
        sources.append((path, "pine"))
    for path in glob.glob(os.path.join(LEARNED_DIR, "*.md")):
        sources.append((path, "learned"))
    return sources


def main():
    client = chromadb.PersistentClient(path=DB_DIR)
    try:
        client.delete_collection("knowledge")
    except Exception:
        pass
    collection = client.create_collection("knowledge")

    sources = collect_sources()
    print(f"Found {len(sources)} source files")

    doc_id = 0
    for path, kind in sources:
        with open(path, "r", errors="ignore") as f:
            text = f.read()
        chunks = chunk_text(text)
        for i, chunk in enumerate(chunks):
            emb = ollama.embeddings(model=EMBED_MODEL, prompt=chunk)["embedding"]
            collection.add(
                ids=[f"doc{doc_id}"],
                embeddings=[emb],
                documents=[chunk],
                metadatas=[{"source": os.path.basename(path), "kind": kind, "chunk": i}],
            )
            doc_id += 1
        print(f"  indexed {os.path.basename(path)} ({len(chunks)} chunks)")

    print(f"Total chunks indexed: {doc_id}")


if __name__ == "__main__":
    main()
