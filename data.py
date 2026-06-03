BD_UNICODE = [
    [0x00e1, 0x00e0, 0x1ea3, 0x00e3, 0x1ea1, 0x0061],
    [0x1ea5, 0x1ea7, 0x1ea9, 0x1eab, 0x1ead, 0x00e2],
    [0x1eaf, 0x1eb1, 0x1eb3, 0x1eb5, 0x1eb7, 0x0103],
    [0x00e9, 0x00e8, 0x1ebb, 0x1ebd, 0x1eb9, 0x0065],
    [0x1ebf, 0x1ec1, 0x1ec3, 0x1ec5, 0x1ec7, 0x00ea],
    [0x00ed, 0x00ec, 0x1ec9, 0x0129, 0x1ecb, 0x0069],
    [0x00f3, 0x00f2, 0x1ecf, 0x00f5, 0x1ecd, 0x006f],
    [0x1ed1, 0x1ed3, 0x1ed5, 0x1ed7, 0x1ed9, 0x00f4],
    [0x1edb, 0x1edd, 0x1edf, 0x1ee1, 0x1ee3, 0x01a1],
    [0x00fa, 0x00f9, 0x1ee7, 0x0169, 0x1ee5, 0x0075],
    [0x1ee9, 0x1eeb, 0x1eed, 0x1eef, 0x1ef1, 0x01b0],
    [0x00fd, 0x1ef3, 0x1ef7, 0x1ef9, 0x1ef5, 0x0079],
]

BASE_CHARS = ['a', 'â', 'ă', 'e', 'ê', 'i', 'o', 'ô', 'ơ', 'u', 'ư', 'y']

CP_INFO: dict[int, tuple[int, int]] = {}
for _vi, _row in enumerate(BD_UNICODE):
    for _ti, _cp in enumerate(_row):
        CP_INFO[_cp] = (_vi, _ti)
        _upper_cp = ord(chr(_cp).upper())
        if _upper_cp != _cp:
            CP_INFO[_upper_cp] = (_vi, _ti)

BASE_VOWEL_SET: dict[str, int] = {
    'a': 0, 'â': 1, 'ă': 2,
    'e': 3, 'ê': 4,
    'i': 5,
    'o': 6, 'ô': 7, 'ơ': 8,
    'u': 9, 'ư': 10,
    'y': 11,
}
for _k, _v in list(BASE_VOWEL_SET.items()):
    BASE_VOWEL_SET[_k.upper()] = _v

def get_char_info(ch: str) -> tuple[int, int] | None:
    cp = ord(ch)
    if cp in CP_INFO:
        return CP_INFO[cp]
    if ch.lower() in BASE_VOWEL_SET:
        return BASE_VOWEL_SET[ch.lower()], 5
    return None

def is_vowel(ch: str) -> bool:
    return get_char_info(ch) is not None

def get_vowel_set(ch: str) -> int | None:
    info = get_char_info(ch)
    return info[0] if info else None

def get_tone(ch: str) -> int:
    info = get_char_info(ch)
    return info[1] if info else 5

def make_char(vowel_set: int, tone: int, upper: bool) -> str:
    ch = chr(BD_UNICODE[vowel_set][tone])
    return ch.upper() if upper else ch
