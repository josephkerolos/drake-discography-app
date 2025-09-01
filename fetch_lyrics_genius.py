#!/usr/bin/env python3

import sqlite3
import lyricsgenius
import os
import sys
import time
from datetime import datetime
import re

# Genius API token (you'll need to get this from https://genius.com/api-clients)
# For now, we'll try without token (limited access)
GENIUS_TOKEN = os.getenv('GENIUS_ACCESS_TOKEN')

def clean_lyrics(lyrics):
    """Clean lyrics text from Genius"""
    if not lyrics:
        return None
    
    # Remove the "EmbedShare URLCopyEmbedCopy" and similar artifacts
    lyrics = re.sub(r'[\d+]?EmbedShare.*?URLCopyEmbedCopy', '', lyrics)
    lyrics = re.sub(r'[\d+]?Embed$', '', lyrics)
    lyrics = re.sub(r'You might also like', '', lyrics)
    
    # Remove contributor count at the beginning if present
    lyrics = re.sub(r'^\d+\s*Contributors?.*?Lyrics', '', lyrics, flags=re.MULTILINE | re.DOTALL)
    
    # Clean up excessive whitespace
    lyrics = re.sub(r'\n{3,}', '\n\n', lyrics)
    lyrics = lyrics.strip()
    
    # Validate that we have actual lyrics (should contain verse/chorus markers or substantial text)
    if len(lyrics) < 100:
        return None
    
    # Check if it contains typical lyrics patterns
    has_structure = any(marker in lyrics.upper() for marker in ['[VERSE', '[CHORUS', '[INTRO', '[OUTRO', '[HOOK', '[BRIDGE'])
    has_content = len(lyrics.split('\n')) > 5  # At least 5 lines
    
    if not has_structure and not has_content:
        return None
    
    return lyrics

def fetch_lyrics_with_genius(title, artist):
    """Fetch lyrics using LyricsGenius API"""
    try:
        # Initialize Genius API
        if GENIUS_TOKEN:
            genius = lyricsgenius.Genius(GENIUS_TOKEN, timeout=10, retries=2)
        else:
            # Try without token (limited functionality)
            genius = lyricsgenius.Genius(timeout=10, retries=2)
        
        # Disable verbose output
        genius.verbose = False
        genius.remove_section_headers = False  # Keep [Verse], [Chorus] markers
        
        # Search for the song
        song = genius.search_song(title, artist)
        
        if song and song.lyrics:
            cleaned_lyrics = clean_lyrics(song.lyrics)
            return cleaned_lyrics
        
        return None
        
    except Exception as e:
        print(f"  Error with LyricsGenius: {str(e)[:50]}")
        return None

def test_single_song():
    """Test fetching a single song to verify it works"""
    print("Testing LyricsGenius with a single song...")
    
    test_songs = [
        ("God's Plan", "Drake"),
        ("One Dance", "Drake"),
        ("Hotline Bling", "Drake")
    ]
    
    for title, artist in test_songs:
        print(f"\nTesting: {title} by {artist}")
        lyrics = fetch_lyrics_with_genius(title, artist)
        
        if lyrics:
            print(f"  ✓ Success! Got {len(lyrics)} characters")
            print(f"  First 200 chars: {lyrics[:200]}...")
            print(f"  Lines: {len(lyrics.split(chr(10)))}")
            
            # Check if it has verse/chorus structure
            has_structure = any(marker in lyrics.upper() for marker in ['[VERSE', '[CHORUS', '[INTRO'])
            print(f"  Has structure markers: {has_structure}")
            return True
        else:
            print(f"  ✗ Failed to fetch lyrics")
    
    return False

def update_all_lyrics():
    """Update all songs in database with proper lyrics"""
    conn = sqlite3.connect('drake_discography.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all songs
    cursor.execute('''
        SELECT id, title, artist, url
        FROM songs
        ORDER BY views DESC
    ''')
    songs = cursor.fetchall()
    
    total_songs = len(songs)
    print(f"\nFound {total_songs} songs to update")
    print("This will take approximately {:.1f} minutes".format(total_songs * 2 / 60))
    print("-" * 60)
    
    success_count = 0
    error_count = 0
    
    for i, song in enumerate(songs, 1):
        # Progress indicator
        progress = (i / total_songs) * 100
        print(f"[{i}/{total_songs}] ({progress:.1f}%) {song['title'][:30]} - {song['artist'][:20]}...", end='')
        sys.stdout.flush()
        
        # Fetch lyrics
        lyrics = fetch_lyrics_with_genius(song['title'], song['artist'])
        
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
        
        # Rate limiting
        time.sleep(2)  # Be respectful to Genius servers
        
        # Show progress every 10 songs
        if i % 10 == 0:
            print(f"  Progress: {success_count} successful, {error_count} failed")
    
    print("-" * 60)
    print(f"\nUpdate complete!")
    print(f"Successfully fetched: {success_count} lyrics")
    print(f"Failed: {error_count}")
    
    conn.close()

if __name__ == '__main__':
    print("Drake Lyrics Fetcher - Using LyricsGenius")
    print("=" * 60)
    
    # First test with a single song
    if test_single_song():
        print("\n✓ Test successful! LyricsGenius is working.")
        
        # Ask user if they want to update all songs
        response = input("\nDo you want to update ALL songs in the database? (yes/no): ")
        if response.lower() in ['yes', 'y']:
            update_all_lyrics()
        else:
            print("Skipping full update.")
    else:
        print("\n✗ Test failed. Please check your internet connection or Genius API access.")
        print("You may need to set GENIUS_ACCESS_TOKEN environment variable.")
        print("Get a token from: https://genius.com/api-clients")