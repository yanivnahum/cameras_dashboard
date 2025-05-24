#!/usr/bin/env python3
"""
Script to check for multiple server.py instances and help manage them.
"""
import psutil
import os
import signal
import sys

def find_server_instances():
    """Find all running server.py instances"""
    instances = []
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time', 'ppid']):
        try:
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                cmdline = proc.info['cmdline'] or []
                if any('server.py' in cmd for cmd in cmdline):
                    instances.append({
                        'pid': proc.info['pid'],
                        'ppid': proc.info['ppid'],
                        'cmdline': ' '.join(cmdline),
                        'create_time': proc.info['create_time'],
                        'process': proc
                    })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    return instances

def main():
    instances = find_server_instances()
    
    if not instances:
        print("✅ No server.py instances found running.")
        return
    
    print(f"🔍 Found {len(instances)} server.py instance(s):")
    print()
    
    for i, instance in enumerate(instances, 1):
        print(f"{i}. PID {instance['pid']} (Parent: {instance['ppid']})")
        print(f"   Command: {instance['cmdline']}")
        print(f"   Started: {psutil.datetime.datetime.fromtimestamp(instance['create_time'])}")
        print()
    
    if len(instances) > 1:
        print("⚠️  WARNING: Multiple instances detected! This can cause:")
        print("   - Conflicting detection cycles")
        print("   - Inconsistent state management")
        print("   - Resource conflicts")
        print()
        
        if len(sys.argv) > 1 and sys.argv[1] == '--kill-all':
            print("🛑 Stopping all server instances...")
            for instance in instances:
                try:
                    proc = psutil.Process(instance['pid'])
                    proc.terminate()
                    print(f"✅ Terminated PID {instance['pid']}")
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    print(f"❌ Could not terminate PID {instance['pid']}: {e}")
            print("Done.")
        else:
            print("To stop all instances, run:")
            print(f"  python3 {sys.argv[0]} --kill-all")
    else:
        print("✅ Only one instance running - this is normal.")

if __name__ == "__main__":
    main() 