from decimal import Decimal, ROUND_HALF_UP

# Simple job -> base hourly-ish salary lookup (1 tick = 1 simulated hour,
# so these are "per work tick" amounts, not annual/monthly). Unlisted jobs
# fall back to _DEFAULT_BASE. No real economy/market pricing yet — that's
# a bigger feature than v0.1 needs.
_JOB_BASE_SALARY = {
    "engineer": 120,
    "doctor": 150,
    "nurse": 90,
    "teacher": 70,
    "chef": 70,
    "shopkeeper": 65,
    "driver": 55,
    "farmer": 60,
    "artist": 55,
    "baker": 50,
}
_DEFAULT_BASE = 60


def calculate_salary(citizen) -> Decimal:
    """Ambitious citizens negotiate/earn a bit more; lazy ones a bit less —
    a +/-25% swing across the 0-100 ambition range, centered on the job's
    base rate."""
    base = _JOB_BASE_SALARY.get(citizen.job.lower(), _DEFAULT_BASE)
    ambition = citizen.personality_json.get("ambition", 50)
    multiplier = 1 + (ambition - 50) / 200
    amount = Decimal(str(base)) * Decimal(str(multiplier))
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
