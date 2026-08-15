#!/usr/bin/env python3
"""Crawl BMC Helix Agent Studio documentation (part of the BMC HelixGPT product
docs, version 26.3 / "helixgpt263" — matches the 26.3 rollout project) into its
own chromadb collection, same XWQL-discovery approach as the other crawlers.

Usage: ./crawl_agent_studio_docs.py
"""
from crawl_hpm_docs import crawl

SPACE_PREFIX = "Service-Management.Employee-Digital-Workplace.BMC-HelixGPT.helixgpt263"
COLLECTION = "agent_studio_docs"
LOG = "/Users/abchatur/local-ai/agent_studio_crawl_log.txt"

if __name__ == "__main__":
    crawl(space_prefix=SPACE_PREFIX, collection_name=COLLECTION, log_path=LOG, number=1000)
