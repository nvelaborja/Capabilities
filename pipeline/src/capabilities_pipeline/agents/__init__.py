"""Agents that propose curated facts, checked by code and by another agent, for a person to merge (ADR 0035, ADR 0048).

Each agent step is one Claude Code run in print mode (`claude -p`) on the user's own Claude login, so runs draw on the
plan's usage limits rather than an API bill. Nothing here merges anything: accepted proposals become a draft pull
request.
"""
