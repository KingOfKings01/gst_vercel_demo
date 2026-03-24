import cv2
import numpy as np
import ddddocr
import base64
import os
import re
from collections import Counter

# ─────────────────────────────────────────────
# TWO BRAINS (Standard + Beta)
# ─────────────────────────────────────────────
_STD = ddddocr.DdddOcr(show_ad=False)
_BETA = ddddocr.DdddOcr(beta=True, show_ad=False)

CHAR_MAP = {
    'o': '0', 'O': '0', 'D': '0', 'Q': '0', 'z': '2', 'Z': '2',
    'l': '1', 'I': '1', 'i': '1', '|': '1', 's': '5', 'S': '5',
    'g': '9', 'q': '9', 't': '7', 'b': '6', 'B': '8', 'A': '4', 'h': '6', 'e': '6'
}

def _clean(text):
    res = ""
    for ch in str(text or ""):
        if ch.isdigit(): res += ch
        elif ch in CHAR_MAP: res += CHAR_MAP[ch]
    return res

def solve_captcha_from_image(img):
    """
    Solves the captcha from an OpenCV image.
    Uses multi-processing logic to improve consistency.
    """
    pool = []
    # 1. Red Channel Isolate
    _, _, red = cv2.split(img)
    
    for scale in [2, 3]:
        scaled = cv2.resize(red, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        # Style A: BlackHat
        for ks in [15, 25]:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (ks, ks))
            bh = cv2.morphologyEx(scaled, cv2.MORPH_BLACKHAT, kernel)
            for tv in [40, 60]:
                _, bht = cv2.threshold(bh, tv, 255, cv2.THRESH_BINARY_INV)
                dt = cv2.imencode('.png', bht)[1].tobytes()
                pool.append(_clean(_STD.classification(dt)))
                pool.append(_clean(_BETA.classification(dt)))
                
    if not pool: return ""
    
    # Consolidate results
    six = [x for x in pool if len(x) == 6]
    if six:
        counts = Counter(six).most_common()
        if counts[0][1] >= 2:
            return counts[0][0]
        # Positional Majority
        ans = ""
        for i in range(6):
            ans += Counter([s[i] for s in six]).most_common(1)[0][0]
        return ans
    
    return sorted(pool, key=lambda x: (abs(len(x)-6), -len(x)))[0] if pool else ""

def solve_captcha_base64(b64):
    """Solves the captcha from a base64 string."""
    if ',' in b64: b64 = b64.split(',')[1]
    nparr = np.frombuffer(base64.b64decode(b64), np.uint8)
    return solve_captcha_from_image(cv2.imdecode(nparr, cv2.IMREAD_COLOR))