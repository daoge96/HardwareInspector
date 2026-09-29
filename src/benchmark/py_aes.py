"""极简纯 Python AES-256-CBC（只做首块加密），用于构造 GPU 内核自检向量。

不追求速度：每个候选只在自检时用两次。
"""
from __future__ import annotations

_SBOX = bytes.fromhex(
    "637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0"
    "b7fd9326363ff7cc34a5e5f171d8311504c723c31896059a071280e2eb27b275"
    "09832c1a1b6e5aa0523bd6b329e32f8453d100ed20fcb15b6acbbe394a4c58cf"
    "d0efaafb434d338545f9027f503c9fa851a3408f929d38f5bcb6da2110fff3d2"
    "cd0c13ec5f974417c4a77e3d645d197360814fdc222a908846eeb814de5e0bdb"
    "e0323a0a4906245cc2d3ac629195e479e7c8376d8dd54ea96c56f4ea657aae08"
    "ba78252e1ca6b4c6e8dd741f4bbd8b8a703eb5664803f60e613557b986c11d9e"
    "e1f8981169d98e949b1e87e9ce5528df8ca1890dbfe6426841992d0fb054bb16")

_RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36, 0x6C, 0xD8, 0xAB, 0x4D)


def _expand_key(key: bytes) -> bytes:
    nk = len(key) // 4
    words = 4 * (nk + 7)
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, words):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [_SBOX[b] for b in t]
            t[0] ^= _RCON[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            t = [_SBOX[b] for b in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    return bytes(b for word in w for b in word)


def _xtime(a: int) -> int:
    a <<= 1
    return (a ^ 0x1B) & 0xFF if a & 0x100 else a


def _encrypt_block(block: bytes, rk: bytes) -> bytes:
    nr = len(rk) // 16 - 1
    s = [block[i] ^ rk[i] for i in range(16)]
    for rnd in range(1, nr + 1):
        s = [_SBOX[b] for b in s]
        s = [s[0], s[5], s[10], s[15], s[4], s[9], s[14], s[3],
             s[8], s[13], s[2], s[7], s[12], s[1], s[6], s[11]]
        if rnd != nr:
            for c in range(4):
                a = s[4 * c:4 * c + 4]
                t = a[0] ^ a[1] ^ a[2] ^ a[3]
                s[4 * c + 0] = a[0] ^ t ^ _xtime(a[0] ^ a[1])
                s[4 * c + 1] = a[1] ^ t ^ _xtime(a[1] ^ a[2])
                s[4 * c + 2] = a[2] ^ t ^ _xtime(a[2] ^ a[3])
                s[4 * c + 3] = a[3] ^ t ^ _xtime(a[3] ^ a[0])
        s = [s[i] ^ rk[rnd * 16 + i] for i in range(16)]
    return bytes(s)


def aes256_cbc_first_block(plain: bytes, key: bytes, iv: bytes) -> bytes:
    """AES-256-CBC 加密，只返回第一块（16 字节）。"""
    rk = _expand_key(key)
    xored = bytes(a ^ b for a, b in zip(plain[:16], iv[:16]))
    return _encrypt_block(xored, rk)
