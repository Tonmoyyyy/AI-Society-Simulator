"""
Lets citizens actually give each other money, not just via a
human-triggered wallet transfer. Same "secondary effect on top of the
primary action FSM" pattern as social_interactions.py and shopping.py —
see those modules' docstrings for why gifting isn't a competing primary
action (it needs wallet balance, which the Citizen model doesn't carry).

Kept intentionally modest: a small fraction of a citizen's balance, and
only citizens who already have some money to spare gift at all — this is
flavor/richness for the simulation, not a redistribution mechanism.
"""

import random
from decimal import Decimal

from app.repositories import wallet_repo

GIFT_PROBABILITY = 0.08
MIN_BALANCE_TO_GIFT = Decimal("20.00")
GIFT_FRACTION_RANGE = (0.05, 0.15)  # gives 5-15% of current balance


def perform_gift(db, citizen, other_citizens, broadcast_queue) -> None:
    if random.random() >= GIFT_PROBABILITY:
        return

    wallet = wallet_repo.get_by_citizen_id(db, citizen.id)
    if wallet is None or wallet.balance < MIN_BALANCE_TO_GIFT:
        return

    candidates = [c for c in other_citizens if c.id != citizen.id]
    if not candidates:
        return
    target = random.choice(candidates)

    target_wallet = wallet_repo.get_by_citizen_id(db, target.id)
    if target_wallet is None:
        target_wallet = wallet_repo.create_wallet(db, target.id, commit=False)
        db.flush()  # need target_wallet.id for the transaction row below

    fraction = Decimal(str(random.uniform(*GIFT_FRACTION_RANGE)))
    amount = (wallet.balance * fraction).quantize(Decimal("0.01"))
    if amount <= 0 or amount > wallet.balance:
        return

    wallet.balance = wallet.balance - amount
    target_wallet.balance = target_wallet.balance + amount
    db.add(wallet)
    db.add(target_wallet)
    wallet_repo.record_transaction(
        db,
        from_wallet_id=wallet.id,
        to_wallet_id=target_wallet.id,
        amount=amount,
        type_="gift",
        commit=False,
    )
    broadcast_queue.append({
        "type": "new_gift",
        "from_citizen_id": citizen.id,
        "from_citizen_name": citizen.name,
        "to_citizen_id": target.id,
        "to_citizen_name": target.name,
        "amount": str(amount),
    })
