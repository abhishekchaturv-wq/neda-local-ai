#!/usr/bin/env python3
"""Retry pages the HPM doc crawl skipped due to transient fetch errors
(timeouts, incomplete reads, SSL handshake timeouts) — NOT pages that were
skipped because they genuinely had no content (those are dead ends: stub/
redirect pages with nothing under #xwikicontent, re-fetching won't change
that). Appends newly-recovered pages into the existing "hpm_docs" collection
rather than rebuilding it.

Usage: ./retry_hpm_crawl.py
"""
import re
import time

import chromadb
import ollama

from crawl_hpm_docs import (
    BASE, DB_DIR, EMBED_MODEL, LOG, _fetch_bytes, chunk_text, extract, log,
)

_FAIL_RE = re.compile(r"^\d\d:\d\d:\d\d \[\d+/\d+\] fetch failed (\S+): (.+)$")
_INDEXED_RE = re.compile(r"^\d\d:\d\d:\d\d \[\d+/\d+\] indexed .*?: (.+)$")
MAX_ATTEMPTS = 3


def transient_failures():
    """Paths that failed to fetch (network/timeout), deduped, excluding any
    that a later run already indexed successfully."""
    failed = {}
    indexed_titles = set()
    with open(LOG) as f:
        for line in f:
            m = _FAIL_RE.match(line)
            if m:
                path, reason = m.groups()
                failed[path] = reason
            m2 = _INDEXED_RE.match(line)
            if m2:
                indexed_titles.add(m2.group(1))
    return failed


def main():
    failed = transient_failures()
    if not failed:
        log("retry: no transient fetch failures found in log")
        return

    log(f"retry: {len(failed)} transient failure(s) to retry")

    client = chromadb.PersistentClient(path=DB_DIR)
    collection = client.get_collection("hpm_docs")
    doc_id = collection.count()

    recovered = 0
    still_failed = 0
    still_no_content = 0

    for path, prior_reason in failed.items():
        html = None
        last_err = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                html = _fetch_bytes(BASE + path).decode("utf-8", errors="ignore")
                break
            except Exception as e:
                last_err = e
                time.sleep(2 * attempt)  # backoff between attempts

        if html is None:
            log(f"retry: still failing {path}: {last_err} (was: {prior_reason})")
            still_failed += 1
            continue

        text = extract(html)
        if len(text) < 100:
            log(f"retry: fetched OK but genuinely no content: {path}")
            still_no_content += 1
            continue

        title = path.strip("/").rsplit("/", 1)[-1].replace("-", " ")
        chunks = chunk_text(text)
        for j, chunk in enumerate(chunks):
            try:
                emb = ollama.embeddings(model=EMBED_MODEL, prompt=chunk)["embedding"]
            except Exception as e:
                log(f"  embed failed: {e}")
                continue
            collection.add(
                ids=[f"hpmdoc_retry{doc_id}"],
                embeddings=[emb],
                documents=[chunk],
                metadatas=[{"source": title, "url": BASE + path, "chunk": j}],
            )
            doc_id += 1
        recovered += 1
        log(f"retry: recovered ({len(chunks)} chunks): {path}")
        time.sleep(0.2)

    log(f"retry DONE. recovered: {recovered}, still failed: {still_failed}, "
        f"genuinely empty: {still_no_content}")


if __name__ == "__main__":
    main()
