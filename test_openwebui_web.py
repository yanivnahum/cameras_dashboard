#!/usr/bin/env python3
"""
Test script to interact with OpenWebUI web interface
"""

import os
import sys
import requests
import json
import time

# Configuration
LOCAL_GEMMA3_URL = os.environ.get('LOCAL_GEMMA3_URL', 'https://geospotx.com')
LOCAL_GEMMA3_API_KEY = os.environ.get('LOCAL_GEMMA3_API_KEY', '')

def test_web_interface():
    """Test the OpenWebUI web interface"""
    print("=== OpenWebUI Web Interface Test ===\n")
    
    print(f"Testing web interface at: {LOCAL_GEMMA3_URL}")
    
    try:
        # Test 1: Basic web interface access
        print("1. Testing basic web interface...")
        response = requests.get(LOCAL_GEMMA3_URL, timeout=10)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            print("   ✅ Web interface is accessible")
            # Look for API-related information in the HTML
            content = response.text.lower()
            if 'api' in content:
                print("   📝 Found API references in HTML")
            if 'openai' in content:
                print("   📝 Found OpenAI references in HTML")
            if 'gemma' in content:
                print("   📝 Found Gemma references in HTML")
        else:
            print(f"   ❌ Web interface error: {response.text[:200]}...")
            return False
        
        # Test 2: Look for API documentation
        print("\n2. Testing API documentation endpoints...")
        doc_endpoints = [
            "/docs",
            "/api/docs", 
            "/swagger",
            "/api/swagger",
            "/redoc",
            "/api/redoc"
        ]
        
        for endpoint in doc_endpoints:
            try:
                doc_response = requests.get(f"{LOCAL_GEMMA3_URL}{endpoint}", timeout=5)
                if doc_response.status_code == 200:
                    print(f"   ✅ Found documentation at: {endpoint}")
                    break
            except:
                continue
        
        # Test 3: Check for OpenAPI/Swagger spec
        print("\n3. Testing OpenAPI specification...")
        spec_endpoints = [
            "/openapi.json",
            "/api/openapi.json",
            "/swagger.json",
            "/api/swagger.json",
            "/v1/openapi.json",
            "/api/v1/openapi.json"
        ]
        
        for endpoint in spec_endpoints:
            try:
                spec_response = requests.get(f"{LOCAL_GEMMA3_URL}{endpoint}", timeout=5)
                if spec_response.status_code == 200:
                    print(f"   ✅ Found OpenAPI spec at: {endpoint}")
                    try:
                        spec_data = spec_response.json()
                        print(f"   📋 API Title: {spec_data.get('info', {}).get('title', 'Unknown')}")
                        print(f"   📋 API Version: {spec_data.get('info', {}).get('version', 'Unknown')}")
                        
                        # Look for chat completion endpoints
                        paths = spec_data.get('paths', {})
                        for path, methods in paths.items():
                            if 'chat' in path.lower() or 'completion' in path.lower():
                                print(f"   🔍 Found chat endpoint: {path}")
                                for method in methods.keys():
                                    print(f"      - {method.upper()}")
                    except:
                        print(f"   📋 Raw spec content: {spec_response.text[:200]}...")
                    break
            except:
                continue
        
        # Test 4: Check for model information
        print("\n4. Testing model information endpoints...")
        model_endpoints = [
            "/v1/models",
            "/api/v1/models",
            "/models",
            "/api/models"
        ]
        
        headers = {}
        if LOCAL_GEMMA3_API_KEY:
            headers['Authorization'] = f'Bearer {LOCAL_GEMMA3_API_KEY}'
        
        for endpoint in model_endpoints:
            try:
                model_response = requests.get(f"{LOCAL_GEMMA3_URL}{endpoint}", headers=headers, timeout=5)
                if model_response.status_code == 200:
                    print(f"   ✅ Found models endpoint: {endpoint}")
                    try:
                        models_data = model_response.json()
                        if 'data' in models_data:
                            for model in models_data['data']:
                                print(f"      - Model: {model.get('id', 'Unknown')}")
                        elif isinstance(models_data, list):
                            for model in models_data:
                                print(f"      - Model: {model.get('id', model.get('name', 'Unknown'))}")
                        else:
                            print(f"      📋 Models response: {json.dumps(models_data, indent=2)[:200]}...")
                    except:
                        print(f"      📋 Raw models response: {model_response.text[:200]}...")
                    break
            except:
                continue
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection error: {e}")
        return False

def test_manual_api_discovery():
    """Try to discover the API structure manually"""
    print("\n=== Manual API Discovery ===\n")
    
    headers = {
        'Content-Type': 'application/json'
    }
    if LOCAL_GEMMA3_API_KEY:
        headers['Authorization'] = f'Bearer {LOCAL_GEMMA3_API_KEY}'
    
    # Test common OpenWebUI API patterns
    print("Testing common OpenWebUI API patterns...")
    
    # Pattern 1: Direct chat endpoint
    print("\n1. Testing direct chat endpoint...")
    try:
        payload = {
            "model": "gemma3",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": False
        }
        
        response = requests.post(f"{LOCAL_GEMMA3_URL}/api/v1/chat", json=payload, headers=headers, timeout=10)
        print(f"   /api/v1/chat - Status: {response.status_code}")
        if response.status_code == 200:
            print("   ✅ Success!")
            print(f"   Response: {response.text[:200]}...")
        else:
            print(f"   Error: {response.text[:200]}...")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Pattern 2: Generate endpoint
    print("\n2. Testing generate endpoint...")
    try:
        payload = {
            "model": "gemma3",
            "prompt": "Hello",
            "stream": False
        }
        
        response = requests.post(f"{LOCAL_GEMMA3_URL}/api/v1/generate", json=payload, headers=headers, timeout=10)
        print(f"   /api/v1/generate - Status: {response.status_code}")
        if response.status_code == 200:
            print("   ✅ Success!")
            print(f"   Response: {response.text[:200]}...")
        else:
            print(f"   Error: {response.text[:200]}...")
    except Exception as e:
        print(f"   Error: {e}")

def main():
    """Main test function"""
    print("🔍 OpenWebUI Web Interface and API Discovery Tool\n")
    
    # Test 1: Web interface
    if not test_web_interface():
        print("❌ Cannot access web interface. Check the URL and network connectivity.")
        return
    
    # Test 2: Manual API discovery
    test_manual_api_discovery()
    
    print("\n=== Recommendations ===")
    print("Based on the test results:")
    print("1. If you found working endpoints, update the server.py file")
    print("2. Check the OpenWebUI documentation for the correct API format")
    print("3. Consider using the web interface to test the model manually")
    print("4. Look for any error messages that might indicate the correct endpoint")
    
    print("\n💡 Next Steps:")
    print("- Run the diagnose_openwebui.py script for more detailed endpoint testing")
    print("- Check the OpenWebUI logs for any API-related errors")
    print("- Verify that the Gemma3 model is properly loaded in OpenWebUI")

if __name__ == "__main__":
    main() 