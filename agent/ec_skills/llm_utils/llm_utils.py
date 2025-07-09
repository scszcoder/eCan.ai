import re

def rough_token_count(text: str) -> int:
    # Split on whitespace and common punctuations (roughly approximates token count)
    tokens = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
    return len(tokens)