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

# ─────────────────────────────────────────────
# SHAPE-AWARE DIGIT HARVESTER
# ─────────────────────────────────────────────

def get_best_candidates(img):
    pool = []
    # 1. KILL THE WAVE (Red Channel Isolate)
    _, _, red = cv2.split(img)
    
    for scale in [2, 3]:
        scaled = cv2.resize(red, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        # STYLE A: BlackHat (Standard Sweep)
        for ks in [15, 25, 35]:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (ks, ks))
            bh = cv2.morphologyEx(scaled, cv2.MORPH_BLACKHAT, kernel)
            for tv in [30, 50, 70]:
                _, bht = cv2.threshold(bh, tv, 255, cv2.THRESH_BINARY_INV)
                dt = cv2.imencode('.png', bht)[1].tobytes()
                pool.append(_clean(_STD.classification(dt)))
                pool.append(_clean(_BETA.classification(dt)))
                
        # STYLE B: "The Mender" (Thickening to catch thin '4' hooks)
        mended = cv2.erode(scaled, np.ones((2, 2 if scale==2 else 3), np.uint8))
        pool.append(_clean(_STD.classification(cv2.imencode('.png', mended)[1].tobytes())))
        
        # STYLE C: Native Sharpening
        sh = cv2.filter2D(scaled, -1, np.array([[0,-1,0], [-1,5,-1], [0,-1,0]]))
        pool.append(_clean(_STD.classification(cv2.imencode('.png', sh)[1].tobytes())))
        
    return [x for x in pool if x]

def solve_captcha_from_image(img):
    pool = get_best_candidates(img)
    
    # Pass 1: Global Majority (6-digit matches)
    six = [x for x in pool if len(x) == 6]
    if six:
        # Strong Consensus
        counts = Counter(six).most_common()
        if counts[0][1] >= 2:
            return counts[0][0]
        # Positional Majority (Cherry Picker)
        ans = ""
        for i in range(6):
            ans += Counter([s[i] for s in six]).most_common(1)[0][0]
        return ans

    # Pass 2: SHAPE-AWARE BLOB FALLBACK
    # Finds the actual ink clusters and slices them specifically
    scaled4 = cv2.resize(img, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    gray4 = cv2.cvtColor(scaled4, cv2.COLOR_BGR2GRAY)
    bh4 = cv2.morphologyEx(gray4, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (35,35)))
    _, clean4 = cv2.threshold(bh4, 40, 255, cv2.THRESH_BINARY)
    
    # Project Vertical
    proj = np.sum(clean4, axis=0)
    active = (proj > (np.mean(proj) * 0.4)).astype(int)
    diff = np.diff(active)
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]
    
    blobs = []
    if len(starts) == len(ends):
        for s, e in zip(starts, ends):
            # If a blob is wide enough to be two digits, split it!
            w = e - s
            if w > (clean4.shape[1] // 5): # 1.5x standard width
                blobs.append((s, s + w//2))
                blobs.append((s + w//2, e))
            else:
                blobs.append((s, e))
    
    # If we don't have exactly 6, pad or crop based on ink density
    if len(blobs) < 6:
        sw = clean4.shape[1] // 6
        blobs = [(int(i*sw), int((i+1)*sw)) for i in range(6)]
    
    final = []
    for i in range(min(6, len(blobs))):
        x1, x2 = blobs[i]
        pad = 12
        seg = cv2.bitwise_not(clean4[:, max(0, x1-pad):min(clean4.shape[1], x2+pad)])
        d = _clean(_STD.classification(cv2.imencode('.png', seg)[1].tobytes()))
        final.append(d[0] if d else "?")
        
    res = "".join(final)
    if "?" not in res and len(res) == 6: return res

    # Deep Fallback: Frequency Ranking
    if not pool: return ""
    return sorted(pool, key=lambda x: (abs(len(x)-6), -len(x)))[0]

def solve_captcha_base64(b64):
    import base64
    if ',' in b64: b64 = b64.split(',')[1]
    nparr = np.frombuffer(base64.b64decode(b64), np.uint8)
    return solve_captcha_from_image(cv2.imdecode(nparr, cv2.IMREAD_COLOR))

if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else 'captcha.png'
    if os.path.exists(path):
        print(solve_captcha_from_image(cv2.imread(path)))

def backup_solution():
    try:
        shutil.copy(r'd:\Work\project 4\project_gst_playwright\captcha_solver.py', r'd:\Work\project 4\history\captcha_solver_ultimate_v3.py')
    except: pass