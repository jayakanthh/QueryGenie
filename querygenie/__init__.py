"""QueryGenie core: the evaluated CodeS text-to-SQL pipeline with confidence-aware abstention.

    pipeline     prompt building, candidate execution, agreement selection (the evaluated setting)
    model        CodesSFTBackend: Spider-fine-tuned CodeS, 4 scored beam candidates
    confidence   strictness modes, measured operating points, ConfidentRun
    databases    the catalogue: sample, Spider, uploaded and connected databases
    connectors   PostgreSQL / MySQL via SQLAlchemy, SQL translated with sqlglot, read-only
    sample_db    builds the small academic sample database
    vendor/      code from the CodeS authors (Apache-2.0), see vendor/README.md
"""
