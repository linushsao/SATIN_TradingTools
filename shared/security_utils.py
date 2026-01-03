# ==============================================================================
# shared/security_utils.py
#
# Version: V1.2-000 (Passphrase Support)
# 描述:     安全相關工具庫。
#           [新增]: 支援帶密碼 (Passphrase) 的私鑰生成與載入。
#           [新增]: sign_data_with_object 支援直接使用記憶體中的金鑰物件簽章。
# ==============================================================================

import hashlib
import base64
import os

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.hazmat.primitives import serialization
    from cryptography.exceptions import InvalidSignature
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

def calculate_hash(data: bytes) -> str:
    """計算資料的 SHA-256 雜湊值 (回傳 Hex 字串)"""
    sha256 = hashlib.sha256()
    sha256.update(data)
    return sha256.hexdigest()

def generate_key_pair(key_size=2048, password: str = None):
    """
    生成 RSA 公私鑰對 (PEM 格式 bytes)。
    Args:
        password: 若提供，則使用 AES-256 加密私鑰。
    """
    if not HAS_CRYPTO:
        raise ImportError("Library 'cryptography' is required for key generation.")

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
    )
    
    # 決定加密演算法
    if password:
        encryption_algorithm = serialization.BestAvailableEncryption(password.encode('utf-8'))
    else:
        encryption_algorithm = serialization.NoEncryption()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption_algorithm
    )
    
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    return private_pem, public_pem

def load_private_key_obj(private_key_pem: bytes, password: str = None):
    """
    載入私鑰並回傳 Key Object (用於記憶體暫存)。
    若私鑰有加密且密碼錯誤/未提供，將拋出例外。
    """
    if not HAS_CRYPTO:
        raise ImportError("Library 'cryptography' is required.")
        
    pwd_bytes = password.encode('utf-8') if password else None
    
    return serialization.load_pem_private_key(
        private_key_pem,
        password=pwd_bytes
    )

def get_public_key_from_private(private_key_pem: bytes, password: str = None) -> bytes:
    """
    從私鑰 PEM 推導出對應的公鑰 PEM。
    """
    private_key = load_private_key_obj(private_key_pem, password)
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return public_pem

def sign_data(private_key_pem: bytes, data: bytes, password: str = None) -> str:
    """
    使用私鑰 PEM 對資料進行簽章 (每次需重新載入 Key，效能較差，適合偶發操作)。
    """
    private_key = load_private_key_obj(private_key_pem, password)
    return sign_data_with_object(private_key, data)

def sign_data_with_object(private_key_obj, data: bytes) -> str:
    """
    使用已載入記憶體的私鑰物件進行簽章 (高效能)。
    """
    if not HAS_CRYPTO:
        raise ImportError("Library 'cryptography' missing.")

    signature = private_key_obj.sign(
        data,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )
    
    return base64.b64encode(signature).decode('utf-8')

def verify_signature(public_key_pem: bytes, data: bytes, signature_b64: str) -> bool:
    """
    使用公鑰驗證簽章。
    """
    if not HAS_CRYPTO:
        raise ImportError("Library 'cryptography' missing.")
        
    try:
        public_key = serialization.load_pem_public_key(public_key_pem)
        signature = base64.b64decode(signature_b64)
        
        public_key.verify(
            signature,
            data,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return True
    except (InvalidSignature, Exception):
        return False