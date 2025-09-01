#!/usr/bin/env python3

import sqlite3
import os
import sys

def check_and_init():
    """Check if the system is ready for chat and initialize if needed"""
    
    # Check database
    if not os.path.exists('drake_discography.db'):
        print("❌ Database not found. Please run the app first.")
        return False
    
    conn = sqlite3.connect('drake_discography.db')
    cursor = conn.cursor()
    
    # Check lyrics count
    cursor.execute('SELECT COUNT(*) FROM songs WHERE lyrics IS NOT NULL')
    lyrics_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM songs')
    total_count = cursor.fetchone()[0]
    
    conn.close()
    
    percentage = (lyrics_count / total_count * 100) if total_count > 0 else 0
    
    print(f"✅ Database ready: {lyrics_count}/{total_count} songs have lyrics ({percentage:.1f}%)")
    
    # Check ChromaDB
    chroma_path = os.path.join(os.path.dirname(__file__), 'chroma_db')
    if os.path.exists(chroma_path):
        print("✅ Vector database exists")
    else:
        print("⚠️  Vector database not found. Will be created on first use.")
    
    # Check API key
    api_key = os.getenv('OPENAI_API_KEY')
    if api_key:
        print("✅ OpenAI API key configured")
    else:
        print("❌ OpenAI API key not set. Set OPENAI_API_KEY environment variable.")
        return False
    
    print("\n🎉 System ready for AI chat!")
    print("The chat will work with the current lyrics available.")
    print(f"Currently {percentage:.1f}% of songs have lyrics fetched.")
    
    return True

if __name__ == '__main__':
    check_and_init()