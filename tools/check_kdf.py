# -*- coding: utf-8 -*-
"""对拍：本项目的 CPU KDF 实现 vs 硬解密码.py 的 first_iterate。"""
import hashlib, importlib.util, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.benchmark.crypto_bench import kdf_sha512, SALT

spec = importlib.util.spec_from_file_location("bcrack", r"D:\OneDrive\Desktop\硬解密码.py")
bc = importlib.util.module_from_spec(spec); spec.loader.exec_module(bc)

ok = True
for pw in ("000000", "999999", "abc123"):
    for spin in (0, 1, 7, 1000):
        mine = kdf_sha512(pw, SALT, spin)
        ref = bc.first_iterate(pw, SALT, spin, hashlib.sha512)
        same = mine == ref
        ok &= same
        if not same:
            print("MISMATCH", pw, spin, mine.hex()[:16], ref.hex()[:16])
print("kdf_sha512 与参考实现一致:", ok)
