# from cryptography.fernet import Fernet

# # 生成密钥（仅需一次，之后需要安全存储此密钥）
# key = b'1Lyt0J0TOYP-isBzB_KJIfzrfLK8Vaujl1c5YqdlW8c='
# cipher_suite = Fernet(key)


# # 加密密码
# def encrypt_password(password: str) -> bytes:
#     return cipher_suite.encrypt(password.encode())


# # 解密密码
# def decrypt_password(encrypted_password: bytes) -> str:
#     password = cipher_suite.decrypt(encrypted_password)
#     return password.decode()


# if __name__ == '__main__':
#     print(key)
#     print(encrypt_password('123456'))