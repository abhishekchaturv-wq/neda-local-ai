#!/usr/bin/env python3
"""Crawl BMC Helix Portfolio Management documentation and index it into NEDA's
knowledge base, entirely locally — page fetching, text extraction, and embedding
all happen here via Python + Ollama, at zero Claude token cost. Separate chromadb
collection ("hpm_docs") from the memory/Pine-script index ("knowledge").

Page discovery uses XWiki's REST query API (XWQL) to get the complete, authoritative
list of pages under the HPM docs space in one call — the site's rendered-HTML nav
tree lives outside the main content div and isn't reliably link-scrapable, so this
is the robust approach (confirmed: 266 pages found this way vs. 0 via link-following
from the landing pages, which have almost no body content of their own).

docs.bmc.com blocks scripted requests (403) — this crawls the docs.helixops.ai
mirror instead, same content, same URL structure.
"""
import re
import ssl
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

import chromadb
import ollama
from bs4 import BeautifulSoup

# Corporate TLS-inspection proxy presents a self-signed chain (same issue as
# smc_scanner.py / hpm_readonly.py) — curl to the same host succeeds.
_SSLCTX = ssl.create_default_context()
_SSLCTX.check_hostname = False
_SSLCTX.verify_mode = ssl.CERT_NONE

BASE = "https://docs.helixops.ai"
SPACE_PREFIX = ("Service-Management.Enterprise-Service-Management."
                "BMC-Helix-Portfolio-Management.BMC-Helix-Portfolio-Management-25-3")
NS = {"x": "http://www.xwiki.org"}
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200
EMBED_MODEL = "nomic-embed-text"
DB_DIR = "/Users/abchatur/local-ai/chroma_db"
LOG = "/Users/abchatur/local-ai/hpm_crawl_log.txt"

_LOG_PATH = LOG  # module-level, overridable per-run via log_to()


def log_to(path):
    """Switch the log file a subsequent crawl() run writes to."""
    global _LOG_PATH
    _LOG_PATH = path


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(_LOG_PATH, "a") as f:
        f.write(line + "\n")


def _fetch_bytes(url, params=None):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30, context=_SSLCTX) as r:
        return r.read()


def discover_pages(space_prefix=SPACE_PREFIX, number=500):
    """Full, authoritative page list via XWiki's XWQL query API."""
    data = _fetch_bytes(f"{BASE}/rest/wikis/xwiki/query", {
        "q": f"where doc.space like '{space_prefix}.%'",
        "type": "xwql",
        "number": str(number),
    })
    root = ET.fromstring(data)
    urls = []
    for result in root.findall("x:searchResult", NS):
        space = result.find("x:space", NS).text
        page_name = result.find("x:pageName", NS).text
        title = result.find("x:title", NS).text or page_name
        if page_name in ("WebPreferences",) or title in ("Page Administration",):
            continue  # system/admin pages, not real documentation content
        path = "/bin/" + space.replace(".", "/") + "/"
        if page_name != "WebHome":
            path += page_name + "/"
        urls.append((path, title))
    return urls


def extract(html):
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find(id="xwikicontent") or soup.find("div", class_="xcontent") or soup.body
    if not main:
        return ""
    for tag in main(["script", "style", "nav"]):
        tag.decompose()
    text = main.get_text(separator="\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text)


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start = end - overlap
    return [c for c in chunks if len(c.strip()) > 50]


def crawl(space_prefix=SPACE_PREFIX, collection_name="hpm_docs", log_path=None,
          number=500, recreate=True):
    """Crawl every page under space_prefix and index it into the given chromadb
    collection. Reusable for any docs.helixops.ai XWiki space, not just HPM."""
    if log_path:
        log_to(log_path)

    client = chromadb.PersistentClient(path=DB_DIR)
    if recreate:
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass
        collection = client.create_collection(collection_name)
    else:
        collection = client.get_or_create_collection(collection_name)

    pages = discover_pages(space_prefix, number=number)
    log(f"discovered {len(pages)} pages under {space_prefix} via XWiki query API")

    doc_id = 0
    pages_indexed = 0
    pages_skipped = 0

    for i, (path, title) in enumerate(pages, 1):
        try:
            html = _fetch_bytes(BASE + path).decode("utf-8", errors="ignore")
        except Exception as e:
            log(f"[{i}/{len(pages)}] fetch failed {path}: {e}")
            pages_skipped += 1
            continue

        text = extract(html)
        if len(text) < 100:
            log(f"[{i}/{len(pages)}] skipped (no content): {title}")
            pages_skipped += 1
            continue

        chunks = chunk_text(text)
        for j, chunk in enumerate(chunks):
            try:
                emb = ollama.embeddings(model=EMBED_MODEL, prompt=chunk)["embedding"]
            except Exception as e:
                log(f"  embed failed: {e}")
                continue
            collection.add(
                ids=[f"{collection_name}_{doc_id}"],
                embeddings=[emb],
                documents=[chunk],
                metadatas=[{"source": title, "url": BASE + path, "chunk": j}],
            )
            doc_id += 1
        pages_indexed += 1
        log(f"[{i}/{len(pages)}] indexed ({len(chunks)} chunks): {title}")
        time.sleep(0.2)  # be polite to the doc server

    log(f"DONE. Pages indexed: {pages_indexed}, skipped: {pages_skipped}, total chunks: {doc_id}")


if __name__ == "__main__":
    crawl()
