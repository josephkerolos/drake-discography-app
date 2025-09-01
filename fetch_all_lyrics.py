#!/usr/bin/env python3

import sqlite3
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import time
import re
import sys

def fetch_lyrics_from_url(url):
    """Fetch lyrics from a Genius URL"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'lxml')
        
        # Find lyrics container
        lyrics_divs = soup.find_all('div', {'data-lyrics-container': 'true'})
        
        if not lyrics_divs:
            return None
        
        # Extract lyrics text
        lyrics_parts = []
        for div in lyrics_divs:
            # Get text with line breaks preserved
            for br in div.find_all('br'):
                br.replace_with('\n')
            text = div.get_text(separator='\n')
            lyrics_parts.append(text)
        
        lyrics = '\n\n'.join(lyrics_parts)
        
        # Clean up lyrics
        lyrics = re.sub(r'\n{3,}', '\n\n', lyrics)
        lyrics = lyrics.strip()
        
        return lyrics
        
    except Exception as e:
        print(f"  Error: {str(e)[:50]}")
        return None

def fetch_all_lyrics():
    conn = sqlite3.connect('drake_discography.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all songs without lyrics
    cursor.execute('''
        SELECT id, title, artist, url 
        FROM songs 
        WHERE lyrics IS NULL AND url IS NOT NULL
        ORDER BY views DESC
    ''')
    songs = cursor.fetchall()
    
    total_songs = len(songs)
    print(f"Found {total_songs} songs without lyrics")
    print("Starting bulk fetch (this will take approximately {:.1f} minutes)".format(total_songs * 1.5 / 60))
    print("-" * 60)
    
    success_count = 0
    error_count = 0
    
    for i, song in enumerate(songs, 1):
        # Progress indicator
        progress = (i / total_songs) * 100
        print(f"[{i}/{total_songs}] ({progress:.1f}%) Fetching: {song['title'][:40]} - {song['artist'][:20]}...", end='')
        sys.stdout.flush()
        
        # Fetch lyrics
        lyrics = fetch_lyrics_from_url(song['url'])
        
        if lyrics:
            # Save to database
            cursor.execute('''
                UPDATE songs 
                SET lyrics = ?, lyrics_fetched_at = ? 
                WHERE id = ?
            ''', (lyrics, datetime.now(), song['id']))
            conn.commit()
            success_count += 1
            print(" ✓")
        else:
            error_count += 1
            print(" ✗")
        
        # Rate limiting - be respectful to Genius servers
        time.sleep(1.5)
        
        # Show progress summary every 10 songs
        if i % 10 == 0:
            print(f"  Progress: {success_count} successful, {error_count} failed")
    
    print("-" * 60)
    print(f"\nBulk fetch complete!")
    print(f"Successfully fetched: {success_count} lyrics")
    print(f"Failed: {error_count}")
    
    # Show statistics
    cursor.execute('SELECT COUNT(*) FROM songs WHERE lyrics IS NOT NULL')
    total_with_lyrics = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM songs')
    total_songs_db = cursor.fetchone()[0]
    
    print(f"\nDatabase statistics:")
    print(f"Total songs: {total_songs_db}")
    print(f"Songs with lyrics: {total_with_lyrics}")
    print(f"Coverage: {(total_with_lyrics/total_songs_db)*100:.1f}%")
    
    conn.close()

if __name__ == '__main__':
    print("Drake Discography - Bulk Lyrics Fetcher")
    print("=" * 60)
    
    # Auto-run without prompt when called directly
    fetch_all_lyrics()