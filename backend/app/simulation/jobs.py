"""
Single source of truth for the v0.1 job catalog. salary.py reads base
rates from here; citizen_service reads the job list from here for
auto-assignment at creation time — so adding a job means editing one
dict, not two files that could drift apart.
"""

JOB_BASE_SALARY = {
    "engineer": 120,
    "doctor": 150,
    "nurse": 90,
    "teacher": 70,
    "chef": 70,
    "shopkeeper": 65,
    "driver": 55,
    "farmer": 60,
    "artist": 55,
    "banker": 2250,
    "thief": 0,      # নিয়মিত কোনো বেতন নেই (চুরি থেকে আয় করবে)
    "bhikkhuk": 10,  # প্রতিদিন খুব সামান্য সাহায্য পাওয়ার আনুমানিক হার
}

DEFAULT_BASE_SALARY = 60

# "unemployed" is deliberately not in JOB_BASE_SALARY (it's the "no job"
# state, not a job with a salary) — citizen_service adds it back into the
# weighted choices for auto-assignment so new citizens aren't all employed.
JOB_NAMES = list(JOB_BASE_SALARY.keys())