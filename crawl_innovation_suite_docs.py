#!/usr/bin/env python3
"""Crawl BMC Helix Innovation Suite documentation (26.3 / "is263" — the current
version, matching the 26.3 rollout project) into its own chromadb collection,
same XWQL-discovery approach as crawl_hpm_docs.py. Zero Claude token cost.

Usage: ./crawl_innovation_suite_docs.py
"""
from crawl_hpm_docs import crawl

SPACE_PREFIX = ("Service-Management.Innovation-Suite."
                "BMC-Helix-Innovation-Suite.is263")
COLLECTION = "innovation_suite_docs"
LOG = "/Users/abchatur/local-ai/innovation_suite_crawl_log.txt"

if __name__ == "__main__":
    crawl(space_prefix=SPACE_PREFIX, collection_name=COLLECTION, log_path=LOG, number=1000)
