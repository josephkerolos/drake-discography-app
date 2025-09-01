#!/usr/bin/env python3

import sqlite3
import time

def monitor_progress():
    while True:
        conn = sqlite3.connect('drake_discography.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM songs WHERE lyrics IS NOT NULL')
        with_lyrics = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM songs')
        total = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COUNT(*) FROM songs 
            WHERE lyrics IS NOT NULL 
            AND lyrics_fetched_at > datetime('now', '-1 hour')
        ''')
        recent = cursor.fetchone()[0]
        
        conn.close()
        
        percentage = (with_lyrics / total) * 100
        remaining = total - with_lyrics
        
        print(f"\rProgress: {with_lyrics}/{total} ({percentage:.1f}%) | Remaining: {remaining} | Recent: {recent}", end='', flush=True)
        
        if remaining == 0:
            print("\n✅ All lyrics fetched!")
            break
            
        time.sleep(5)

if __name__ == '__main__':
    print("Monitoring lyrics fetch progress...")
    print("-" * 50)
    monitor_progress()