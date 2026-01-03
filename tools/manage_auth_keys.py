# =============================================================================
# tools/manage_auth_keys.py
#
# 描述:     授權金鑰管理工具 (Server Side)。
#           管理 Repo Service 的 authorized_keys 檔案。
# 用法:     
#   add:    python tools/manage_auth_keys.py add <DevID> --key-path <PublicPEM>
#   remove: python tools/manage_auth_keys.py remove <DevID>
#   list:   python tools/manage_auth_keys.py list
# =============================================================================

import sys
import os
import argparse
import base64

# 將專案根目錄加入 sys.path 以引用 shared 模組
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
sys.path.append(PROJECT_ROOT)

try:
    from shared.security_utils import calculate_hash
except ImportError:
    # 若無法引用(例如還沒安裝 crypto lib)，calculate_hash 可能不可用，這裡做簡單 fallback 或報錯
    pass

# 設定 Repo Service 的授權檔案位置
# 預設為: service_repo/authorized_keys
DEFAULT_AUTH_FILE = os.path.join(PROJECT_ROOT, 'service_repo', 'authorized_keys')

def parse_args():
    parser = argparse.ArgumentParser(description="Manage Authorized Keys for Repo Service")
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # Add Command
    parser_add = subparsers.add_parser('add', help="Add a developer public key")
    parser_add.add_argument('id', help="Developer ID")
    parser_add.add_argument('--key-path', required=True, help="Path to public key file (.pem)")
    
    # Remove Command
    parser_rem = subparsers.add_parser('remove', help="Remove a developer")
    parser_rem.add_argument('id', help="Developer ID")
    
    # List Command
    parser_list = subparsers.add_parser('list', help="List authorized developers")
    
    parser.add_argument('--file', default=DEFAULT_AUTH_FILE, help=f"Path to authorized_keys file (Default: {DEFAULT_AUTH_FILE})")
    
    return parser.parse_args()

def load_auth_file(path):
    keys = {}
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    try:
                        dev_id, b64_key = line.split('|', 1)
                        keys[dev_id.strip()] = b64_key.strip()
                    except: pass
    return keys

def save_auth_file(path, keys):
    # 確保目錄存在
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write("# SATIN Repo Service Authorized Keys\n")
        f.write(f"# Updated: {os.times()}\n\n")
        for dev_id, b64_key in keys.items():
            f.write(f"{dev_id}|{b64_key}\n")

def cmd_add(args):
    if not os.path.exists(args.key_path):
        print(f"[Error] Public key file not found: {args.key_path}")
        return

    try:
        with open(args.key_path, 'rb') as f:
            pub_bytes = f.read()
            
        # 簡單驗證是否為 PEM 格式
        if b"-----BEGIN PUBLIC KEY-----" not in pub_bytes:
            print("[Error] Invalid PEM public key format.")
            return

        # 轉為 Base64 單行字串
        b64_key = base64.b64encode(pub_bytes).decode('utf-8')
        
        keys = load_auth_file(args.file)
        if args.id in keys:
            print(f"[Warn] Developer ID '{args.id}' already exists. Overwriting.")
            
        keys[args.id] = b64_key
        save_auth_file(args.file, keys)
        print(f"✅ Added '{args.id}' to {args.file}")
        
    except Exception as e:
        print(f"[Error] Add failed: {e}")

def cmd_remove(args):
    keys = load_auth_file(args.file)
    if args.id in keys:
        del keys[args.id]
        save_auth_file(args.file, keys)
        print(f"✅ Removed '{args.id}'")
    else:
        print(f"[Warn] ID '{args.id}' not found.")

def cmd_list(args):
    keys = load_auth_file(args.file)
    print(f"=== Authorized Developers ({len(keys)}) ===")
    print(f"File: {args.file}\n")
    print(f"{'Developer ID':<20} | {'Key Fingerprint (SHA256, first 8 chars)'}")
    print("-" * 60)
    
    if not keys:
        print("(No keys registered)")
    
    for dev_id, b64_key in keys.items():
        try:
            # 嘗試計算指紋
            raw_key = base64.b64decode(b64_key)
            from shared.security_utils import calculate_hash
            fp = calculate_hash(raw_key)[:8]
        except:
            fp = "Invalid Key"
            
        print(f"{dev_id:<20} | {fp}")

def main():
    args = parse_args()
    
    if args.command == 'add':
        cmd_add(args)
    elif args.command == 'remove':
        cmd_remove(args)
    elif args.command == 'list':
        cmd_list(args)

if __name__ == "__main__":
    main()