#!/usr/bin/env python3

import sqlite3
import requests
from bs4 import BeautifulSoup
import os
import sys
import time
from datetime import datetime
import re
import json

def fetch_lyrics_from_genius(url):
    """Fetch actual lyrics from Genius URL - fixed version"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Method 1: Look for the lyrics in the page's embedded JSON data
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string and 'window.__PRELOADED_STATE__' in script.string:
                # Extract the JSON data
                json_text = script.string
                json_text = json_text.split('window.__PRELOADED_STATE__ = ')[1]
                json_text = json_text.replace('undefined', 'null')
                # Remove trailing semicolon
                json_text = json_text.rstrip(';')
                
                try:
                    data = json.loads(json_text)
                    # Navigate through the JSON structure to find lyrics
                    if 'songPage' in data and 'lyricsData' in data['songPage']:
                        lyrics_data = data['songPage']['lyricsData']
                        if 'body' in lyrics_data:
                            lyrics_html = lyrics_data['body']['html']
                            # Parse the HTML to get clean text
                            lyrics_soup = BeautifulSoup(lyrics_html, 'html.parser')
                            lyrics = lyrics_soup.get_text(separator='\n')
                            return clean_lyrics(lyrics)
                except:
                    pass
        
        # Method 2: Try the container divs but filter out metadata
        containers = soup.find_all('div', {'data-lyrics-container': 'true'})
        
        if containers:
            lyrics_parts = []
            for container in containers:
                # Get the text
                text = container.get_text(separator='\n')
                
                # Skip if it starts with contributor count (metadata)
                if re.match(r'^\d+\s*Contributors?', text):
                    continue
                    
                # Skip if it's too short (likely metadata)
                if len(text) < 50:
                    continue
                    
                # Keep if it has lyrics markers or looks like lyrics
                if '[' in text or len(text.split('\n')) > 3:
                    # Clean the text
                    for br in container.find_all('br'):
                        br.replace_with('\n')
                    text = container.get_text(separator='\n')
                    lyrics_parts.append(text)
            
            if lyrics_parts:
                lyrics = '\n\n'.join(lyrics_parts)
                return clean_lyrics(lyrics)
        
        # Method 3: Look for divs with class containing "Lyrics"
        lyrics_divs = soup.find_all('div', class_=lambda x: x and 'Lyrics' in x)
        if lyrics_divs:
            lyrics_parts = []
            for div in lyrics_divs:
                text = div.get_text(separator='\n')
                if len(text) > 100 and not text.startswith('Contributors'):
                    lyrics_parts.append(text)
            
            if lyrics_parts:
                lyrics = '\n\n'.join(lyrics_parts)
                return clean_lyrics(lyrics)
        
        return None
        
    except Exception as e:
        print(f"  Error: {str(e)[:100]}")
        return None

def clean_lyrics(lyrics):
    """Clean and validate lyrics text"""
    if not lyrics:
        return None
    
    # Remove common artifacts
    lyrics = re.sub(r'[\d+]?EmbedShare.*?URLCopyEmbedCopy', '', lyrics)
    lyrics = re.sub(r'[\d+]?Embed$', '', lyrics)
    lyrics = re.sub(r'You might also like.*?\n', '', lyrics)
    lyrics = re.sub(r'See.*?LiveGet tickets as low as \$\d+', '', lyrics)
    
    # Remove contributor counts
    lyrics = re.sub(r'^\d+\s*Contributors?.*?Lyrics?\s*', '', lyrics, flags=re.MULTILINE | re.DOTALL)
    lyrics = re.sub(r'^\d+\s*Contributors?.*?\n', '', lyrics, flags=re.MULTILINE)
    
    # Remove translation headers
    lyrics = re.sub(r'Translations?\s*\n.*?(?=\[|\n\n)', '', lyrics, flags=re.DOTALL)
    
    # Clean excessive whitespace
    lyrics = re.sub(r'\n{3,}', '\n\n', lyrics)
    lyrics = lyrics.strip()
    
    # Validate
    if len(lyrics) < 100:
        return None
    
    # Check for actual lyrics content (not just metadata)
    lines = lyrics.split('\n')
    content_lines = [line for line in lines if len(line.strip()) > 0]
    
    if len(content_lines) < 5:
        return None
    
    # Check if it looks like lyrics (has verses, choruses, or multiple lines of text)
    has_structure = any(marker in lyrics for marker in ['[Verse', '[Chorus', '[Intro', '[Outro', '[Hook', '[Bridge'])
    has_content = len(content_lines) > 10
    
    if not has_structure and not has_content:
        return None
    
    return lyrics

def test_single_song():
    """Test fetching a single song"""
    test_urls = [
        ('https://genius.com/Drake-gods-plan-lyrics', "God's Plan", "Drake"),
        ('https://genius.com/Drake-one-dance-lyrics', "One Dance", "Drake"),
        ('https://genius.com/Drake-hotline-bling-lyrics', "Hotline Bling", "Drake")
    ]
    
    print("Testing improved lyrics fetching...")
    
    for url, title, artist in test_urls:
        print(f"\nTesting: {title} by {artist}")
        print(f"  URL: {url}")
        
        lyrics = fetch_lyrics_from_genius(url)
        
        if lyrics:
            print(f"  ✓ Success! Got {len(lyrics)} characters")
            # Show first few lines (avoiding copyright issues)
            preview_lines = lyrics.split('\n')[:5]
            print(f"  First 5 lines:")
            for line in preview_lines:
                if line.strip():
                    print(f"    {line[:50]}...")
            print(f"  Total lines: {len(lyrics.split(chr(10)))}")
            return True
        else:
            print(f"  ✗ Failed to fetch lyrics")
    
    return False

def clear_bad_lyrics():
    """Clear the bad lyrics data from database"""
    conn = sqlite3.connect('drake_discography.db')
    cursor = conn.cursor()
    
    print("\nChecking current lyrics quality...")
    
    # Check a sample
    cursor.execute('''
        SELECT id, title, artist, SUBSTR(lyrics, 1, 100) as preview
        FROM songs
        WHERE lyrics IS NOT NULL
        LIMIT 5
    ''')
    
    bad_count = 0
    for row in cursor.fetchall():
        preview = row[3]
        if preview and ('Contributors' in preview or 'Translations' in preview):
            bad_count += 1
    
    if bad_count > 0:
        print(f"Found {bad_count}/5 songs with bad lyrics (metadata instead of lyrics)")
        
        # Count total bad lyrics
        cursor.execute('''
            SELECT COUNT(*) 
            FROM songs 
            WHERE lyrics LIKE '%Contributors%' 
               OR lyrics LIKE '%Translations%'
               OR LENGTH(lyrics) < 200
        ''')
        total_bad = cursor.fetchone()[0]
        
        print(f"Total songs with bad lyrics: {total_bad}")
        
        response = input("\nDo you want to clear these bad lyrics? (yes/no): ")
        if response.lower() in ['yes', 'y']:
            cursor.execute('''
                UPDATE songs 
                SET lyrics = NULL, lyrics_fetched_at = NULL
                WHERE lyrics LIKE '%Contributors%' 
                   OR lyrics LIKE '%Translations%'
                   OR LENGTH(lyrics) < 200
            ''')
            conn.commit()
            print(f"✓ Cleared {total_bad} bad lyrics entries")
    else:
        print("✓ Lyrics look good!")
    
    conn.close()

def update_all_lyrics():
    """Update all songs with proper lyrics"""
    conn = sqlite3.connect('drake_discography.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get songs without lyrics or with bad lyrics
    cursor.execute('''
        SELECT id, title, artist, url
        FROM songs
        WHERE url IS NOT NULL
          AND (lyrics IS NULL 
               OR lyrics LIKE '%Contributors%'
               OR lyrics LIKE '%Translations%'
               OR LENGTH(lyrics) < 200)
        ORDER BY views DESC
        LIMIT 100
    ''')
    songs = cursor.fetchall()
    
    total_songs = len(songs)
    print(f"\nFound {total_songs} songs to update")
    print("-" * 60)
    
    success_count = 0
    error_count = 0
    
    for i, song in enumerate(songs, 1):
        progress = (i / total_songs) * 100
        print(f"[{i}/{total_songs}] ({progress:.1f}%) {song['title'][:30]}...", end='')
        sys.stdout.flush()
        
        lyrics = fetch_lyrics_from_genius(song['url'])
        
        if lyrics:
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
        
        time.sleep(1.5)  # Rate limiting
        
        if i % 10 == 0:
            print(f"  Progress: {success_count} successful, {error_count} failed")
    
    print("-" * 60)
    print(f"\nUpdate complete!")
    print(f"Successfully fetched: {success_count} lyrics")
    print(f"Failed: {error_count}")
    
    conn.close()

if __name__ == '__main__':
    print("Drake Lyrics Fetcher - Fixed Web Scraping")
    print("=" * 60)
    
    if test_single_song():
        print("\n✓ Test successful! Lyrics fetching is working.")
        
        # Clear bad lyrics
        clear_bad_lyrics()
        
        # Update lyrics
        response = input("\nDo you want to update lyrics for songs? (yes/no): ")
        if response.lower() in ['yes', 'y']:
            update_all_lyrics()
    else:
        print("\n✗ All methods failed. Genius may have changed their site structure.")