# AI Model Integration for Person Detection

This camera server now supports two AI models for person detection:

1. **Google Gemini AI** (default) - Uses Google's Gemini 2.0 Flash model
2. **Local Gemma3** - Uses your local Gemma3 model via OpenWebUI

## Configuration

### Environment Variables (Initial Setup)

You can configure the AI model using environment variables for initial setup:

```bash
# Choose AI model: 'gemini' or 'local_gemma3'
export AI_MODEL_TYPE=local_gemma3

# Local Gemma3 server URL (required for local_gemma3)
export LOCAL_GEMMA3_URL=https://geospotx.com

# Local Gemma3 API key (optional)
export LOCAL_GEMMA3_API_KEY=your_api_key_here

# Google Gemini API key (required for gemini)
export GEMINI_API_KEY=your_gemini_api_key_here
```

### Persistent Configuration

The AI model configuration is automatically saved to `ai_config.json` and persists across server restarts. This file is created when you first configure the AI model through the web interface.

### Web Interface Configuration

You can also configure the AI model through the web interface:

1. Go to the Dashboard
2. Click "🤖 AI Configuration"
3. Select your preferred AI model
4. Configure the settings
5. Click "Save Configuration"

## Local Gemma3 Setup

### Prerequisites

1. **OpenWebUI Server**: You need a running OpenWebUI server with Gemma3 model loaded
2. **Network Access**: The camera server must be able to reach your OpenWebUI server
3. **API Endpoint**: OpenWebUI must expose the `/v1/chat/completions` endpoint

### OpenWebUI Configuration

1. Install and run OpenWebUI on your server
2. Load the Gemma3 model (e.g., `gemma-3-27b-it`)
3. Ensure the API is accessible at `https://geospotx.com/v1/chat/completions`
4. Configure authentication if needed

### Testing Local Gemma3

Use the provided test script to verify your setup:

```bash
# Set environment variables
export LOCAL_GEMMA3_URL=https://geospotx.com
export LOCAL_GEMMA3_API_KEY=your_api_key_here  # if required

# Run the test
python3 test_local_gemma3.py
```

The test script will:
1. Check connectivity to your OpenWebUI server
2. List available models
3. Test a sample person detection request

## Model Comparison

| Feature | Google Gemini | Local Gemma3 |
|---------|---------------|--------------|
| **Accuracy** | High | High |
| **Speed** | Fast | Variable (depends on hardware) |
| **Cost** | Per API call | Free (local) |
| **Privacy** | Data sent to Google | Completely local |
| **Setup** | API key only | Requires local server |
| **Reliability** | High | Depends on local infrastructure |

## Switching Between Models

### Via Environment Variables

```bash
# Use Google Gemini
export AI_MODEL_TYPE=gemini

# Use Local Gemma3
export AI_MODEL_TYPE=local_gemma3
```

### Via Web Interface

1. Navigate to "🤖 AI Configuration"
2. Select your preferred model
3. Configure the settings
4. Save the configuration

The system will automatically use the selected model for all future person detection cycles.

## Monitoring

### Logs

Person detection logs show which AI model is being used:

```
2024-01-15 10:30:00 - person_detection - INFO - Using Local Gemma3 for person detection
2024-01-15 10:30:05 - person_detection - INFO - Local Gemma3 response for person detection: no
```

### Web Interface

The Person Detection Logs page displays:
- Current AI model being used
- Local server URL (if using local Gemma3)
- Real-time detection results

## Troubleshooting

### Local Gemma3 Issues

1. **Connection Failed**
   - Check if OpenWebUI server is running
   - Verify the URL is correct
   - Check network connectivity

2. **Authentication Error**
   - Verify API key is correct
   - Check if authentication is required

3. **Model Not Found**
   - Ensure Gemma3 model is loaded in OpenWebUI
   - Check model name in configuration

4. **Slow Response**
   - Check server hardware resources
   - Consider using a more powerful server
   - Verify model is properly optimized

### Testing

Run the test script to diagnose issues:

```bash
python3 test_local_gemma3.py
```

### Logs

Check the person detection logs for detailed error messages:

```bash
tail -f logs/person_detection.log
```

## Performance Considerations

### Local Gemma3

- **Hardware**: Requires sufficient RAM and GPU/CPU
- **Network**: Low latency connection to OpenWebUI server
- **Model Size**: Gemma3-27B requires significant resources
- **Concurrent Requests**: Consider request queuing for high load

### Google Gemini

- **API Limits**: Check Google's rate limits
- **Cost**: Monitor API usage and costs
- **Network**: Requires internet connectivity

## Security

### Local Gemma3

- **Network Security**: Ensure secure connection to OpenWebUI
- **API Keys**: Store API keys securely
- **Server Access**: Restrict access to OpenWebUI server

### Google Gemini

- **API Key Security**: Keep Gemini API key secure
- **Data Privacy**: Images are sent to Google for processing

## Migration Guide

### From Gemini to Local Gemma3

1. Set up OpenWebUI server with Gemma3
2. Configure environment variables
3. Test the connection
4. Update AI model configuration
5. Monitor detection results

### From Local Gemma3 to Gemini

1. Obtain Google Gemini API key
2. Set `AI_MODEL_TYPE=gemini`
3. Set `GEMINI_API_KEY`
4. Test the configuration
5. Monitor detection results 