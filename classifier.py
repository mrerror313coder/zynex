import re
from typing import Tuple

KEYWORDS_HIGH = [
    r"\bapply by\b",
    r"\bdeadline\b",
    r"\bapplications close\b",
    r"\bcall for\b",
    r"\bscholarship\b",
    r"\binternship\b",
    r"\bfellowship\b",
    r"\bcompetition\b",
    r"\bsubmit application\b",
]
KEYWORDS_MED = [
    r"\bopportunity\b",
    r"\bopenings\b",
    r"\bpositions\b",
    r"\bstipend\b",
    r"\baward\b",
    r"\bhackathon\b",
]
NEGATIVE = [r"\bnewsletter\b", r"\bunsubscribe\b", r"\badvertisement\b", r"\bpromo\b", r"\bspam\b"]


def is_opportunity(text: str, threshold: int = 3) -> Tuple[bool, str]:
    score = 0
    evidence = ""
    lines = text.splitlines() or [text]

    for line in lines:
        normalized = line.lower()
        for pattern in KEYWORDS_HIGH:
            if re.search(pattern, normalized):
                score += 3
                evidence = line.strip() or evidence
        for pattern in KEYWORDS_MED:
            if re.search(pattern, normalized):
                score += 1
                if not evidence:
                    evidence = line.strip()
        for pattern in NEGATIVE:
            if re.search(pattern, normalized):
                score -= 2

    fallback = lines[0].strip() if lines else ""
    return score >= threshold, evidence or fallback
