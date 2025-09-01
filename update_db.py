#!/usr/bin/env python3

import sqlite3

def update_database():
    conn = sqlite3.connect('drake_discography.db')
    cursor = conn.cursor()
    
    # Check if lyrics column exists
    cursor.execute("PRAGMA table_info(songs)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'lyrics' not in columns:
        print("Adding lyrics column...")
        cursor.execute('''
            ALTER TABLE songs 
            ADD COLUMN lyrics TEXT
        ''')
        
    if 'lyrics_fetched_at' not in columns:
        print("Adding lyrics_fetched_at column...")
        cursor.execute('''
            ALTER TABLE songs 
            ADD COLUMN lyrics_fetched_at TIMESTAMP
        ''')
    
    conn.commit()
    
    # Show updated schema
    cursor.execute("PRAGMA table_info(songs)")
    print("\nUpdated schema:")
    for col in cursor.fetchall():
        print(f"  {col[1]} - {col[2]}")
    
    conn.close()
    print("\nDatabase updated successfully!")

if __name__ == '__main__':
    update_database()