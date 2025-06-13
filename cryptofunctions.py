from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import os
import base64
import binascii

def derive_key(password: str, salt: bytes) -> bytes:
    # Derive a 256-bit AES key from the password and salt
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,  # 256 bits key
        salt=salt,
        iterations=100_000,
        backend=default_backend()
    )
    return kdf.derive(password.encode())

def encrypt(plaintext: str, password: str) -> str:
    salt = os.urandom(16)  # Random salt for key derivation
    key = derive_key(password, salt)

    iv = os.urandom(16)  # Initialization vector for AES CBC
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()

    # Pad plaintext to be multiple of 16 bytes (PKCS7 padding)
    padding_length = 16 - (len(plaintext.encode()) % 16)
    padded_plaintext = plaintext.encode() + bytes([padding_length] * padding_length)

    ciphertext = encryptor.update(padded_plaintext) + encryptor.finalize()

    # Return base64 encoded string containing salt + iv + ciphertext
    encrypted_data = base64.b64encode(salt + iv + ciphertext).decode()
    return encrypted_data

def decrypt(encrypted_data: str, password: str) -> str:
    decoded = base64.b64decode(encrypted_data)

    salt = decoded[:16]
    iv = decoded[16:32]
    ciphertext = decoded[32:]

    key = derive_key(password, salt)

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    # Remove PKCS7 padding
    padding_length = padded_plaintext[-1]
    plaintext = padded_plaintext[:-padding_length].decode()
    return plaintext

def compute_crc(data: str) -> str:
    crc = binascii.crc_hqx(data.encode('utf-8'), 0xFFFF)
    return f"{crc:04X}"  # 4 hex digits

def verify_crc(data: str, crc_hex: str) -> bool:
    computed_crc = compute_crc(data)
    return computed_crc.upper() == crc_hex.upper()

def hamming_encode_4bit(nibble):
    G = [
        [1, 1, 0, 1],
        [1, 0, 1, 1],
        [1, 0, 0, 0],
        [0, 1, 1, 1],
        [0, 1, 0, 0],
        [0, 0, 1, 0],
        [0, 0, 0, 1],
    ]
    bits = [(nibble >> i) & 1 for i in range(3, -1, -1)]
    encoded = [(sum(bits[j] * G[i][j] for j in range(4)) % 2) for i in range(7)]
    return ''.join(map(str, encoded))

def hamming_decode_7bit(bits):
    H = [
        [1, 0, 1, 0, 1, 0, 1],
        [0, 1, 1, 0, 0, 1, 1],
        [0, 0, 0, 1, 1, 1, 1]
    ]
    bits = list(map(int, bits))
    syndrome = [sum(H[i][j] * bits[j] for j in range(7)) % 2 for i in range(3)]
    error_pos = int(''.join(map(str, syndrome)), 2)
    if error_pos != 0:
        bits[error_pos - 1] ^= 1  # Correct the bit

    data = bits[2], bits[4], bits[5], bits[6]
    value = sum(b << (3 - i) for i, b in enumerate(data))
    return value
