"""Pure orchestrator tying deck/hand/rules/state_machine/dealer into one round.

No I/O. Given a seed and a scripted sequence of player actions, a Round's outcome must
be fully deterministic and reproducible -- this is what makes Phase 1 "done": a full
multi-player round playable from a plain Python script/REPL, no server involved.

TODO:
- Round class: deal(), accept a player action for the seat-to-act, settle()
- Settlement math: win/lose/push/blackjack payout, using the ratio chosen in rules.py
"""
