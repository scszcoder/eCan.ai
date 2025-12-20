import json
import random
from pathlib import Path

class FingerprintManager:
    def __init__(self, fingerprint_file: str = "fingerprints.json"):
        self.fingerprint_file = Path(fingerprint_file)
        with open(self.fingerprint_file, "r", encoding="utf-8") as f:
            self.fingerprints = json.load(f)

    def get_random_fingerprint(self):
        return random.choice(self.fingerprints)
