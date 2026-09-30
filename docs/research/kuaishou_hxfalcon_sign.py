"""Pure-Python port of amagi's Kuaishou __NS_hxfalcon signer (GPL-3.0 upstream).

Ported from https://github.com/bandange/amagi-rs
  src/platforms/kuaishou/sign/{hudr,he,primitives,state}.rs
  src/platforms/kuaishou/sign/helpers/{payload,crypto,kww}.rs

================================================================================
⚠️ 状态：**未投入生产使用**（2026-09-30 实测）
================================================================================

## 本文件的定位：**算法存档**，不是可用实现

快手签名是混淆 JS（`kws-10-0.0.1-obfuscated.*.js`），本文件是
从 amagi-rs 移植的**纯 Python 算法还原** —— 它的价值在于：

  · 万一快手前端升级导致"浏览器抓签名"失效，这是**回溯算法的唯一线索**
  · 报告里的错误码表 + 接口白名单**有实用价值**（见 .md）

## 实测结论：**直接用会失败**

    本实现 generate_hxfalcon(url, count=100, script_count=24)
    → POST /rest/v/search/feed
    → HTTP 200 {"result":50,"error_msg":"**签名验证失败**"}

报告说的"逐字节验证通过"指的是**签名串与真实浏览器签名逐字节一致**，
那是**算法正确性**的证据；**不等于**"接口能返回数据"。

## 为什么没切换过去

现役方案（`platforms/kuaishou/client.py`）是
**浏览器抓一次签名 + 复用**，实测 **10 条/次可用**。

报告建议的"方案 A（纯 HTTP + 首次播种）"需要 4 个运行时常量：

    count / startup_random / script_count / secs_stack

其中**两个我抓不到真实值**（实测）：

    script_count = 0        ← 页面加载完后 document.scripts.length 是 0
    stack_tail   = "at UtilityScript.evaluate…"   ← 抓到的是**我们自己的** eval 栈

**没播种就签名失败** —— 所以现在切换会**让可用功能变不可用**。

## 若将来要用

1. 搞清那 4 个常量**在哪个时机**抓得到（可能要注入脚本、在页面加载**前**挂钩）
2. 报告提到的"方案 B（realm 劫持）"是保底：劫持 `Object.prototype.caver`
   拿到页面自己的 `$encode` realm，**只借它生成签名串**，
   数据请求仍由 httpx 发（不经过浏览器，性能好）
3. 注意报告指出的两个坑：
   · SDK 版本号**分站不同**（www 实测 `cda9`）
   · `fixed_body` 常量已漂移（amagi/falcon 都写 `0100000001`，
     实测真实值是 `0100000000`）—— 本文件已修正

详见 `kuaishou_hxfalcon_research.md`。
"""
import base64
import json
import math
import random
import struct
import time
from collections import OrderedDict
from urllib.parse import urlparse, parse_qsl

# ---------------------------------------------------------------- primitives
BLAKE2S_IV = [
    0xA54FF53A ^ 0x3C6EF372,  # placeholder replaced below
]
BLAKE2S_IV = [
    2837534710, 2845986804, 2436420605, 706843635,
    719254516, 2557931286, 2596197199, 2432949778,
]
BLAKE2S_SIGMA = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    [14, 10, 4, 8, 9, 15, 13, 6, 1, 12, 0, 2, 11, 7, 5, 3],
    [11, 8, 12, 0, 5, 2, 15, 13, 10, 14, 3, 6, 7, 1, 9, 4],
    [7, 9, 3, 1, 13, 12, 11, 14, 2, 6, 5, 10, 4, 0, 15, 8],
    [9, 0, 5, 7, 2, 4, 10, 15, 14, 1, 11, 12, 6, 8, 3, 13],
    [2, 12, 6, 10, 0, 11, 8, 3, 4, 13, 7, 5, 15, 14, 1, 9],
    [12, 5, 1, 15, 14, 13, 4, 10, 0, 7, 6, 3, 9, 2, 8, 11],
    [13, 11, 7, 14, 12, 1, 3, 9, 5, 0, 15, 4, 8, 6, 2, 10],
    [6, 15, 14, 9, 11, 3, 0, 8, 12, 2, 13, 7, 1, 4, 10, 5],
    [10, 2, 8, 4, 7, 6, 1, 5, 15, 11, 9, 14, 3, 12, 13, 0],
]
CTS_STATE_VECTOR = [
    98, 0, 0, -128, 49, 117, -71, -3, -32, -84, 104, 36, -33, -101, 87, 19,
    32, 0, 0, 64, 2, 0, 0, 16, -1, -1, -1, 127, -1, -1, -1, 63,
    0, 0, 0, -16, 0, 0, 0, -64, 0, 0, 0, -128, -1, -1, -1, 15,
]
M32 = 0xFFFFFFFF


def _rotr(v, s):
    v &= M32
    return ((v >> s) | (v << (32 - s))) & M32


def _rotl(v, s):
    v &= M32
    return ((v << s) | (v >> (32 - s))) & M32


def _to_i8(v):
    v &= 0xFF
    return v - 256 if v > 127 else v


def _to_i32(v):
    v &= M32
    return v - (1 << 32) if v >= (1 << 31) else v


def _bq(state, a, b, c, d, x, y):
    state[a] = (state[a] + state[b] + x) & M32
    state[d] = _rotr(state[d] ^ state[a], 16)
    state[c] = (state[c] + state[d]) & M32
    state[b] = _rotr(state[b] ^ state[c], 12)
    state[a] = (state[a] + state[b] + y) & M32
    state[d] = _rotr(state[d] ^ state[a], 8)
    state[c] = (state[c] + state[d]) & M32
    state[b] = _rotr(state[b] ^ state[c], 7)


def _blake2s_compress(h, words, offset, counter, length, is_last):
    work = [0] * 16
    block = [0] * 16
    for i in range(8):
        work[i] = h[i]
        work[i + 8] = BLAKE2S_IV[i]
    work[12] = (work[12] ^ counter) & M32
    if is_last:
        work[14] = (work[14] ^ M32) & M32
    for i in range(length):
        block[i % 16] = (block[i % 16] ^ words[offset + i]) & M32
    for sigma in BLAKE2S_SIGMA:
        _bq(work, 0, 4, 8, 12, block[sigma[0]], block[sigma[1]])
        _bq(work, 1, 5, 9, 13, block[sigma[2]], block[sigma[3]])
        _bq(work, 2, 6, 10, 14, block[sigma[4]], block[sigma[5]])
        _bq(work, 3, 7, 11, 15, block[sigma[6]], block[sigma[7]])
        _bq(work, 0, 5, 10, 15, block[sigma[8]], block[sigma[9]])
        _bq(work, 1, 6, 11, 12, block[sigma[10]], block[sigma[11]])
        _bq(work, 2, 7, 8, 13, block[sigma[12]], block[sigma[13]])
        _bq(work, 3, 4, 9, 14, block[sigma[14]], block[sigma[15]])
    for i in range(8):
        h[i] = (h[i] ^ work[i] ^ work[i + 8]) & M32


def derive_b2has(value: str) -> str:
    raw = value.encode("utf-8")
    pad = 0 if len(raw) % 4 == 0 else 4 - (len(raw) % 4)
    padded = raw + b"\x00" * pad
    words = [struct.unpack_from("<I", padded, i)[0] for i in range(0, len(padded), 4)]

    h = list(BLAKE2S_IV)
    h[0] = (h[0] ^ 16842784) & M32
    offset = 0
    length = len(words)
    counter = 0
    while length > 64:
        length -= 64
        counter = (counter + 64) & M32
        _blake2s_compress(h, words, offset, counter, 64, False)
        offset += 64
    _blake2s_compress(h, words, offset, (counter + length) & M32, length, True)
    return "".join("%08x" % w for w in h)


def _read_i32_le(b, i):
    return struct.unpack_from("<i", bytes([x & 0xFF for x in b[i:i + 4]]), 0)[0]


class CtsState:
    def __init__(self):
        v = CTS_STATE_VECTOR
        self.s = _read_i32_le(v, 12)
        self.u = _read_i32_le(v, 8)
        self.c = _read_i32_le(v, 4)
        self.l = _read_i32_le(v, 0)
        self.p = _read_i32_le(v, 16)
        self.f = _read_i32_le(v, 20)
        self.d = _read_i32_le(v, 24)
        self.y = _read_i32_le(v, 28)
        self.h = _read_i32_le(v, 44)
        self.e = _read_i32_le(v, 40)
        self.m = _read_i32_le(v, 36)
        self.b = _read_i32_le(v, 32)


def _shl32(v, n):
    v &= M32
    return (v << n) & M32


def _shr32(v, n):
    return (v & M32) >> n


def _seed_cts(st, seed):
    chars = [ord(ch) & 0xFF for ch in seed]
    for i in range(4):
        val = chars[i + 4]
        st.s = _shl32(st.s, 8) | val
        st.u = _shl32(st.u, 8) | val
        st.c = _shl32(st.c, 8) | val
    if st.s == 0:
        st.s = 324508639
    if st.u == 0:
        st.u = 610839776
    if st.c == 0:
        st.c = _to_i32(4256789809)


def _cts_byte(st, value):
    result = 0
    right_bit = st.u & 1
    left_bit = st.c & 1
    for _ in range(8):
        if st.s & 1 != 0:
            st.s = _to_i32((st.s ^ _shr32(st.l, 1)) | st.e)
            if st.u & 1 != 0:
                st.u = _to_i32((st.u ^ _shr32(st.p, 1)) | st.m)
                right_bit = 1
            else:
                st.u = _to_i32(_shr32(st.u, 1) & st.y)
                right_bit = 0
        else:
            st.s = _to_i32(_shr32(st.s, 1) & st.d)
            if st.c & 1 != 0:
                st.c = _to_i32((st.c ^ _shr32(st.f, 1)) | st.b)
                left_bit = 1
            else:
                st.c = _to_i32(_shr32(st.c, 1) & st.h)
                left_bit = 0
        mixed = _shl32(result, 1) | (right_bit ^ left_bit)
        if mixed > 127:
            mixed -= 256
        elif mixed < -128:
            mixed += 256
        result = mixed
    return _to_i8(value ^ (result + 3))


def derive_cts(inp):
    st = CtsState()
    _seed_cts(st, "Vuz4fCHxn1CO")
    return [_cts_byte(st, b) for b in inp]


def bytes_to_lower_hex(bs):
    return "".join("%02x" % (b & 0xFF) for b in bs)


def hex_to_signed_bytes(h):
    return [_to_i8(int(h[i:i + 2], 16)) for i in range(0, len(h) - len(h) % 2, 2)]


def xor_byte_arrays(left, right):
    return [_to_i8(left[i] ^ (right[i % len(right)] & 0xFF)) for i in range(len(left))]


def to_le_hex(value, size):
    return "".join("%02x" % ((value >> (8 * i)) & 0xFF) for i in range(size))


def lrc_hex(src_hex):
    total = sum(b & 0xFF for b in hex_to_signed_bytes(src_hex))
    return "%02x" % ((-total) & 0xFF)


def transform_he_hex(prefix_hex, checksum_hex):
    inp = hex_to_signed_bytes(prefix_hex + checksum_hex)
    if not inp:
        return ""
    key = inp[-1]
    out = [_to_i8(inp[i] ^ key) for i in range(len(inp) - 1)] + [key]
    return bytes_to_lower_hex(out)


# ------------------------------------------------------------------- HUDR
HUDR_PREFIX = "HUDR_"
HUDR_MASK = 35
HUDR_CHACHA_KEY = [
    4183807412, 394484062, 1106561997, 2378328696,
    630790222, 2546784104, 2891127470, 1922531795,
]
HUDR_CHACHA_NONCE = [2215853858, 1643070585, 1849059804]


def _chacha_quarter(st, a, b, c, d):
    st[a] = (st[a] + st[b]) & M32
    st[d] = _rotl(st[d] ^ st[a], 16)
    st[c] = (st[c] + st[d]) & M32
    st[b] = _rotl(st[b] ^ st[c], 12)
    st[a] = (st[a] + st[b]) & M32
    st[d] = _rotl(st[d] ^ st[a], 8)
    st[c] = (st[c] + st[d]) & M32
    st[b] = _rotl(st[b] ^ st[c], 7)


class ChaCha:
    def __init__(self, key, nonce):
        self.key, self.nonce = key, nonce

    def _block(self, state):
        w = list(state)
        for _ in range(0, 20, 2):
            _chacha_quarter(w, 0, 4, 8, 12)
            _chacha_quarter(w, 1, 5, 9, 13)
            _chacha_quarter(w, 2, 6, 10, 14)
            _chacha_quarter(w, 3, 7, 11, 15)
            _chacha_quarter(w, 0, 5, 10, 15)
            _chacha_quarter(w, 1, 6, 11, 12)
            _chacha_quarter(w, 2, 7, 8, 13)
            _chacha_quarter(w, 3, 4, 9, 14)
        return [(w[i] + state[i]) & M32 for i in range(16)]

    def encrypt(self, data):
        state = [0] * 16
        state[0], state[1], state[2], state[3] = 394484062, 2378328696, 630790222, 1922531795
        for i in range(8):
            state[i + 4] = self.key[i]
        state[12] = 1
        state[13], state[14], state[15] = self.nonce
        mixed = self._block(state)
        out = bytearray()
        word_index = 0
        for val in data:
            if word_index == 64:
                state[12] = (state[12] + 1) & M32
                mixed = self._block(state)
                word_index = 0
            w = mixed[word_index >> 2]
            ks = (w >> ((word_index & 3) << 3)) & 0xFF
            word_index += 1
            out.append(val ^ ks)
        return bytes(out)


def _b64_url(bs):
    return base64.b64encode(bs).decode().replace("+", "-").replace("/", "_").replace("=", ".")


def hudr_info_cache(script_count):
    return bytes([68, 0]) + bytes((script_count >> (8 * i)) & 0xFF for i in range(4))


def build_hudr_payload(count, script_count, secs_s, secs_c):
    payload = bytearray([45, 61, 0, 2])
    payload += hudr_info_cache(script_count)
    payload += bytes([112, 0])
    payload += bytes((count >> (8 * i)) & 0xFF for i in range(4))
    payload += bytes([114, 1])
    tail_len = len(secs_s.encode("utf-16-le")) // 2
    payload += bytes((tail_len >> (8 * i)) & 0xFF for i in range(2))
    payload += bytes(ord(ch) & 0xFF for ch in secs_s)
    payload += bytes([115, 0])
    payload += bytes((secs_c >> (8 * i)) & 0xFF for i in range(4))
    return bytes(payload)


def derive_hudr(count, script_count, secs_s, secs_c):
    payload = build_hudr_payload(count, script_count, secs_s, secs_c)
    masked = bytes(HUDR_MASK ^ b for b in payload)
    enc = ChaCha(HUDR_CHACHA_KEY, HUDR_CHACHA_NONCE).encrypt(masked)
    body = _b64_url(enc)
    return body, HUDR_PREFIX + body


# --------------------------------------------------------------------- HE
HE_HEADER = "4B54"
HE_VERSION = "cda9"
HE_STARTUP_MARKER = "ab"
HE_FIXED_BODY = "0100000000"
HE_INPUT_XOR_MASK = [45, 211, 69, 192]
HE_COUNTER_XOR_MASK = 3131873467
HE_TIME_XOR_MASK = 3360347992
HE_TAIL = "9b563eda7b563e"
HE_RANDOM_MAX = 281474976710655


def derive_he_hash_field(sign_input, hudr_body):
    hash_input = sign_input + "HUDR_" + hudr_body
    digest_hex = bytes_to_lower_hex(derive_cts(derive_b2has(hash_input).encode("latin-1")))
    return bytes_to_lower_hex(xor_byte_arrays(hex_to_signed_bytes(digest_hex[:8]), HE_INPUT_XOR_MASK))


def derive_he(count, hudr_body, random_value, sign_input, startup_random, timestamp):
    random48 = int(math.floor(random_value * HE_RANDOM_MAX))
    hash_field = derive_he_hash_field(sign_input, hudr_body)
    time_xor = timestamp ^ HE_TIME_XOR_MASK
    pre_hex = "".join([
        HE_HEADER, HE_VERSION, HE_STARTUP_MARKER,
        to_le_hex(startup_random, 6), to_le_hex(random48, 6),
        HE_FIXED_BODY, to_le_hex(count ^ HE_COUNTER_XOR_MASK, 4),
        hash_field, to_le_hex(time_xor, 6), HE_TAIL, lrc_hex(HE_TAIL),
    ])
    return transform_he_hex(pre_hex, lrc_hex(pre_hex))


# ------------------------------------------------------------ sign input
def build_sign_input(url):
    parsed = urlparse(url)
    query = OrderedDict(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    params = [f"{k}={v}" for k, v in query.items() if "__NS" not in k]
    params.sort()
    return parsed.path + "".join(params)


def generate_hxfalcon(url, count=100, script_count=0, stack=None,
                      startup_random=None, cat_version="2"):
    sign_input = build_sign_input(url)
    if stack is None:
        stack = ""
    stack_tail = stack[-100:]
    startup_random = startup_random if startup_random is not None else int(time.time() * 1000)
    ts = int(time.time() * 1000)
    rv = random.random()
    body, full = derive_hudr(count, script_count, stack_tail, count)
    he = derive_he(count, body, rv, sign_input, startup_random, ts)
    return full + "$HE_" + he, sign_input, cat_version


if __name__ == "__main__":
    u = ("https://www.kuaishou.com/rest/v/search/feed?caver=2")
    sig, si, cv = generate_hxfalcon(u)
    print("sign_input:", si)
    print("signature :", sig)
