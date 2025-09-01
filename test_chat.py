#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chat_handler import get_chat_handler

# Set API key from environment or prompt user
if not os.getenv('OPENAI_API_KEY'):
    print("Please set OPENAI_API_KEY environment variable")
    sys.exit(1)

# Test queries
test_queries = [
    "When does Drake talk about his mother?",
    "What songs mention Toronto or the 6?", 
    "Find lyrics about success and money",
    "When does Drake talk about relationships?"
]

print("Testing improved RAG system with real lyrics...")
print("=" * 60)

handler = get_chat_handler()

for query in test_queries:
    print(f"\nQuery: {query}")
    print("-" * 40)
    result = handler.chat(query)
    if result.get('response'):
        print(f"Response preview: {result['response'][:300]}...")
        print(f"Citations found: {len(result.get('citations', []))}")
        if result.get('citations'):
            print(f"First citation: {result['citations'][0]['title']} by {result['citations'][0]['artist']}")
    else:
        print("No response generated")

print("\n✓ All tests complete!")