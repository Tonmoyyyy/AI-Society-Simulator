from decimal import Decimal, ROUND_HALF_UP

from app.simulation.jobs import JOB_BASE_SALARY, DEFAULT_BASE_SALARY


def calculate_salary(citizen) -> Decimal:
    """Ambitious citizens negotiate/earn a bit more; lazy ones a bit less —
    a +/-25% swing across the 0-100 ambition range, centered on the job's
    base rate. Base rates come from simulation/jobs.py (shared with
    citizen_service's job auto-assignment)."""
    base = JOB_BASE_SALARY.get(citizen.job.lower(), DEFAULT_BASE_SALARY)
    ambition = citizen.personality_json.get("ambition", 50)
    multiplier = 1 + (ambition - 50) / 200
    amount = Decimal(str(base)) * Decimal(str(multiplier))
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
