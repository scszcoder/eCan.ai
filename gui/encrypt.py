import os
import base64
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend


def derive_key(serial_number, salt=None):
    # Generate a random salt if not provided
    if salt is None:
        # salt = os.urandom(16)
        salt = b'fixed_salt_16_by'

    # Derive a key using PBKDF2HMAC
    kdf = PBKDF2HMAC(
        algorithm=SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    key = kdf.derive(serial_number.encode())

    return key, salt


def encrypt_message(message, key):
    # Generate a random initialization vector (IV)
    iv = os.urandom(16)

    # Initialize the cipher
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()

    # Pad the message to be a multiple of the block size
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded_data = padder.update(message.encode('utf-8')) + padder.finalize()

    # Encrypt the message
    encrypted_message = encryptor.update(padded_data) + encryptor.finalize()

    # Combine IV and encrypted message
    return base64.urlsafe_b64encode(iv + encrypted_message).decode('utf-8')


def decrypt_message(encrypted_message, key):
    # Decode the base64 encoded message
    encrypted_message = base64.urlsafe_b64decode(encrypted_message.encode('utf-8'))

    # Extract the IV from the beginning of the encrypted message
    iv = encrypted_message[:16]
    encrypted_message = encrypted_message[16:]

    # Initialize the cipher
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()

    # Decrypt the message
    decrypted_padded_message = decryptor.update(encrypted_message) + decryptor.finalize()

    # Unpad the message
    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    decrypted_message = unpadder.update(decrypted_padded_message) + unpadder.finalize()

    return decrypted_message.decode('utf-8')


# # Example usage
# A = "This is a random string"
# B = "UniqueSerialNumber123"
#
# Use a fixed salt for consistent key derivation
# fixed_salt = b'b'fixed_salt_16_by'  # Should be 16 bytes for this example

# # Derive the key from the serial number
# key, salt = derive_key(B)
#
# # Encrypt the message
# C = encrypt_message(A, key)
# print(f"Encrypted message (C): {C}")
#
# # Decrypt the message
# decrypted_A = decrypt_message(C, key)
# print(f"Decrypted message (A): {decrypted_A}")
#
# # To verify, you would typically store the salt alongside the encrypted message
# print(f"Salt used for key derivation: {base64.urlsafe_b64encode(salt).decode('utf-8')}")
