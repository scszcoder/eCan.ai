import re

def all_substrings(needles, haystack):
    if not needles:  # define empty policy: True or False as you need
        return True
    h = haystack.lower()
    return all(n and n.lower() in h for n in needles)  # excludes empty needles
