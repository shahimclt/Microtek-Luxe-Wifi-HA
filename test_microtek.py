import base64
import json

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def generate16_byte_key(password: str) -> bytes:
    if len(password) == 16:
        key = password
    elif len(password) > 16:
        key = password[:16]
    else:
        key = password + ("\0" * (16 - len(password)))
    return key.encode("utf-8")


def decrypt_payload(b64_payload: str, password: str) -> bytes:
    decoded = base64.b64decode(b64_payload)
    iv = decoded[:16]
    ciphertext = decoded[16:]
    key = generate16_byte_key(password)
    decryptor = Cipher(
        algorithms.AES(key),
        modes.CBC(iv)
    ).decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    return plaintext


def try_parse_json(data: bytes):
    try:
        # Java converts directly to ASCII without trimming
        text = data.decode("ascii")
        # JSON parser may choke on trailing NULs
        text_clean = text.rstrip("\x00")
        return json.loads(text_clean)
    except Exception as e:
        return f"JSON parse failed: {e}"


if __name__ == "__main__":
    wifi_password = input("WiFi password: ").strip()
    print("\nPaste the Base64 payload only")
    print("(everything after the second | and before the closing ))\n")
    payload = input("Payload: ").strip()
    decrypted = decrypt_payload(payload, wifi_password)
    print("\n=== RAW HEX ===")
    print(decrypted.hex())
    print("\n=== ASCII ===")
    try:
        print(decrypted.decode("ascii"))
    except Exception as e:
        print(f"ASCII decode failed: {e}")
    print("\n=== JSON ===")
    result = try_parse_json(decrypted)
    print(json.dumps(result, indent=2) if isinstance(result, dict) else result)