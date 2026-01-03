# =============================================================================
# tools/key_gen.py
#
# 描述:     開發者金鑰生成工具。
#           使用 shared.security_utils 生成 RSA-2048 公私鑰對。
# 用法:     python tools/key_gen.py
# 輸出:     tools/keys/developer_private.pem
#           tools/keys/developer_public.pem
# =============================================================================

import sys
import os

# 將專案根目錄加入 sys.path 以引用 shared 模組
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
sys.path.append(PROJECT_ROOT)

try:
    from shared.security_utils import generate_key_pair
except ImportError as e:
    print(f"Error importing shared modules: {e}")
    print("Please run this script from the project root (e.g., python tools/key_gen.py)")
    sys.exit(1)

def main():
    print("=== SATIN Developer Key Generator ===")
    
    # 1. 準備輸出目錄
    keys_dir = os.path.join(CURRENT_DIR, 'keys')
    if not os.path.exists(keys_dir):
        os.makedirs(keys_dir)
        print(f"[Init] Created directory: {keys_dir}")
        
    # 2. 生成金鑰
    print("[Gen] Generating RSA-2048 key pair... (this may take a moment)")
    try:
        private_pem, public_pem = generate_key_pair(key_size=2048)
    except Exception as e:
        print(f"[Error] Key generation failed: {e}")
        return

    # 3. 寫入檔案
    priv_path = os.path.join(keys_dir, 'developer_private.pem')
    pub_path = os.path.join(keys_dir, 'developer_public.pem')
    
    try:
        with open(priv_path, 'wb') as f:
            f.write(private_pem)
        
        # 設定私鑰權限 (僅擁有者可讀，Unix-like 系統有效)
        if os.name != 'nt':
            os.chmod(priv_path, 0o600)
            
        with open(pub_path, 'wb') as f:
            f.write(public_pem)
            
        print("\n✅ Keys generated successfully!")
        print(f"🔑 Private Key: {priv_path} (KEEP SECRET!)")
        print(f"🔒 Public Key:  {pub_path} (Send this to Repo Admin)")
        
    except Exception as e:
        print(f"[Error] Failed to write keys to disk: {e}")

if __name__ == "__main__":
    main()