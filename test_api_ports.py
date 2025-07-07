#!/usr/bin/env python3
"""
Test script to check if OpenWebUI API is running on different ports
"""

import os
import sys
import requests
import json
from urllib.parse import urlparse

# Configuration
LOCAL_GEMMA3_URL = os.environ.get('LOCAL_GEMMA3_URL', 'https://geospotx.com')
LOCAL_GEMMA3_API_KEY = os.environ.get('LOCAL_GEMMA3_API_KEY', '')

def test_port(host, port, use_https=True):
    """Test if API is available on a specific port"""
    protocol = 'https' if use_https else 'http'
    url = f"{protocol}://{host}:{port}"
    
    print(f"Testing {url}...")
    
    headers = {'Content-Type': 'application/json'}
    if LOCAL_GEMMA3_API_KEY:
        headers['Authorization'] = f'Bearer {LOCAL_GEMMA3_API_KEY}'
    
    try:
        # Test models endpoint
        response = requests.get(f"{url}/v1/models", headers=headers, timeout=5)
        print(f"   /v1/models - Status: {response.status_code}")
        
        if response.status_code == 200:
            if response.text.startswith('<!doctype html>'):
                print("   ❌ HTML response (web interface)")
            else:
                print("   ✅ JSON response (API found!)")
                try:
                    data = response.json()
                    print(f"   📋 Response: {json.dumps(data, indent=2)[:200]}...")
                    return True
                except:
                    print(f"   📋 Response: {response.text[:200]}...")
                    return True
        elif response.status_code == 401:
            print("   🔐 Authentication required")
        elif response.status_code == 404:
            print("   ❌ Not found")
        else:
            print(f"   ❓ Status: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("   ❌ Connection refused")
    except requests.exceptions.Timeout:
        print("   ⏰ Timeout")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    return False

def main():
    """Main test function"""
    print("🔍 OpenWebUI API Port Discovery Tool\n")
    
    # Parse the URL to get host
    parsed_url = urlparse(LOCAL_GEMMA3_URL)
    host = parsed_url.hostname or parsed_url.netloc
    
    print(f"Host: {host}")
    print(f"Original URL: {LOCAL_GEMMA3_URL}")
    print(f"API Key: {'Set' if LOCAL_GEMMA3_API_KEY else 'Not set'}\n")
    
    # Common ports for OpenWebUI API
    common_ports = [
        5000,   # Common Flask/FastAPI port
        8000,   # Common development port
        8080,   # Alternative development port
        3000,   # Node.js common port
        4000,   # Alternative API port
        9000,   # Another common port
        5001,   # Alternative Flask port
        8001,   # Alternative development port
        8081,   # Alternative development port
        3001,   # Alternative Node.js port
    ]
    
    print("=== Testing Common API Ports ===\n")
    
    found_api = False
    
    # Test HTTPS first (more common for production)
    for port in common_ports:
        if test_port(host, port, use_https=True):
            print(f"\n🎉 Found API on https://{host}:{port}")
            found_api = True
            break
        print()
    
    # If not found on HTTPS, try HTTP
    if not found_api:
        print("=== Testing HTTP Ports ===\n")
        for port in common_ports:
            if test_port(host, port, use_https=False):
                print(f"\n🎉 Found API on http://{host}:{port}")
                found_api = True
                break
            print()
    
    if not found_api:
        print("\n❌ No API found on common ports")
        print("\n💡 Next Steps:")
        print("1. Check OpenWebUI documentation for the correct API port")
        print("2. Look for API configuration in the web interface")
        print("3. Check if API needs to be enabled in OpenWebUI settings")
        print("4. Verify that the OpenWebUI server is running with API support")
    else:
        print("\n✅ API found! Update your configuration to use the correct port.")

if __name__ == "__main__":
    main() 