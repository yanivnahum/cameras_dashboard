#!/usr/bin/env python3
"""
Diagnostic script to find the correct OpenWebUI API endpoints
"""

import os
import sys
import requests
import json
import base64

# Configuration
LOCAL_GEMMA3_URL = os.environ.get('LOCAL_GEMMA3_URL', 'https://geospotx.com')
LOCAL_GEMMA3_API_KEY = os.environ.get('LOCAL_GEMMA3_API_KEY', '')

def test_endpoint(url, method='GET', payload=None, headers=None):
    """Test a specific endpoint"""
    try:
        if method.upper() == 'GET':
            response = requests.get(url, headers=headers, timeout=10)
        elif method.upper() == 'POST':
            response = requests.post(url, json=payload, headers=headers, timeout=10)
        else:
            print(f"❌ Unsupported method: {method}")
            return False
            
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print(f"   ✅ Success!")
            try:
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)[:200]}...")
            except:
                print(f"   Response: {response.text[:200]}...")
            return True
        else:
            print(f"   ❌ Error: {response.text[:200]}...")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Connection error: {e}")
        return False

def test_openwebui_endpoints():
    """Test various OpenWebUI API endpoints"""
    print("=== OpenWebUI API Endpoint Diagnosis ===\n")
    
    # Prepare headers
    headers = {
        'Content-Type': 'application/json'
    }
    if LOCAL_GEMMA3_API_KEY:
        headers['Authorization'] = f'Bearer {LOCAL_GEMMA3_API_KEY}'
    
    print(f"Testing OpenWebUI server at: {LOCAL_GEMMA3_URL}")
    print(f"API Key: {'Set' if LOCAL_GEMMA3_API_KEY else 'Not set'}\n")
    
    # Test 1: Basic connectivity
    print("1. Testing basic connectivity...")
    test_endpoint(f"{LOCAL_GEMMA3_URL}/", headers=headers)
    
    # Test 2: Standard OpenAI-compatible endpoints
    print("\n2. Testing OpenAI-compatible endpoints...")
    
    endpoints_to_test = [
        "/v1/models",
        "/api/v1/models", 
        "/v1/chat/completions",
        "/api/v1/chat/completions",
        "/chat/completions",
        "/api/chat/completions"
    ]
    
    for endpoint in endpoints_to_test:
        print(f"\n   Testing: {endpoint}")
        test_endpoint(f"{LOCAL_GEMMA3_URL}{endpoint}", headers=headers)
    
    # Test 3: OpenWebUI-specific endpoints
    print("\n3. Testing OpenWebUI-specific endpoints...")
    
    openwebui_endpoints = [
        "/api/v1/chat",
        "/api/chat",
        "/v1/chat",
        "/api/v1/generate",
        "/api/generate",
        "/v1/generate"
    ]
    
    for endpoint in openwebui_endpoints:
        print(f"\n   Testing: {endpoint}")
        test_endpoint(f"{LOCAL_GEMMA3_URL}{endpoint}", headers=headers)
    
    # Test 4: Test with a simple chat payload
    print("\n4. Testing chat completion with payload...")
    
    # Create a simple test image
    test_image_data = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\xaa\xff\xd9'
    image_base64 = base64.b64encode(test_image_data).decode('utf-8')
    
    # Test different payload formats
    payloads_to_test = [
        # Standard OpenAI format
        {
            "model": "gemma3",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Hello, can you see this image?"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                    ]
                }
            ],
            "stream": False,
            "temperature": 0.1,
            "max_tokens": 100
        },
        # Simplified format
        {
            "model": "gemma3",
            "messages": [
                {"role": "user", "content": "Hello, can you see this image?"}
            ],
            "stream": False
        },
        # OpenWebUI format (if different)
        {
            "model": "gemma3",
            "prompt": "Hello, can you see this image?",
            "stream": False
        }
    ]
    
    # Test with different endpoints
    chat_endpoints = [
        "/v1/chat/completions",
        "/api/v1/chat/completions", 
        "/api/v1/chat",
        "/api/chat"
    ]
    
    for i, payload in enumerate(payloads_to_test):
        print(f"\n   Testing payload format {i+1}...")
        for endpoint in chat_endpoints:
            print(f"     Endpoint: {endpoint}")
            test_endpoint(f"{LOCAL_GEMMA3_URL}{endpoint}", method='POST', payload=payload, headers=headers)
    
    # Test 5: Check for documentation or info endpoints
    print("\n5. Testing info/documentation endpoints...")
    
    info_endpoints = [
        "/",
        "/docs",
        "/api/docs",
        "/v1/docs",
        "/api/v1/docs",
        "/openapi.json",
        "/api/openapi.json",
        "/v1/openapi.json",
        "/api/v1/openapi.json"
    ]
    
    for endpoint in info_endpoints:
        print(f"\n   Testing: {endpoint}")
        test_endpoint(f"{LOCAL_GEMMA3_URL}{endpoint}", headers=headers)

def test_alternative_approaches():
    """Test alternative approaches if standard endpoints don't work"""
    print("\n=== Testing Alternative Approaches ===\n")
    
    headers = {
        'Content-Type': 'application/json'
    }
    if LOCAL_GEMMA3_API_KEY:
        headers['Authorization'] = f'Bearer {LOCAL_GEMMA3_API_KEY}'
    
    # Test 1: Different HTTP methods
    print("1. Testing different HTTP methods...")
    methods = ['GET', 'POST', 'PUT', 'PATCH']
    
    for method in methods:
        print(f"\n   Testing {method} on /v1/chat/completions")
        test_endpoint(f"{LOCAL_GEMMA3_URL}/v1/chat/completions", method=method, headers=headers)
    
    # Test 2: Different content types
    print("\n2. Testing different content types...")
    
    content_types = [
        'application/json',
        'application/x-www-form-urlencoded',
        'multipart/form-data'
    ]
    
    for content_type in content_types:
        print(f"\n   Testing Content-Type: {content_type}")
        test_headers = headers.copy()
        test_headers['Content-Type'] = content_type
        
        # Simple payload for testing
        payload = {"model": "gemma3", "messages": [{"role": "user", "content": "Hello"}]}
        test_endpoint(f"{LOCAL_GEMMA3_URL}/v1/chat/completions", method='POST', payload=payload, headers=test_headers)

def main():
    """Main diagnostic function"""
    print("🔍 OpenWebUI API Endpoint Diagnosis Tool\n")
    
    # Test 1: Basic endpoint discovery
    test_openwebui_endpoints()
    
    # Test 2: Alternative approaches
    test_alternative_approaches()
    
    print("\n=== Diagnosis Summary ===")
    print("Based on the test results above:")
    print("1. Look for endpoints that return status 200")
    print("2. Check the response format to understand the API structure")
    print("3. Note any error messages that might indicate the correct endpoint")
    print("4. Update the server.py file with the correct endpoint and payload format")
    
    print("\n💡 Next Steps:")
    print("- If you find a working endpoint, update the detect_persons_local_gemma3() function")
    print("- Check the OpenWebUI documentation for the correct API format")
    print("- Consider using the OpenWebUI web interface to test the model manually")

if __name__ == "__main__":
    main() 