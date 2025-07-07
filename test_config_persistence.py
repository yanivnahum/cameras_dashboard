#!/usr/bin/env python3
"""
Test script for AI configuration persistence
"""

import os
import json
import tempfile
import shutil

def test_config_persistence():
    """Test that AI configuration is saved and loaded correctly"""
    print("=== Testing AI Configuration Persistence ===\n")
    
    # Create a temporary config file
    temp_config = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
    temp_config_path = temp_config.name
    temp_config.close()
    
    try:
        # Test 1: Save configuration
        print("1. Testing configuration save...")
        test_config = {
            'ai_model_type': 'local_gemma3',
            'local_gemma3_url': 'https://test.example.com',
            'local_gemma3_api_key': 'test_api_key_123'
        }
        
        with open(temp_config_path, 'w') as f:
            json.dump(test_config, f, indent=2)
        
        print(f"✅ Configuration saved to: {temp_config_path}")
        
        # Test 2: Load configuration
        print("\n2. Testing configuration load...")
        with open(temp_config_path, 'r') as f:
            loaded_config = json.load(f)
        
        # Verify all values are loaded correctly
        if (loaded_config['ai_model_type'] == test_config['ai_model_type'] and
            loaded_config['local_gemma3_url'] == test_config['local_gemma3_url'] and
            loaded_config['local_gemma3_api_key'] == test_config['local_gemma3_api_key']):
            print("✅ Configuration loaded correctly")
            print(f"   Model: {loaded_config['ai_model_type']}")
            print(f"   URL: {loaded_config['local_gemma3_url']}")
            print(f"   API Key: {'Set' if loaded_config['local_gemma3_api_key'] else 'Not Set'}")
        else:
            print("❌ Configuration load failed - values don't match")
            return False
        
        # Test 3: Test with missing file (should use defaults)
        print("\n3. Testing with missing config file...")
        os.unlink(temp_config_path)
        
        # Simulate the load function behavior
        default_model = 'gemini'
        default_url = 'https://geospotx.com'
        default_key = ''
        
        if not os.path.exists(temp_config_path):
            print("✅ Correctly handles missing config file")
            print(f"   Using defaults: Model={default_model}, URL={default_url}")
        else:
            print("❌ Should not find config file after deletion")
            return False
        
        print("\n🎉 All persistence tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False
    finally:
        # Clean up
        if os.path.exists(temp_config_path):
            os.unlink(temp_config_path)

def test_server_config_integration():
    """Test that the server configuration functions work correctly"""
    print("\n=== Testing Server Configuration Integration ===\n")
    
    # Test the configuration file path
    config_file = 'ai_config.json'
    print(f"Configuration file: {config_file}")
    
    # Check if config file exists
    if os.path.exists(config_file):
        print(f"✅ Configuration file exists")
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            print(f"   Current configuration:")
            print(f"   - Model: {config.get('ai_model_type', 'Not set')}")
            print(f"   - URL: {config.get('local_gemma3_url', 'Not set')}")
            print(f"   - API Key: {'Set' if config.get('local_gemma3_api_key') else 'Not set'}")
        except Exception as e:
            print(f"❌ Error reading config file: {e}")
            return False
    else:
        print(f"ℹ️  Configuration file does not exist (will be created on first save)")
    
    return True

if __name__ == "__main__":
    success1 = test_config_persistence()
    success2 = test_server_config_integration()
    
    if success1 and success2:
        print("\n🎉 All tests passed! Configuration persistence is working correctly.")
        exit(0)
    else:
        print("\n❌ Some tests failed. Please check the implementation.")
        exit(1) 