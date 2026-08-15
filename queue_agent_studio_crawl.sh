#!/bin/bash
while ps -p 21586 > /dev/null 2>&1; do
  sleep 30
done
echo "$(date '+%H:%M:%S') Innovation Suite crawl finished, starting Agent Studio crawl" >> queue_runner_log.txt
cd /Users/abchatur/local-ai
venv/bin/python crawl_agent_studio_docs.py
echo "$(date '+%H:%M:%S') Agent Studio crawl process exited" >> queue_runner_log.txt
