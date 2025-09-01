#!/bin/bash

echo "🎵 Drake Discography Lyrics Fetch Status"
echo "========================================"

# Check if process is running
if pgrep -f "fetch_all_lyrics.py" > /dev/null; then
    echo "✅ Fetch process is RUNNING"
else
    echo "⏹️  Fetch process has COMPLETED or STOPPED"
fi

echo ""

# Show last few lines from log
echo "Latest activity:"
tail -5 lyrics_fetch.log 2>/dev/null | grep -E "\[.*\]"

echo ""

# Database stats
python3 -c "
import sqlite3
conn = sqlite3.connect('drake_discography.db')
cursor = conn.cursor()

cursor.execute('SELECT COUNT(*) FROM songs WHERE lyrics IS NOT NULL')
with_lyrics = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM songs')
total = cursor.fetchone()[0]

remaining = total - with_lyrics
percentage = (with_lyrics / total) * 100
eta_minutes = (remaining * 1.5) / 60

print(f'📊 Database Statistics:')
print(f'   Songs with lyrics: {with_lyrics}/{total} ({percentage:.1f}%)')
print(f'   Remaining: {remaining} songs')
if remaining > 0:
    print(f'   Estimated time: {eta_minutes:.0f} minutes')
else:
    print(f'   ✅ ALL LYRICS FETCHED!')

conn.close()
"

echo ""
echo "Run 'tail -f lyrics_fetch.log' to watch live progress"