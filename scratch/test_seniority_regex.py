import re

# Comprehensive seniority pattern
# Catches senior markers as whole words/abbreviations, case-insensitive,
# with or without a period or hyphen:
# Sr, Sr., Snr, Senior, Lead, Principal, Staff, Manager, Director, Architect,
# Head of, Distinguished, Fellow, Consultant-level wording such as "Sr. Consultant".
# Avoids false positives inside other words (e.g. "Srinivas", "Leader" in a team name, "Staffing").

seniority_pattern = re.compile(
    r'\b(?:'
    r'sr|snr|senior|lead|principal|staff|manager|director|architect|'
    r'head\s+of|distinguished|fellow'
    r')(?:\.|\b)'
    r'|'
    r'\b(?:sr\.?|snr\.?|senior|lead|principal|staff)\s*[-]?\s*consultant(?:\s+level)?\b'
    r'|'
    r'\bconsultant\s*[-]?\s*level\b',
    re.IGNORECASE
)

test_cases = [
    ("Sr Software Engineer - Python", True),
    ("Software Engineer - Sr. Consultant Level (SDET, Playwright)", True),
    ("Sr. Software Engineer", True),
    ("Snr Software Engineer", True),
    ("Snr. Software Engineer", True),
    ("Sr-Software Engineer", True),
    ("Senior Software Engineer", True),
    ("Lead Engineer", True),
    ("Principal Architect", True),
    ("Staff Software Engineer", True),
    ("Engineering Manager", True),
    ("Director of Engineering", True),
    ("Solutions Architect", True),
    ("Head of Engineering", True),
    ("Distinguished Engineer", True),
    ("Fellow", True),
    ("Senior Consultant", True),
    ("Sr. Consultant", True),
    ("Sr.-Consultant", True),
    ("Software Engineer - Consultant Level", True),
    # False positive checks
    ("Srinivas", False),
    ("Team Leader", False),
    ("Staffing Coordinator", False),
    ("Leadership Development Program", False),
    ("Junior Software Engineer", False),
    ("Software Engineer", False),
    ("Associate Software Engineer", False),
    ("Graduate Trainee", False),
    ("Associate Consultant", False),
]

all_pass = True
for title, expected in test_cases:
    m = bool(seniority_pattern.search(title))
    status = "PASS" if m == expected else "FAIL"
    if status == "FAIL":
        all_pass = False
    print(f"{title:60} -> {m} (expected {expected}) {status}")

print(f"\nOverall: {'ALL PASSED' if all_pass else 'FAILURES EXIST'}")
