#!/usr/bin/env python3
"""
Test script for local Gemma3 integration
"""

import os
import sys
import requests
import base64
import json

# Configuration
LOCAL_GEMMA3_URL = os.environ.get('LOCAL_GEMMA3_URL', 'https://geospotx.com')
LOCAL_GEMMA3_API_KEY = os.environ.get('LOCAL_GEMMA3_API_KEY', '')

def test_local_gemma3_connection():
    """Test connection to local Gemma3 server"""
    print(f"Testing connection to: {LOCAL_GEMMA3_URL}")
    
    try:
        # Test basic connectivity
        response = requests.get(f"{LOCAL_GEMMA3_URL}/v1/models", timeout=10)
        print(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            models = response.json()
            print("Available models:")
            for model in models.get('data', []):
                print(f"  - {model.get('id', 'Unknown')}")
            return True
        else:
            print(f"Error: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"Connection error: {e}")
        return False

def test_local_gemma3_chat():
    """Test chat completion with local Gemma3"""
    print("\nTesting chat completion...")
    
    # Create a simple test image (1x1 pixel)
    test_image_data = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\xaa\xff\xd9'
    
    # Encode image to base64
    image_base64 = base64.b64encode(test_image_data).decode('utf-8')
    
    # Prepare the request payload
    payload = {
        "model": "gemma3",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Look carefully at this image. Is there a human person clearly and unambiguously visible? Only answer 'yes' if you are highly confident (90%+ certain) that there is a human being present. If there is any doubt, unclear shapes, shadows, or objects that might be mistaken for a person, answer 'no'. Answer with 'yes' or 'no'."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ],
        "stream": False,
        "temperature": 0.1,
        "max_tokens": 100
    }
    
    # Prepare headers
    headers = {
        'Content-Type': 'application/json'
    }
    
    # Add API key if provided
    if LOCAL_GEMMA3_API_KEY:
        headers['Authorization'] = f'Bearer {LOCAL_GEMMA3_API_KEY}'
    
    try:
        # Make request to local Gemma3 server
        api_url = f"{LOCAL_GEMMA3_URL}/v1/chat/completions"
        response = requests.post(api_url, json=payload, headers=headers, timeout=30)
        
        print(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            response_data = response.json()
            content = response_data['choices'][0]['message']['content']
            print(f"Response: {content}")
            return True
        else:
            print(f"Error: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return False

def main():
    """Main test function"""
    print("=== Local Gemma3 Integration Test ===\n")
    
    # Test 1: Basic connectivity
    print("1. Testing basic connectivity...")
    if test_local_gemma3_connection():
        print("✅ Basic connectivity test passed\n")
    else:
        print("❌ Basic connectivity test failed\n")
        return False
    
    # Test 2: Chat completion
    print("2. Testing chat completion...")
    if test_local_gemma3_chat():
        print("✅ Chat completion test passed\n")
    else:
        print("❌ Chat completion test failed\n")
        return False
    
    print("🎉 All tests passed! Local Gemma3 integration is working correctly.")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 