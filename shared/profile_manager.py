# ==============================================================================
# shared/profile_manager.py
#
# Version: V1.3-001 (Key-In-DB)
# 更新日期: 2025-12-12
# 描述:     使用者身分設定檔管理器 (SQLite 版)。
#           [修正]: 
#             1. 資料庫 Schema 新增 private_key_blob, public_key_blob 欄位。
#             2. add_profile 支援直接寫入金鑰二進位資料。
# ==============================================================================

import sqlite3
import os
import base64
from shared.logging_tool import info, error

# 設定資料庫儲存於 User Home 的隱藏目錄
APP_DIR = os.path.join(os.path.expanduser("~"), ".satin")
DB_PATH = os.path.join(APP_DIR, "satin_profiles.db")

class ProfileManager:
    def __init__(self):
        self._ensure_db()

    def _ensure_db(self):
        """初始化資料庫結構與遷移"""
        if not os.path.exists(APP_DIR):
            try:
                os.makedirs(APP_DIR)
                if os.name == 'nt':
                    import ctypes
                    FILE_ATTRIBUTE_HIDDEN = 0x02
                    ctypes.windll.kernel32.SetFileAttributesW(APP_DIR, FILE_ATTRIBUTE_HIDDEN)
            except Exception as e:
                print(f"[ProfileManager] Warning: Could not set hidden attrib: {e}")

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # 建立設定檔表 (Base Schema)
        c.execute('''
            CREATE TABLE IF NOT EXISTS profiles (
                user_id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                key_path_b64 TEXT NOT NULL, 
                description TEXT,
                is_admin INTEGER DEFAULT 0,
                last_login TEXT
            )
        ''')
        
        # [Migration] 嘗試新增欄位 (若不存在)
        try:
            c.execute("ALTER TABLE profiles ADD COLUMN user_dir TEXT")
        except sqlite3.OperationalError: pass
        
        try:
            c.execute("ALTER TABLE profiles ADD COLUMN nickname TEXT")
        except sqlite3.OperationalError: pass
            
        try:
            c.execute("ALTER TABLE profiles ADD COLUMN avatar_path_b64 TEXT")
        except sqlite3.OperationalError: pass

        # [NEW] Key-In-DB Migration
        try:
            c.execute("ALTER TABLE profiles ADD COLUMN private_key_blob BLOB")
        except sqlite3.OperationalError: pass
        
        try:
            c.execute("ALTER TABLE profiles ADD COLUMN public_key_blob BLOB")
        except sqlite3.OperationalError: pass
        
        # 建立系統狀態表
        c.execute('''
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        conn.commit()
        conn.close()

    def _encode_path(self, path):
        """將路徑轉為 Base64 字串 (混淆)"""
        if not path: return ""
        path = path.replace("\\", "/")
        return base64.b64encode(path.encode('utf-8')).decode('utf-8')

    def _decode_path(self, b64_str):
        """解碼 Base64 字串"""
        if not b64_str: return ""
        try:
            p = base64.b64decode(b64_str.encode('utf-8')).decode('utf-8')
            return os.path.normpath(p) 
        except:
            return ""

    def get_all_profiles(self):
        """取得所有使用者列表"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM profiles ORDER BY is_admin DESC, user_id ASC")
        rows = c.fetchall()
        conn.close()
        
        results = []
        for r in rows:
            u_dir = self._decode_path(r['user_dir']) if 'user_dir' in r.keys() and r['user_dir'] else ""
            avt_path = self._decode_path(r['avatar_path_b64']) if 'avatar_path_b64' in r.keys() and r['avatar_path_b64'] else ""
            nick = r['nickname'] if 'nickname' in r.keys() and r['nickname'] else r['user_id']
            
            # [NEW] Check if blob exists
            has_db_key = False
            if 'private_key_blob' in r.keys() and r['private_key_blob']:
                has_db_key = True

            results.append({
                "id": r['user_id'],
                "nickname": nick,
                "default_role": r['role'], 
                "key_path": self._decode_path(r['key_path_b64']),
                "user_dir": u_dir,
                "avatar_path": avt_path,
                "description": r['description'],
                "is_admin": bool(r['is_admin']),
                "has_db_key": has_db_key,
                # Avoid returning full blob in list for performance, fetch individually
            })
        return results

    def get_profile(self, user_id):
        """取得單一使用者資料"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM profiles WHERE user_id=?", (user_id,))
        r = c.fetchone()
        conn.close()
        
        if r:
            u_dir = self._decode_path(r['user_dir']) if 'user_dir' in r.keys() and r['user_dir'] else ""
            avt_path = self._decode_path(r['avatar_path_b64']) if 'avatar_path_b64' in r.keys() and r['avatar_path_b64'] else ""
            nick = r['nickname'] if 'nickname' in r.keys() and r['nickname'] else user_id
            
            # [NEW] Fetch Blobs
            priv_blob = r['private_key_blob'] if 'private_key_blob' in r.keys() else None
            pub_blob = r['public_key_blob'] if 'public_key_blob' in r.keys() else None

            return {
                "id": r['user_id'],
                "nickname": nick,
                "default_role": r['role'],
                "key_path": self._decode_path(r['key_path_b64']),
                "user_dir": u_dir,
                "avatar_path": avt_path,
                "description": r['description'],
                "is_admin": bool(r['is_admin']),
                "private_key_blob": priv_blob,
                "public_key_blob": pub_blob
            }
        return None

    def add_profile(self, user_id, key_path, description="", user_dir="", private_key_bytes=None, public_key_bytes=None):
        """
        新增使用者
        [MOD]: 新增 private_key_bytes, public_key_bytes 參數，存入 DB。
        """
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        try:
            c.execute("SELECT COUNT(*) FROM profiles")
            count = c.fetchone()[0]
            is_admin = 1 if count == 0 else 0
            
            c.execute("SELECT is_admin FROM profiles WHERE user_id=?", (user_id,))
            existing = c.fetchone()
            if existing: is_admin = existing[0]
            
            b64_key_path = self._encode_path(key_path)
            b64_user_dir = self._encode_path(user_dir)
            role = "User"
            
            # [MOD] Insert with BLOBS
            c.execute('''
                INSERT OR REPLACE INTO profiles 
                (user_id, role, key_path_b64, description, is_admin, user_dir, nickname, avatar_path_b64, private_key_blob, public_key_blob)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, role, b64_key_path, description, is_admin, b64_user_dir, user_id, "", private_key_bytes, public_key_bytes))
            
            conn.commit()

            if user_dir:
                try:
                    if not os.path.exists(user_dir): os.makedirs(user_dir)
                    for sub in ['project', 'key']:
                        sub_dir = os.path.join(user_dir, sub)
                        if not os.path.exists(sub_dir): os.makedirs(sub_dir)
                    info(f"[ProfileManager] User workspace created at: {user_dir}")
                except Exception as e:
                    print(f"[ProfileManager] Failed to create directories: {e}")

            return True, "Profile Added"
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    def update_profile_meta(self, user_id, description, nickname=None, avatar_path=None):
        """更新使用者中繼資料"""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        try:
            updates = []
            params = []
            
            if description is not None:
                updates.append("description=?")
                params.append(description)
            if nickname is not None:
                updates.append("nickname=?")
                params.append(nickname)
            if avatar_path is not None:
                updates.append("avatar_path_b64=?")
                params.append(self._encode_path(avatar_path))
            
            if not updates: return True, "No changes"
            
            params.append(user_id)
            query = f"UPDATE profiles SET {', '.join(updates)} WHERE user_id=?"
            
            c.execute(query, tuple(params))
            conn.commit()
            return True, "Updated"
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    def delete_profile(self, user_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM profiles WHERE user_id=?", (user_id,))
        last = self.get_last_active()
        if last == user_id:
            self.set_last_active(None)
        conn.commit()
        conn.close()

    def set_last_active(self, user_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        if user_id:
            c.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES ('last_active', ?)", (user_id,))
        else:
            c.execute("DELETE FROM system_state WHERE key='last_active'")
        conn.commit()
        conn.close()

    def get_last_active(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT value FROM system_state WHERE key='last_active'")
        row = c.fetchone()
        conn.close()
        return row[0] if row else None

    def reset_all(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM profiles")
        c.execute("DELETE FROM system_state")
        conn.commit()
        conn.close()