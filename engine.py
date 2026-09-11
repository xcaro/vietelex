from data import (
    BASE_CHARS, BASE_VOWEL_SET,
    get_char_info, get_vowel_set, get_tone, make_char, is_vowel,
)
from validator import VietnamesePhonologyValidator

TELEX_TONES = {'s': 0, 'f': 1, 'r': 2, 'x': 3, 'j': 4, 'z': 5}

DOUBLE_VOWEL = {
    'a': (0, 1),
    'e': (3, 4),
    'o': (6, 7),
}

TELEX_BREVE     = {0: 2, 6: 8, 7: 8, 9: 10}
TELEX_BREVE_REV = {2: 0, 8: 6, 10: 9}

MAX_MODIFY_LEN  = 6
MAX_AFTER_VOWEL = 2
MAX_VOWEL_SEQ   = 3

def _is_ascii_letter(ch: str) -> bool:
    return ord(ch) < 128 and ch.isalpha()

class VietelexEngine:

    def __init__(self, validator_enabled: bool = True):
        self.buf:   list[str]  = []
        self.upper: list[bool] = []
        self._w_undo = None
        self.last_w_converted  = False
        self.temp_viet_off     = False
        self._validator = VietnamesePhonologyValidator() if validator_enabled else None

    def clear(self):
        self._w_undo = None
        self.buf.clear()
        self.upper.clear()
        self.last_w_converted = False
        self.temp_viet_off    = False

    def set_validator_enabled(self, enabled: bool):
        self._validator = VietnamesePhonologyValidator() if enabled else None
        self.clear()

    def backspace(self):
        self._w_undo = None
        if self.buf:
            self.buf.pop()
            self.upper.pop()
        self.last_w_converted = False
        self.temp_viet_off = False

    def notify_deleted(self, n: int = -1) -> None:
        if n == 0:
            return
        self._w_undo = None
        if n < 0 or n >= len(self.buf):
            self.clear()
        else:
            del self.buf[-n:]
            del self.upper[-n:]
            self.last_w_converted = False
            self.temp_viet_off = False

    def _put_char(self, ch: str):
        self.buf.append(ch)
        self.upper.append(ch != ch.lower() and ch.isalpha())

    def result_str(self) -> str:
        return ''.join(self.buf)

    def process(self, ch: str) -> tuple[int, str]:
        lo    = ch.lower()
        if lo != 'w':
            self._w_undo = None
        is_up = (ch != ch.lower() and ch.isalpha())

        if self.temp_viet_off:
            if not ch.isalpha():
                self.clear()
                return 0, ch
            self._put_char(ch)
            return 0, ch

        if not ch.isalpha() and ch not in TELEX_TONES:
            self.clear()
            return 0, ch

        if lo == 'd':
            r = self._double_d(is_up)
            if r is not None:
                return r

        if lo == 'w':
            return self._handle_w(is_up)

        if lo in DOUBLE_VOWEL:
            r = self._double_char(lo, is_up, ch)
            if r is not None:
                return r

        if lo in TELEX_TONES:
            r = self._put_tone_mark(TELEX_TONES[lo], ch, is_up)
            if r is not None:
                return r

        self._put_char(ch)
        return 0, ch

    def _handle_w(self, is_up: bool) -> tuple[int, str]:
        w_ch = 'W' if is_up else 'w'

        if self._w_undo is not None:
            previous = self._w_undo
            self._w_undo = None
            start = next(i for i, (old, new) in enumerate(zip(previous, self.buf)) if old != new)
            backs = len(self.buf) - start
            self.buf[:] = previous
            self._put_char(w_ch)
            self.last_w_converted = False
            self.temp_viet_off = True
            return backs, ''.join(self.buf[start:])

        previous = self.buf.copy()
        backs, ins = self._put_breve_mark(is_up)
        if backs > 0 or ins.lower() != 'w':
            if not self.temp_viet_off:
                self._w_undo = previous
            self.last_w_converted = True
            return backs, ins

        self.last_w_converted = False
        self._put_char(w_ch)
        return 0, w_ch

    def _put_breve_mark(self, is_up: bool) -> tuple[int, str]:

        if self._validator and not self._validator.is_valid_context(self.buf, self.upper):
            w_ch = 'W' if is_up else 'w'
            return 0, w_ch

        n = len(self.buf)
        w_ch = 'W' if is_up else 'w'
        if n == 0:
            return 0, w_ch

        left_most = max(0, n - MAX_MODIFY_LEN)
        i = n - 1

        while i >= left_most:
            ch_i = self.buf[i]
            vs = get_vowel_set(ch_i)
            if vs is None:
                if not ch_i.isalpha():
                    break
                i -= 1
                continue
            base_vs = TELEX_BREVE_REV.get(vs, vs)
            if base_vs in TELEX_BREVE:
                break
            i -= 1

        if i < left_most:
            return 0, w_ch

        vs = get_vowel_set(self.buf[i])
        if vs is None:
            return 0, w_ch
        base_vs = TELEX_BREVE_REV.get(vs, vs)
        if base_vs not in TELEX_BREVE:
            return 0, w_ch

        def base_char(j: int) -> str:
            v = get_vowel_set(self.buf[j])
            if v is None:
                return self.buf[j].lower()
            return BASE_CHARS[TELEX_BREVE_REV.get(v, v)]

        if i > 0:

            if base_char(i) == 'u' and base_char(i - 1) in ('o', 'u'):
                i -= 1
                vs      = get_vowel_set(self.buf[i])
                base_vs = TELEX_BREVE_REV.get(vs, vs) if vs is not None else None

            if i > 0 and base_char(i - 1) == 'u':
                not_after_q = (i < 2) or (self.buf[i - 2].lower() != 'q')
                if not_after_q:
                    bc = base_char(i)
                    if bc == 'a' or (bc == 'o' and i != n - 1):
                        i -= 1
                        vs      = get_vowel_set(self.buf[i])
                        base_vs = TELEX_BREVE_REV.get(vs, vs) if vs is not None else None

        if i < left_most or vs is None:
            return 0, w_ch
        base_vs = TELEX_BREVE_REV.get(vs, vs)
        if base_vs not in TELEX_BREVE:
            return 0, w_ch

        target_vs = TELEX_BREVE[base_vs]
        tone  = get_tone(self.buf[i])
        up_i  = self.upper[i]

        if vs == base_vs:

            if base_vs == 9 and i + 1 < n:
                next_vs   = get_vowel_set(self.buf[i + 1])
                next_base = TELEX_BREVE_REV.get(next_vs, next_vs) if next_vs is not None else None
                not_after_q = (i < 1) or (self.buf[i - 1].lower() != 'q')
                if next_base == 6 and not_after_q:
                    tone_u = get_tone(self.buf[i])
                    tone_o = get_tone(self.buf[i + 1])
                    self.buf[i]     = make_char(TELEX_BREVE[9], tone_u, self.upper[i])
                    self.buf[i + 1] = make_char(TELEX_BREVE[6], tone_o, self.upper[i + 1])
                    backs = n - i
                    return backs, ''.join(self.buf[i:])

            if base_vs == 6 and i > 0:
                prev_vs   = get_vowel_set(self.buf[i - 1])
                prev_base = TELEX_BREVE_REV.get(prev_vs, prev_vs) if prev_vs is not None else None
                not_after_q = (i < 2) or (self.buf[i - 2].lower() != 'q')
                if prev_base == 9 and not_after_q:
                    tone_u = get_tone(self.buf[i - 1])
                    tone_o = get_tone(self.buf[i])
                    self.buf[i - 1] = make_char(TELEX_BREVE[9], tone_u, self.upper[i - 1])
                    self.buf[i]     = make_char(TELEX_BREVE[6], tone_o, self.upper[i])
                    backs = n - (i - 1)
                    return backs, ''.join(self.buf[i - 1:])

            self.buf[i] = make_char(target_vs, tone, up_i)
            backs = n - i
            return backs, ''.join(self.buf[i:])
        else:

            self.buf[i] = make_char(base_vs, tone, up_i)
            self._put_char(w_ch)
            self.temp_viet_off = True
            backs = n - i
            return backs, ''.join(self.buf[i:])

    def _double_char(self, lo: str, is_up: bool, ch: str):

        if self._validator and not self._validator.is_valid_context(self.buf, self.upper):
            return None

        n = len(self.buf)
        if n == 0:
            return None

        src_vs, target_vs = DOUBLE_VOWEL[lo]
        left_most = max(0, n - MAX_MODIFY_LEN)
        i = n - 1

        while i >= left_most:
            vs_i = get_vowel_set(self.buf[i])
            if vs_i is None:
                ch_i = self.buf[i]
                if not ch_i.isalpha():
                    break
                i -= 1
                continue
            if vs_i in (src_vs, target_vs):
                break

            if vs_i in (5, 11):
                i -= 1
                continue

            break

        if i < left_most:
            return None

        vs_i = get_vowel_set(self.buf[i])
        if vs_i not in (src_vs, target_vs):

            if self.last_w_converted:
                if lo == 'a' and vs_i == 2:
                    tone_i = get_tone(self.buf[i])
                    up_i   = self.upper[i]
                    self.buf[i] = make_char(1, tone_i, up_i)
                    backs = n - i
                    return backs, ''.join(self.buf[i:])
                if lo == 'o' and vs_i == 8:
                    tone_i = get_tone(self.buf[i])
                    up_i   = self.upper[i]
                    self.buf[i] = make_char(7, tone_i, up_i)
                    backs = n - i
                    return backs, ''.join(self.buf[i:])
            return None

        if lo == 'o' and i < n - 1:
            next_vs = get_vowel_set(self.buf[i + 1])
            if next_vs is not None and BASE_CHARS[next_vs] == 'e':
                return None

        tone_i = get_tone(self.buf[i])
        up_i   = self.upper[i]

        if vs_i == src_vs:
            new_ch = make_char(target_vs, tone_i, up_i)
            self.buf[i] = new_ch
            start = i

            if i > 0 and target_vs in (1, 2):
                prev_vs = get_vowel_set(self.buf[i - 1])
                if prev_vs is not None:
                    prev_base = TELEX_BREVE_REV.get(prev_vs, prev_vs)
                    prev_tone = get_tone(self.buf[i - 1])
                    if prev_base == 9 and prev_tone != 5:
                        self.buf[i - 1] = make_char(prev_base, 5, self.upper[i - 1])
                        self.buf[i]     = make_char(target_vs, prev_tone, up_i)
                        start = i - 1
            backs = n - start
            return backs, ''.join(self.buf[start:])
        else:

            restore = make_char(src_vs, tone_i, up_i)
            self.buf[i] = restore
            rep = ch.upper() if is_up else ch
            self._put_char(rep)
            self.temp_viet_off = True
            backs = n - i
            return backs, ''.join(self.buf[i:])

    def _double_d(self, is_up: bool):

        if self._validator and not self._validator.is_valid_context(self.buf, self.upper):
            return None

        n = len(self.buf)
        if n == 0:
            return None

        left_most = max(0, n - MAX_MODIFY_LEN)
        i = n - 1

        while i >= left_most:
            ch = self.buf[i]
            if ch in ('đ', 'Đ'):
                return None
            if not ch.isalpha():
                return None
            if ch.lower() == 'd' and get_char_info(ch) is None:
                break
            i -= 1

        if i < left_most:
            return None

        word_start = i
        while word_start > 0 and self.buf[word_start - 1].isalpha() and self.buf[word_start - 1] not in ('đ', 'Đ'):
            word_start -= 1
        for k in range(word_start, i):
            if is_vowel(self.buf[k]):
                return None

        up_d = self.upper[i]
        new_ch = 'Đ' if up_d else 'đ'
        self.buf[i] = new_ch
        self.upper[i] = up_d
        backs = n - i
        return backs, ''.join(self.buf[i:])

    def _put_tone_mark(self, tone_idx: int, orig_key: str, is_up: bool):

        if self._validator and not self._validator.is_valid_context(self.buf, self.upper):
            return None

        pos = self._find_tone_pos()
        if pos == -1:
            return None

        vs = get_vowel_set(self.buf[pos])
        if vs is None:
            return None

        cur_tone = get_tone(self.buf[pos])
        n = len(self.buf)

        if cur_tone == tone_idx:

            self.buf[pos] = make_char(vs, 5, self.upper[pos])
            self._put_char(orig_key)
            self.temp_viet_off = True
            backs = n - pos
            return backs, ''.join(self.buf[pos:])

        self.buf[pos] = make_char(vs, tone_idx, self.upper[pos])
        backs = n - pos
        return backs, ''.join(self.buf[pos:])

    def _find_tone_pos(self) -> int:
        buf = self.buf
        n   = len(buf)
        if n == 0:
            return -1

        i = n - 1

        left_most = max(n - MAX_MODIFY_LEN, 0)
        while i >= left_most:
            if is_vowel(buf[i]):
                break
            i -= 1
        if i < left_most or not is_vowel(buf[i]):
            return -1
        cuoi = i

        left_most2 = max(cuoi - MAX_VOWEL_SEQ + 1, 0)
        i = cuoi
        while i > left_most2 and is_vowel(buf[i - 1]):
            prev_ch = buf[i - 1]
            if not _is_ascii_letter(prev_ch):
                i -= 1
                break
            i -= 1
        vowel_start = i

        if not is_vowel(buf[vowel_start]):
            return cuoi

        l = cuoi - vowel_start + 1
        has_final = (n > cuoi + 1)

        if l == 1:
            return cuoi

        if l == 2:
            if vowel_start > 0:
                t = buf[vowel_start - 1].upper()
                if t == 'Q':
                    return cuoi
                vs0 = get_vowel_set(buf[vowel_start])
                if t == 'G' and vs0 is not None and BASE_CHARS[vs0] == 'i':
                    return cuoi
            vs_s = get_vowel_set(buf[vowel_start])
            vs_e = get_vowel_set(buf[cuoi])
            if vs_s is not None and vs_e is not None:
                b_s = TELEX_BREVE_REV.get(vs_s, vs_s)
                b_e = TELEX_BREVE_REV.get(vs_e, vs_e)

                if b_s == 9 and b_e == 6:
                    return cuoi

                if b_s == 9 and vs_e == 7:
                    return cuoi

                if vs_s == 9 and b_e in (1, 2):
                    return cuoi

                if b_s == 6 and b_e in (0, 3):
                    return cuoi

                if b_s == 9 and b_e == 11:
                    return cuoi

                if b_s in (5, 11, 9) and b_e == 4:
                    return cuoi
            if not _is_ascii_letter(buf[vowel_start]):
                return vowel_start
            return cuoi if has_final else vowel_start

        if l == 3:

            vs_e = get_vowel_set(buf[cuoi])
            if vs_e is not None and TELEX_BREVE_REV.get(vs_e, vs_e) == 4:
                return cuoi
            return vowel_start + 1

        return cuoi
