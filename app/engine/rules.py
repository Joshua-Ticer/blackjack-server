"""Legal-action policy: what a player may do given a hand and table rules.

Document the rule set chosen here (this file is the source of truth referenced by
docs/adr/):
- Blackjack payout ratio: 3:2 or 6:5 -- TODO decide and document
- Dealer stands on soft 17? -- TODO decide and document
- Double-after-split allowed? -- TODO decide and document
- Split aces: one card only, no re-split? -- TODO decide and document
- Surrender: allowed, and late vs. early? -- TODO decide and document

TODO:
- legal_actions(hand, table_rules) -> set[Action]
"""
