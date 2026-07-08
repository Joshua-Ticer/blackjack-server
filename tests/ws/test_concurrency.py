"""Adversarial concurrency tests: prove the single-writer-per-table design holds.

TODO: fire two simultaneous `hit` requests from the same seat and assert only one is
honored; fire a duplicate `place_bet` with the same action_id and assert dedup.
"""
