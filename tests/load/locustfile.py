"""Load test: simulate N tables x M concurrent players hammering the WS gateway.

Run against the Dockerized "prod-like" stack, not the laptop dev server, or the
numbers are misleading -- see docs/roadmap.md Phase 6.

TODO: a Locust User class that connects, sits, bets, and acts through repeated rounds;
capture p50/p95/p99 action latency.
"""
