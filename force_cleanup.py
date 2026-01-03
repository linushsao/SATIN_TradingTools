# ==============================================================================
# force_cleanup.py
#
# Version: V0.1-003 (User Confirmation)
# 描述: SATIN 系統 Port 清理工具。
#       流程: 1.列出狀態 -> 2.詢問確認 -> 3.執行清理 -> 4.驗證結果
# ==============================================================================

import os
import sys
import subprocess
import time

# 定義要掃描的 SATIN 相關 Port
TARGET_PORTS = [
    5556, 5557,       # Trading Service (Pub/Rep)
    5558, 5559,       # Backtest Service (Pub/Rep)
    5560, 5561,       # Repo Service (Rep/Pub)
    5562              # Microkernel (Rep)
]

def get_port_status():
    """
    掃描目標 Port 的佔用情形。
    回傳: dict { port: pid } (若無佔用則 PID 為 None)
    """
    status = {port: None for port in TARGET_PORTS}
    
    try:
        # 執行 netstat -aon 指令
        cmd = "netstat -aon"
        result = subprocess.check_output(cmd, shell=True).decode('utf-8', errors='ignore')
        lines = result.splitlines()
        
        for line in lines:
            if "TCP" not in line:
                continue
            
            parts = line.split()
            # 一般格式: Proto  Local Address  Foreign Address  State  PID
            if len(parts) < 5:
                continue
                
            local_addr = parts[1]
            pid = parts[-1]
            
            # 檢查是否為目標 Port
            for port in TARGET_PORTS:
                if f":{port}" in local_addr:
                    # 優先保留 LISTENING 狀態的 PID
                    if status[port] is None or "LISTENING" in line:
                        status[port] = pid
                        
    except Exception as e:
        print(f"[錯誤] 無法執行 netstat: {e}")
        
    return status

def get_process_name(pid):
    """根據 PID 反查程序名稱"""
    if not pid or pid == "0": return "N/A"
    try:
        cmd = f'tasklist /FI "PID eq {pid}" /FO CSV /NH'
        output = subprocess.check_output(cmd, shell=True).decode('utf-8', errors='ignore').strip()
        if output and '"' in output:
            parts = output.split('","')
            if len(parts) > 0:
                return parts[0].strip('"')
        return "Unknown"
    except Exception:
        return "Unknown"

def print_report(title, port_status):
    """格式化輸出檢查報告"""
    print(f"\n--- {title} ---")
    print(f"{'Port':<8} {'Status':<12} {'PID':<8} {'Process Name'}")
    print("-" * 50)
    
    active_count = 0
    pid_name_cache = {}

    for port in sorted(TARGET_PORTS):
        pid = port_status.get(port)
        if pid:
            state = "🔴 BUSY"
            pid_str = pid
            if pid not in pid_name_cache:
                pid_name_cache[pid] = get_process_name(pid)
            p_name = pid_name_cache[pid]
            active_count += 1
        else:
            state = "🟢 FREE"
            pid_str = "-"
            p_name = "-"
            
        print(f"{port:<8} {state:<12} {pid_str:<8} {p_name}")
    
    print("-" * 50)
    return active_count

def kill_process(pid):
    """強制終止指定 PID"""
    if pid == "0" or not pid: return
    try:
        pname = get_process_name(pid)
        print(f"  >>> 正在終止 PID {pid} ({pname})...")
        subprocess.check_call(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"      [OK] 已終止")
    except subprocess.CalledProcessError:
        print(f"      [Failed] 無法終止 (權限不足或已消失)")

def main():
    print("==================================================")
    print("      SATIN Port Cleaner (Safe Mode)              ")
    print("==================================================")

    # 步驟 1: 列出目前狀態
    current_status = get_port_status()
    occupied_count = print_report("1. 檢查目前 Port 狀態", current_status)

    if occupied_count == 0:
        print("\n[結果] 系統目前乾淨，無須清理。")
        return

    # 步驟 2: 詢問使用者確認
    print(f"\n[警告] 發現 {occupied_count} 個被佔用的 Port。")
    user_input = input("請問是否強制清除上述所有程序? (y/n): ")

    if user_input.lower() != 'y':
        print("\n[取消] 使用者取消操作，程式結束。")
        return

    # 步驟 3: 執行清理
    print("\n--- 2. 執行清理程序 ---")
    pids_to_kill = set(pid for pid in current_status.values() if pid)
    
    for pid in pids_to_kill:
        kill_process(pid)
    
    print("  >>> 等待 2 秒讓作業系統釋放 Port...")
    time.sleep(2)

    # 步驟 4: 再次列出狀態驗證
    final_status = get_port_status()
    final_count = print_report("3. 驗證清理結果", final_status)

    if final_count == 0:
        print("\n[成功] 所有 Port 已釋放，現在可以啟動系統了。")
    else:
        print("\n[警告] 仍有 Port 被佔用，請檢查是否有系統級服務干擾。")

if __name__ == "__main__":
    main()