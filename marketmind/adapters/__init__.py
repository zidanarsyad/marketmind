"""Adapters that turn real third-party datasets into MarketMind's data contracts (docs/schemas/datasets/).

Each adapter writes a data folder with raw/ (the CSV files the agents read) and manifest.json (what the data is, its
licence, and which fields were derived or are unknown). Point a study at it with `python run.py --data-dir <folder>`.
Adapters never download anything: the user fetches the source under its own terms.
"""
