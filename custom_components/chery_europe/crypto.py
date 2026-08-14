"""SM4-ECB PKCS7 encryption helper for the Chery Europe login."""

from __future__ import annotations

import base64
import hashlib

from gmssl.sm4 import CryptSM4, SM4_ENCRYPT

#: Fixed 16-byte SM4 key hardcoded in the app (``SM4.createHexKey``).
#: Shared by the Chery/Omoda/Jaecoo "legend" BFF login flow.
SM4_LOGIN_KEY = b"mHU80av2zFtf4OY6"


def sm4_encrypt_ecb_pkcs7(plaintext: str, key: bytes) -> str:
    """Encrypt ``plaintext`` with SM4-ECB/PKCS7 and return base64 ciphertext."""
    cipher = CryptSM4()
    cipher.set_key(key, SM4_ENCRYPT)
    ciphertext = cipher.crypt_ecb(plaintext.encode("utf-8"))
    return base64.b64encode(ciphertext).decode("ascii")


def encrypt_command_pin(pin: str) -> str:
    """Return the SM4-encrypted command PIN used by ``checkPassword``."""
    digest = hashlib.md5(pin.encode("utf-8"), usedforsecurity=False).hexdigest()
    return sm4_encrypt_ecb_pkcs7(digest.ljust(32), SM4_LOGIN_KEY)