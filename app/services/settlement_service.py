from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal
from app.engine.round import Seat
from app.engine.settlement import SettlementResult
from app.models.ledger import LedgerEntry
from app.models.round import Participation
from app.models.round import Round as RoundModel
from app.models.user import User


async def settle_round(
    round_id: UUID,
    results: list[SettlementResult],
    seats: list[Seat],
) -> dict[str, int]:
    seats_by_player = {seat.player_id: seat for seat in seats}
    results_by_player: dict[str, list[SettlementResult]] = defaultdict(list)
    for r in results:
        results_by_player[r.player_id].append(r)

    balances: dict[str, int] = {}

    async with SessionLocal() as session:
        async with session.begin():
            for player_id, player_results in results_by_player.items():
                user = await session.get(User, player_id, with_for_update=True)

                for r in player_results:
                    user.chip_balance += r.net
                    session.add(
                        LedgerEntry(
                            user_id=player_id,
                            round_id=round_id,
                            amount=r.net,
                            type=r.outcome.value,
                            balance_after=user.chip_balance,
                        )
                    )
                balances[player_id] = user.chip_balance

                seat = seats_by_player[player_id]
                participation = (
                    await session.execute(
                        select(Participation).where(
                            Participation.round_id == round_id,
                            Participation.user_id == player_id,
                        )
                    )
                ).scalar_one_or_none()
                if participation is not None:
                    participation.hands = [
                        [str(c) for c in hand.cards] for hand in seat.hands
                    ]
                    participation.outcome = "/".join(
                        r.outcome.value for r in player_results
                    )
                    participation.payout = sum(r.payout for r in player_results)

            round_row = await session.get(RoundModel, round_id)
            if round_row is not None:
                round_row.status = "settled"
                round_row.ended_at = datetime.now(timezone.utc).replace(tzinfo=None)

    return balances
