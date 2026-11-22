import socket
import json
import base64
import re
import threading
import time

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

latest_state = {}

# EXPECTED_UDID = "34ab95b09228"

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

    return decryptor.update(ciphertext) + decryptor.finalize()


def listener(ap_password: str):
    print("Listener function entered")
    global latest_state

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    sock.bind(("", 15951))

    print("Microtek listener started", flush=True)

    while True:
        try:
            data, addr = sock.recvfrom(4096)

            # print(f"UDP packet from {addr}", flush=True)

            packet = data.decode(errors="ignore")

            match = re.match(
                r"^\(([^|]+)\|([^|]+)\|(.+)\)$",
                packet.strip()
            )

            if not match:
                continue

            version = match.group(1)
            mac = match.group(2)
            payload = match.group(3)

            decrypted = decrypt_payload(
                payload,
                ap_password
            )

            text = decrypted.decode("ascii").rstrip("\x00")

            state = json.loads(text)

            # if state.get("udid", "").lower() != EXPECTED_UDID:
            #     continue

            state["_version"] = version
            state["_mac"] = mac
            state["_ip"] = addr[0]
            state["_received_at"] = time.time()
            state["_age"] = 0

            # print("Received Microtek state:", state)

            latest_state.clear()
            latest_state.update(state)

        except Exception as e:
            print("Microtek error:", e, flush=True)


def start_listener(password: str):
    print("Creating Microtek thread", flush=True)
    thread = threading.Thread(
        target=listener,
        args=(password,),
        daemon=True
    )
    thread.start()
    print("Thread started", flush=True)