#!/usr/bin/env python3

import sqlite3
import sys
import time
from datetime import datetime
from fetch_lyrics_fixed import fetch_lyrics_from_genius, clean_lyrics

def clear_bad_lyrics():
    """Clear all bad lyrics from database"""
    conn = sqlite3.connect('drake_discography.db')
    cursor = conn.cursor()
    
    print("Clearing bad lyrics from database...")
    
    # Clear lyrics that are obviously metadata
    cursor.execute('''
        UPDATE songs 
        SET lyrics = NULL, lyrics_fetched_at = NULL
        WHERE lyrics LIKE '%Contributors%' 
           OR lyrics LIKE '%Translations%'
           OR lyrics LIKE '%Русский%'
           OR lyrics LIKE '%Español%'
           OR LENGTH(lyrics) < 200
           OR lyrics NOT LIKE '%[%'
    ''')
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    print(f"✓ Cleared {affected} bad lyrics entries")
    return affected

def update_lyrics_batch(limit=50):
    """Update a batch of songs with proper lyrics"""
    conn = sqlite3.connect('drake_discography.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get songs without lyrics
    cursor.execute('''
        SELECT id, title, artist, url
        FROM songs
        WHERE url IS NOT NULL
          AND lyrics IS NULL
        ORDER BY views DESC
        LIMIT ?
    ''', (limit,))
    songs = cursor.fetchall()
    
    if not songs:
        print("No songs to update!")
        conn.close()
        return 0, 0
    
    total_songs = len(songs)
    print(f"\nUpdating {total_songs} songs...")
    print("-" * 60)
    
    success_count = 0
    error_count = 0
    
    for i, song in enumerate(songs, 1):
        progress = (i / total_songs) * 100
        print(f"[{i}/{total_songs}] ({progress:.1f}%) {song['title'][:40]}...", end='')
        sys.stdout.flush()
        
        lyrics = fetch_lyrics_from_genius(song['url'])
        
        if lyrics and len(lyrics) > 200:
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
        
        # Rate limiting - be respectful
        time.sleep(1.5)
        
        if i % 10 == 0:
            print(f"  Progress: {success_count} successful, {error_count} failed")
    
    conn.close()
    
    print("-" * 60)
    print(f"Batch complete: {success_count} successful, {error_count} failed")
    
    return success_count, error_count

def get_database_stats():
    """Get current database statistics"""
    conn = sqlite3.connect('drake_discography.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM songs')
    total = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM songs WHERE lyrics IS NOT NULL')
    with_lyrics = cursor.fetchone()[0]
    
    cursor.execute('''
        SELECT COUNT(*) FROM songs 
        WHERE lyrics IS NOT NULL 
          AND LENGTH(lyrics) > 500
          AND lyrics LIKE '%[%'
    ''')
    with_good_lyrics = cursor.fetchone()[0]
    
    conn.close()
    
    return total, with_lyrics, with_good_lyrics

def main():
    print("Drake Lyrics Database Fixer")
    print("=" * 60)
    
    # Get initial stats
    total, with_lyrics, with_good = get_database_stats()
    print(f"\nInitial Database Stats:")
    print(f"  Total songs: {total}")
    print(f"  Songs with lyrics: {with_lyrics}")
    print(f"  Songs with good lyrics: {with_good}")
    
    # Step 1: Clear bad lyrics
    print(f"\nStep 1: Clearing bad lyrics...")
    cleared = clear_bad_lyrics()
    
    # Get updated stats
    total, with_lyrics, with_good = get_database_stats()
    print(f"\nUpdated Database Stats:")
    print(f"  Total songs: {total}")
    print(f"  Songs with lyrics: {with_lyrics}")
    print(f"  Songs with good lyrics: {with_good}")
    
    # Step 2: Fetch new lyrics in batches
    print(f"\nStep 2: Fetching proper lyrics...")
    print(f"Will fetch lyrics for top {min(50, total - with_lyrics)} songs by views")
    
    total_success = 0
    total_errors = 0
    
    # Do one batch of 50 songs
    success, errors = update_lyrics_batch(50)
    total_success += success
    total_errors += errors
    
    # Final stats
    total, with_lyrics, with_good = get_database_stats()
    print(f"\n" + "=" * 60)
    print(f"FINAL Database Stats:")
    print(f"  Total songs: {total}")
    print(f"  Songs with lyrics: {with_lyrics} ({with_lyrics/total*100:.1f}%)")
    print(f"  Songs with good lyrics: {with_good} ({with_good/total*100:.1f}%)")
    print(f"\nFetching Summary:")
    print(f"  Successfully fetched: {total_success}")
    print(f"  Failed: {total_errors}")
    
    if with_good > 0:
        print(f"\n✓ Database has been improved! Ready for re-vectorization.")
    else:
        print(f"\n⚠ Warning: Still no good lyrics found. Check fetching method.")

if __name__ == '__main__':
    main()