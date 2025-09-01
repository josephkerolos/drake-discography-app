#!/usr/bin/env python3

import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

api_key = os.getenv('OPENAI_API_KEY')
print(f"Testing API key: {api_key[:7]}...{api_key[-4:]}")

try:
    client = OpenAI(api_key=api_key)
    
    # Try a simple completion
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Say 'API key works!'"}],
        max_tokens=10
    )
    
    print(f"✅ SUCCESS: {response.choices[0].message.content}")
    
except Exception as e:
    print(f"❌ ERROR: {e}")
    print("\nThis API key is invalid or expired.")
    print("Please get a new API key from: https://platform.openai.com/api-keys")
    print("\nThen set it in Railway:")
    print("1. Go to your Railway project")
    print("2. Click on the 'web' service")
    print("3. Go to Variables tab")
    print("4. Add: OPENAI_API_KEY=your-new-key-here")