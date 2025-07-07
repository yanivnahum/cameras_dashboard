#!/usr/bin/env python3
"""
Comprehensive test to understand OpenWebUI server configuration
"""

import os
import sys
import requests
import json
import time

# Configuration
LOCAL_GEMMA3_URL = os.environ.get('LOCAL_GEMMA3_URL', 'https://geospotx.com')
LOCAL_GEMMA3_API_KEY = os.environ.get('LOCAL_GEMMA3_API_KEY', '')

def test_endpoint_with_details(url, method='GET', headers=None, data=None):
    """Test an endpoint with detailed information"""
    if headers is None:
        headers = {}
    
    print(f"Testing {method} {url}")
    
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, timeout=10)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=data, timeout=10)
        else:
            print(f"   ❌ Unsupported method: {method}")
            return
        
        print(f"   Status: {response.status_code}")
        print(f"   Content-Type: {response.headers.get('content-type', 'Not specified')}")
        print(f"   Content-Length: {response.headers.get('content-length', 'Not specified')}")
        
        if response.status_code == 200:
            content = response.text
            if content.startswith('<!doctype html>') or content.startswith('<html'):
                print("   📄 HTML Response (Web Interface)")
                # Look for OpenWebUI indicators
                if 'openwebui' in content.lower():
                    print("   🎯 OpenWebUI detected in HTML")
                if 'gemma' in content.lower():
                    print("   🤖 Gemma model mentioned in HTML")
                if 'api' in content.lower():
                    print("   🔌 API mentioned in HTML")
            else:
                print("   📋 Non-HTML Response (Possible API)")
                try:
                    json_data = response.json()
                    print(f"   ✅ Valid JSON: {json.dumps(json_data, indent=2)[:300]}...")
                except:
                    print(f"   📄 Text Response: {content[:200]}...")
        elif response.status_code == 401:
            print("   🔐 Authentication Required")
        elif response.status_code == 403:
            print("   🚫 Forbidden")
        elif response.status_code == 404:
            print("   ❌ Not Found")
        elif response.status_code == 405:
            print("   ❌ Method Not Allowed")
        else:
            print(f"   ❓ Unexpected Status: {response.text[:100]}...")
            
    except requests.exceptions.ConnectionError:
        print("   ❌ Connection Refused")
    except requests.exceptions.Timeout:
        print("   ⏰ Timeout")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print()

def main():
    """Main test function"""
    print("🔍 Comprehensive OpenWebUI API Test\n")
    
    print(f"Target URL: {LOCAL_GEMMA3_URL}")
    print(f"API Key: {'Set' if LOCAL_GEMMA3_API_KEY else 'Not set'}\n")
    
    # Test 1: Main domain endpoints
    print("=== Testing Main Domain Endpoints ===\n")
    
    base_headers = {'Content-Type': 'application/json'}
    if LOCAL_GEMMA3_API_KEY:
        base_headers['Authorization'] = f'Bearer {LOCAL_GEMMA3_API_KEY}'
    
    main_endpoints = [
        '/',
        '/api',
        '/api/v1',
        '/v1',
        '/docs',
        '/openapi.json',
        '/api/docs',
        '/api/openapi.json'
    ]
    
    for endpoint in main_endpoints:
        test_endpoint_with_details(f"{LOCAL_GEMMA3_URL}{endpoint}", headers=base_headers)
    
    # Test 2: Port 3000 (which showed some response)
    print("=== Testing Port 3000 ===\n")
    
    port3000_endpoints = [
        '/',
        '/api',
        '/api/v1',
        '/v1',
        '/v1/models',
        '/v1/chat/completions',
        '/api/v1/chat',
        '/docs',
        '/openapi.json'
    ]
    
    for endpoint in port3000_endpoints:
        test_endpoint_with_details(f"http://geospotx.com:3000{endpoint}", headers=base_headers)
    
    # Test 3: Test POST requests to common endpoints
    print("=== Testing POST Requests ===\n")
    
    # Simple test payload
    test_payload = {
        "model": "gemma3",
        "messages": [
            {
                "role": "user",
                "content": "Hello, this is a test message."
            }
        ],
        "stream": False
    }
    
    post_endpoints = [
        '/v1/chat/completions',
        '/api/v1/chat/completions',
        '/api/v1/chat',
        '/api/chat',
        '/v1/chat',
        '/chat'
    ]
    
    for endpoint in post_endpoints:
        # Test on main domain
        test_endpoint_with_details(f"{LOCAL_GEMMA3_URL}{endpoint}", 
                                 method='POST', 
                                 headers=base_headers, 
                                 data=test_payload)
        
        # Test on port 3000
        test_endpoint_with_details(f"http://geospotx.com:3000{endpoint}", 
                                 method='POST', 
                                 headers=base_headers, 
                                 data=test_payload)
    
    # Test 4: Check for any running services
    print("=== Service Discovery ===\n")
    
    # Test a range of ports to see what's running
    test_ports = [80, 443, 3000, 5000, 8000, 8080, 9000]
    
    for port in test_ports:
        protocol = 'https' if port in [443] else 'http'
        url = f"{protocol}://geospotx.com:{port}"
        
        try:
            response = requests.get(f"{url}/", timeout=5)
            print(f"Port {port} ({protocol}): Status {response.status_code}")
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                if 'html' in content_type.lower():
                    print(f"   📄 HTML content")
                elif 'json' in content_type.lower():
                    print(f"   📋 JSON content")
                else:
                    print(f"   📄 Content-Type: {content_type}")
        except requests.exceptions.ConnectionError:
            print(f"Port {port} ({protocol}): Connection refused")
        except requests.exceptions.Timeout:
            print(f"Port {port} ({protocol}): Timeout")
        except Exception as e:
            print(f"Port {port} ({protocol}): Error - {e}")
    
    print("\n=== Summary and Recommendations ===\n")
    print("Based on the test results:")
    print("1. If you found a working API endpoint, update your server.py configuration")
    print("2. If all endpoints return HTML, the API might be disabled or require authentication")
    print("3. Check the OpenWebUI documentation for proper API configuration")
    print("4. Consider accessing the web interface directly to check settings")
    print("5. Look for environment variables or configuration files that enable API access")

if __name__ == "__main__":
    main() 