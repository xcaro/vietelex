from data import is_vowel, get_vowel_set, BASE_CHARS

INVALID_CHARS_IN_WORD = frozenset('fjzw')

INVALID_ONSET_CLUSTERS = frozenset([

    'bl', 'cl', 'fl', 'gl', 'pl', 'sl',
    'br', 'cr', 'dr', 'fr', 'gr', 'pr',
    'sc', 'sk', 'sm', 'sn', 'sp', 'st', 'sw',
    'tw', 'dw', 'kn', 'gn', 'wr',
    'sh',

    'str', 'spr', 'scr', 'spl', 'thr', 'shr', 'chr',
])

INVALID_CODA_CLUSTERS = frozenset([

    'st', 'sk', 'nd', 'ld', 'lf', 'lk', 'lm', 'lp',
    'mp', 'mt', 'nk', 'nt', 'rd', 'rk', 'rl', 'rm',
    'rn', 'rp', 'rs', 'rt', 'ts', 'ks', 'ft', 'ct',
    'gh',

    'br', 'cr', 'dr', 'fr', 'gr', 'pr',
    'bl', 'cl', 'fl', 'gl', 'pl', 'sl',
    'sc', 'sm', 'sn', 'sp', 'sw',
    'tw', 'dw', 'kn', 'gn', 'wr', 'sh',
])

INVALID_CODA_SINGLE = frozenset(['s', 'z', 'f', 'l', 'r', 'v', 'x', 'j', 'w', 'b', 'd'])

INVALID_VOWEL_SEQS = frozenset([
    'ae', 'ea',
    'ei', 'eu', 'ey',
    'ii', 'iy',
    'ou', 'oy',
    'yi', 'yo', 'yu', 'yy',

])

class VietnamesePhonologyValidator:

    def is_valid_context(self, buf: list[str], upper: list[bool]) -> bool:
        word_start = self._find_word_start(buf)
        word = [c.lower() for c in buf[word_start:]]

        if not word:
            return True

        if self._has_invalid_chars(word):
            return False

        if self._has_invalid_onset(word):
            return False

        if self._has_invalid_vowel_seq(word):
            return False

        if self._has_multi_syllable_structure(word):
            return False

        coda = self._get_coda(word)
        if self._is_invalid_coda(coda):
            return False

        return True

    def _find_word_start(self, buf: list[str]) -> int:
        for i in range(len(buf) - 1, -1, -1):
            ch = buf[i]
            if not ch.isalpha() and ch not in ('đ', 'Đ'):
                return i + 1
        return 0

    def _has_invalid_vowel_seq(self, word: list[str]) -> bool:
        current = ''
        for ch in word:
            if is_vowel(ch):
                vs = get_vowel_set(ch)
                base = BASE_CHARS[vs] if vs is not None else ch
                current += base
            else:
                current = ''
                continue
            if len(current) >= 2 and current[-2:] in INVALID_VOWEL_SEQS:
                return True

            if current[-2:] == 'ye' and len(current) >= 3 and current[-3] != 'u':
                return True
        return False

    def _has_invalid_chars(self, word: list[str]) -> bool:
        return any(c in INVALID_CHARS_IN_WORD for c in word)

    def _has_invalid_onset(self, word: list[str]) -> bool:
        onset = ''
        for ch in word:
            if is_vowel(ch) or ch == 'đ':
                break
            onset += ch

        if not onset:
            return False

        if len(onset) >= 3 and onset[:3] in INVALID_ONSET_CLUSTERS:
            return True

        if len(onset) >= 2 and onset[:2] in INVALID_ONSET_CLUSTERS:
            return True
        return False

    def _has_multi_syllable_structure(self, word: list[str]) -> bool:
        in_vowel_group = False
        vowel_group_count = 0
        for ch in word:
            if is_vowel(ch):
                if not in_vowel_group:
                    vowel_group_count += 1
                    if vowel_group_count >= 2:
                        return True
                    in_vowel_group = True
            else:
                in_vowel_group = False
        return False

    def _get_coda(self, word: list[str]) -> str:
        last_vowel_idx = -1
        for i, ch in enumerate(word):
            if is_vowel(ch):
                last_vowel_idx = i
        if last_vowel_idx == -1:
            return ''
        return ''.join(word[last_vowel_idx + 1:])

    def _is_invalid_coda(self, coda: str) -> bool:
        if not coda:
            return False
        if len(coda) == 1:
            return coda in INVALID_CODA_SINGLE

        if coda in ('ng', 'nh', 'ch'):
            return False

        if len(coda) >= 3:
            return True

        if coda[0] == coda[1]:
            return True

        if coda[-1] in INVALID_CODA_SINGLE:
            return True
        return coda in INVALID_CODA_CLUSTERS