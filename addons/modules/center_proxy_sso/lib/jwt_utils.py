# -*- coding: utf-8 -*-
"""Verify HS256 JWT without PyJWT (stdlib only)."""
import base64
import hashlib
import hmac
import json
import time


class JwtError(Exception):
    pass


def _b64url_decode(segment):
    padding = "=" * ((4 - len(segment) % 4) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def verify_hs256(token, secret):
    """Return payload dict if signature and exp are valid."""
    if not token or not secret:
        raise JwtError("Thiếu token hoặc secret")

    parts = token.split(".")
    if len(parts) != 3:
        raise JwtError("JWT không hợp lệ")

    header_b64, payload_b64, sig_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
        signature = _b64url_decode(sig_b64)
    except (ValueError, json.JSONDecodeError) as exc:
        raise JwtError("JWT không parse được") from exc

    if header.get("alg") != "HS256":
        raise JwtError("Chỉ hỗ trợ HS256")

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise JwtError("Chữ ký JWT không hợp lệ")

    exp = payload.get("exp")
    if exp is not None:
        try:
            if float(exp) < time.time():
                raise JwtError("JWT đã hết hạn")
        except (TypeError, ValueError) as exc:
            raise JwtError("JWT exp không hợp lệ") from exc

    return payload
