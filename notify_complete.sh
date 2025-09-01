#!/bin/bash

# Monitor the fetch process and notify when complete
while true; do
    if ! pgrep -f "fetch_all_lyrics.py" > /dev/null; then
        # Process completed
        echo -e "\a"  # Notification sound
        
        # Get final stats
        python3 -c "
import sqlite3
conn = sqlite3.connect('drake_discography.db')
cursor = conn.cursor()

cursor.execute('SELECT COUNT(*) FROM songs WHERE lyrics IS NOT NULL')
with_lyrics = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM songs')
total = cursor.fetchone()[0]

percentage = (with_lyrics / total) * 100

print('='*60)
print('✅ LYRICS FETCH COMPLETE!')
print('='*60)
print(f'Successfully fetched: {with_lyrics}/{total} songs ({percentage:.1f}%)')
conn.close()
"
        
        # Check log for summary
        echo ""
        echo "Fetch Summary:"
        tail -10 lyrics_fetch.log | grep -E "(complete|successful|failed)"
        
        break
    fi
    sleep 30
done