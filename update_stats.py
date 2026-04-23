# ─────────────────────────────────────────────────────────────
# CWS Prospects — Daily Stats Auto-Update
# Runs every morning at 8am CT (1pm UTC) and on manual trigger
# ─────────────────────────────────────────────────────────────

name: Update Prospect Stats

on:
  schedule:
    - cron: '0 13 * * *'
  workflow_dispatch:

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

jobs:
  update-stats:
    runs-on: ubuntu-latest

    permissions:
      contents: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install requests

      - name: Run update_stats.py
        run: python update_stats.py

      - name: Commit updated stats
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

          if git diff --quiet index.html; then
            echo "No stat changes today — nothing to commit."
          else
            git add index.html
            git commit -m "Auto-update: MiLB stats $(date +'%Y-%m-%d')"
            git push
            echo "Stats updated and pushed."
          fi
