#!/usr/bin/env python3
"""
Debug script to understand OpenWebUI API configuration
"""

import os
import sys
import requests
import json
import re

# Configuration
LOCAL_GEMMA3_URL = os.environ.get('LOCAL_GEMMA3_URL', 'https://geospotx.com')
LOCAL_GEMMA3_API_KEY = os.environ.get('LOCAL_GEMMA3_API_KEY', '')

def analyze_html_response(html_content):
    """Analyze HTML response to find API-related information"""
    print("   📄 Analyzing HTML response...")
    
    # Look for API-related content
    api_patterns = [
        r'api[_-]?key',
        r'openai',
        r'gemma',
        r'chat',
        r'completion',
        r'generate',
        r'v1',
        r'endpoint'
    ]
    
    found_patterns = []
    for pattern in api_patterns:
        if re.search(pattern, html_content, re.IGNORECASE):
            found_patterns.append(pattern)
    
    if found_patterns:
        print(f"   🔍 Found API-related patterns: {', '.join(found_patterns)}")
    else:
        print("   🔍 No obvious API patterns found in HTML")
    
    # Look for JavaScript that might contain API endpoints
    js_patterns = [
        r'fetch\([\'"]([^\'"]*api[^\'"]*)[\'"]',
        r'axios\.(get|post)\([\'"]([^\'"]*api[^\'"]*)[\'"]',
        r'url[\'"]?\s*:\s*[\'"]([^\'"]*api[^\'"]*)[\'"]',
        r'endpoint[\'"]?\s*:\s*[\'"]([^\'"]*api[^\'"]*)[\'"]'
    ]
    
    for pattern in js_patterns:
        matches = re.findall(pattern, html_content, re.IGNORECASE)
        if matches:
            print(f"   🔍 Found potential API endpoints in JS: {matches[:3]}")  # Show first 3
    
    # Look for configuration or settings
    config_patterns = [
        r'config[\'"]?\s*:\s*\{[^}]*\}',
        r'settings[\'"]?\s*:\s*\{[^}]*\}',
        r'api[\'"]?\s*:\s*\{[^}]*\}'
    ]
    
    for pattern in config_patterns:
        matches = re.findall(pattern, html_content, re.IGNORECASE)
        if matches:
            print(f"   🔍 Found configuration: {matches[0][:100]}...")

def test_with_authentication():
    """Test with different authentication methods"""
    print("\n=== Testing Authentication Methods ===\n")
    
    # Test 1: No authentication
    print("1. Testing without authentication...")
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.get(f"{LOCAL_GEMMA3_URL}/v1/models", headers=headers, timeout=10)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            if response.text.startswith('<!doctype html>'):
                print("   ❌ Still getting HTML response")
                analyze_html_response(response.text)
            else:
                print("   ✅ Got non-HTML response!")
                print(f"   Response: {response.text[:200]}...")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 2: With API key if provided
    if LOCAL_GEMMA3_API_KEY:
        print(f"\n2. Testing with API key...")
        headers['Authorization'] = f'Bearer {LOCAL_GEMMA3_API_KEY}'
        try:
            response = requests.get(f"{LOCAL_GEMMA3_URL}/v1/models", headers=headers, timeout=10)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                if response.text.startswith('<!doctype html>'):
                    print("   ❌ Still getting HTML response")
                else:
                    print("   ✅ Got non-HTML response!")
                    print(f"   Response: {response.text[:200]}...")
        except Exception as e:
            print(f"   Error: {e}")
    
    # Test 3: Different authentication headers
    print(f"\n3. Testing different auth headers...")
    auth_headers = [
        {'X-API-Key': LOCAL_GEMMA3_API_KEY} if LOCAL_GEMMA3_API_KEY else {},
        {'Authorization': f'Token {LOCAL_GEMMA3_API_KEY}'} if LOCAL_GEMMA3_API_KEY else {},
        {'X-Auth-Token': LOCAL_GEMMA3_API_KEY} if LOCAL_GEMMA3_API_KEY else {}
    ]
    
    for i, auth_header in enumerate(auth_headers):
        if auth_header:
            print(f"   Testing auth method {i+1}...")
            headers.update(auth_header)
            try:
                response = requests.get(f"{LOCAL_GEMMA3_URL}/v1/models", headers=headers, timeout=10)
                print(f"   Status: {response.status_code}")
                if response.status_code == 200 and not response.text.startswith('<!doctype html>'):
                    print("   ✅ Got non-HTML response!")
                    print(f"   Response: {response.text[:200]}...")
                    break
            except Exception as e:
                print(f"   Error: {e}")

def test_web_interface_features():
    """Test web interface features to understand the setup"""
    print("\n=== Testing Web Interface Features ===\n")
    
    try:
        # Get the main page
        response = requests.get(LOCAL_GEMMA3_URL, timeout=10)
        if response.status_code == 200:
            html_content = response.text
            
            # Look for specific OpenWebUI features
            features = {
                'OpenWebUI': 'openwebui' in html_content.lower(),
                'API Documentation': 'api' in html_content.lower() and 'doc' in html_content.lower(),
                'Chat Interface': 'chat' in html_content.lower(),
                'Model Selection': 'model' in html_content.lower() and 'select' in html_content.lower(),
                'Gemma': 'gemma' in html_content.lower(),
                'Authentication': 'login' in html_content.lower() or 'auth' in html_content.lower(),
                'Settings': 'setting' in html_content.lower() or 'config' in html_content.lower()
            }
            
            print("Web Interface Features Found:")
            for feature, found in features.items():
                status = "✅" if found else "❌"
                print(f"   {status} {feature}")
            
            # Look for specific OpenWebUI indicators
            if 'openwebui' in html_content.lower():
                print("\n   🎯 This appears to be an OpenWebUI installation")
                
                # Look for version information
                version_match = re.search(r'version[\'"]?\s*:\s*[\'"]([^\'"]*)[\'"]', html_content, re.IGNORECASE)
                if version_match:
                    print(f"   📋 Version: {version_match.group(1)}")
                
                # Look for API configuration
                api_enabled = re.search(r'api[\'"]?\s*:\s*true', html_content, re.IGNORECASE)
                if api_enabled:
                    print("   🔧 API appears to be enabled")
                else:
                    print("   ⚠️  API might be disabled")
            
        else:
            print(f"❌ Cannot access web interface: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error testing web interface: {e}")

def test_alternative_endpoints():
    """Test alternative endpoints that might work"""
    print("\n=== Testing Alternative Endpoints ===\n")
    
    # Test endpoints that might bypass the web interface
    alternative_endpoints = [
        "/api/v1/",
        "/api/",
        "/v1/",
        "/rest/",
        "/graphql",
        "/api/graphql"
    ]
    
    headers = {'Content-Type': 'application/json'}
    if LOCAL_GEMMA3_API_KEY:
        headers['Authorization'] = f'Bearer {LOCAL_GEMMA3_API_KEY}'
    
    for endpoint in alternative_endpoints:
        print(f"Testing {endpoint}...")
        try:
            response = requests.get(f"{LOCAL_GEMMA3_URL}{endpoint}", headers=headers, timeout=10)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                if response.text.startswith('<!doctype html>'):
                    print("   ❌ HTML response")
                else:
                    print("   ✅ Non-HTML response!")
                    print(f"   Response: {response.text[:200]}...")
            elif response.status_code == 404:
                print("   ❌ Not found")
            elif response.status_code == 401:
                print("   🔐 Authentication required")
            elif response.status_code == 403:
                print("   🚫 Forbidden")
            else:
                print(f"   ❓ Unexpected status: {response.text[:100]}...")
                
        except Exception as e:
            print(f"   Error: {e}")

def provide_recommendations():
    """Provide recommendations based on findings"""
    print("\n=== Recommendations ===\n")
    
    print("Based on the diagnostic results:")
    print("1. 🔍 The server is returning HTML for all endpoints, which suggests:")
    print("   - API endpoints might be disabled")
    print("   - Authentication might be required")
    print("   - The server might be in web-only mode")
    print("   - API might be on a different port or path")
    
    print("\n2. 🛠️  Next steps to try:")
    print("   - Check OpenWebUI configuration for API settings")
    print("   - Look for API documentation in the web interface")
    print("   - Try accessing the web interface directly in a browser")
    print("   - Check if there's a separate API server or port")
    print("   - Look for environment variables that enable API access")
    
    print("\n3. 🔧 Common OpenWebUI API configuration:")
    print("   - API might need to be explicitly enabled")
    print("   - API might be on a different port (e.g., 5000 instead of 80/443)")
    print("   - API might require specific headers or authentication")
    print("   - API might use a different base path")
    
    print("\n4. 🌐 Manual testing:")
    print(f"   - Open {LOCAL_GEMMA3_URL} in a browser")
    print("   - Look for API documentation or settings")
    print("   - Check if there's a way to enable API access")
    print("   - Look for any API-related configuration options")

def main():
    """Main diagnostic function"""
    print("🔍 OpenWebUI API Configuration Debug Tool\n")
    
    print(f"Target URL: {LOCAL_GEMMA3_URL}")
    print(f"API Key: {'Set' if LOCAL_GEMMA3_API_KEY else 'Not set'}\n")
    
    # Test 1: Web interface features
    test_web_interface_features()
    
    # Test 2: Authentication methods
    test_with_authentication()
    
    # Test 3: Alternative endpoints
    test_alternative_endpoints()
    
    # Test 4: Provide recommendations
    provide_recommendations()
    
    print("\n💡 Immediate Actions:")
    print("1. Open the web interface in a browser to check configuration")
    print("2. Look for API settings or documentation")
    print("3. Check if there's a separate API port or endpoint")
    print("4. Verify that the OpenWebUI server is configured for API access")

if __name__ == "__main__":
    main() 