"""
Gives citizens with money something to spend it on. Like
social_interactions.py, this is a secondary effect layered on top of the
primary action FSM (see decision_pipeline.py) rather than a competing
primary action — scoring "should I shop" against sleep/eat/work/socialize
would need the utility functions to know the citizen's wallet balance,
which lives in a separate table the Citizen model doesn't carry. Every
citizen gets an independent, modest chance per tick to buy something they
can afford, regardless of what their primary action was.
"""

import random

from app.repositories import shop_repo, wallet_repo

SHOP_PROBABILITY = 0.2


def perform_shopping(db, citizen, broadcast_queue) -> None:
    if random.random() >= SHOP_PROBABILITY:
        return

    wallet = wallet_repo.get_by_citizen_id(db, citizen.id)
    if wallet is None or wallet.balance <= 0:
        return

    affordable = shop_repo.list_affordable_products(db, wallet.balance)
    if not affordable:
        return

    product = random.choice(affordable)

    wallet.balance = wallet.balance - product.price
    db.add(wallet)
    wallet_repo.record_transaction(
        db,
        from_wallet_id=wallet.id,
        to_wallet_id=None,  # money leaving the simulated economy — see Purchase model docstring
        amount=product.price,
        type_="purchase",
        commit=False,
    )
    shop_repo.create_purchase(
        db,
        citizen_id=citizen.id,
        shop_id=product.shop_id,
        product_id=product.id,
        price=product.price,
        commit=False,
    )
    broadcast_queue.append({
        "type": "new_purchase",
        "citizen_id": citizen.id,
        "citizen_name": citizen.name,
        "product_name": product.name,
        "price": str(product.price),
    })
