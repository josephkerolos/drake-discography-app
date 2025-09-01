from flask import Flask, render_template, request, jsonify, session
import sqlite3
import os
from dotenv import load_dotenv
from math import ceil
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import time
import re
import secrets

# Load environment variables from .env file
load_dotenv()

from chat_handler import get_chat_handler

app = Flask(__name__)
app.config['DATABASE'] = 'drake_discography.db'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))

def get_db_connection():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    conn = get_db_connection()
    
    page = request.args.get('page', 1, type=int)
    per_page = 50
    search = request.args.get('search', '')
    sort_by = request.args.get('sort', 'views')
    order = request.args.get('order', 'desc')
    artist_filter = request.args.get('artist', '')
    
    query = 'SELECT * FROM songs WHERE 1=1'
    params = []
    
    if search:
        query += ' AND (title LIKE ? OR artist LIKE ?)'
        params.extend([f'%{search}%', f'%{search}%'])
    
    if artist_filter:
        if artist_filter == 'drake_solo':
            query += ' AND artist = ?'
            params.append('Drake')
        elif artist_filter == 'drake_featured':
            query += ' AND featured_drake = 1'
    
    count_query = f'SELECT COUNT(*) as total FROM ({query})'
    cursor = conn.execute(count_query, params)
    total_songs = cursor.fetchone()['total']
    total_pages = ceil(total_songs / per_page)
    
    sort_column = 'views' if sort_by == 'views' else 'title' if sort_by == 'title' else 'artist'
    query += f' ORDER BY {sort_column} {order.upper()}'
    query += f' LIMIT ? OFFSET ?'
    params.extend([per_page, (page - 1) * per_page])
    
    songs = conn.execute(query, params).fetchall()
    
    stats_cursor = conn.execute('''
        SELECT 
            COUNT(*) as total,
            COUNT(DISTINCT artist) as artists,
            SUM(views) as total_views,
            (SELECT COUNT(*) FROM songs WHERE artist = 'Drake') as drake_solo,
            (SELECT COUNT(*) FROM songs WHERE featured_drake = 1) as drake_featured
        FROM songs
    ''')
    stats = stats_cursor.fetchone()
    
    conn.close()
    
    return render_template('index.html', 
                         songs=songs, 
                         page=page,
                         total_pages=total_pages,
                         total_songs=total_songs,
                         search=search,
                         sort_by=sort_by,
                         order=order,
                         artist_filter=artist_filter,
                         stats=stats)

@app.route('/api/stats')
def api_stats():
    conn = get_db_connection()
    
    top_songs = conn.execute('''
        SELECT title, artist, views, url
        FROM songs
        ORDER BY views DESC
        LIMIT 10
    ''').fetchall()
    
    top_collaborators = conn.execute('''
        SELECT artist, COUNT(*) as count, SUM(views) as total_views
        FROM songs
        WHERE artist != 'Drake' AND featured_drake = 1
        GROUP BY artist
        ORDER BY count DESC
        LIMIT 10
    ''').fetchall()
    
    conn.close()
    
    return jsonify({
        'top_songs': [dict(song) for song in top_songs],
        'top_collaborators': [dict(collab) for collab in top_collaborators]
    })

@app.route('/api/lyrics/<int:song_id>')
def fetch_lyrics(song_id):
    conn = get_db_connection()
    
    # Check if lyrics already exist
    song = conn.execute('SELECT * FROM songs WHERE id = ?', (song_id,)).fetchone()
    
    if not song:
        conn.close()
        return jsonify({'error': 'Song not found'}), 404
    
    # Return cached lyrics if available
    if song['lyrics']:
        conn.close()
        return jsonify({
            'lyrics': song['lyrics'],
            'title': song['title'],
            'artist': song['artist'],
            'cached': True
        })
    
    # Fetch lyrics from Genius
    if not song['url']:
        conn.close()
        return jsonify({'error': 'No URL available for this song'}), 400
    
    try:
        # Add delay to be respectful to Genius servers
        time.sleep(1)
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(song['url'], headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'lxml')
        
        # Find lyrics container
        lyrics_divs = soup.find_all('div', {'data-lyrics-container': 'true'})
        
        if not lyrics_divs:
            conn.close()
            return jsonify({'error': 'Lyrics not found on page'}), 404
        
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
        lyrics = re.sub(r'\n{3,}', '\n\n', lyrics)  # Remove excessive line breaks
        lyrics = lyrics.strip()
        
        # Save to database
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE songs 
            SET lyrics = ?, lyrics_fetched_at = ? 
            WHERE id = ?
        ''', (lyrics, datetime.now(), song_id))
        conn.commit()
        conn.close()
        
        return jsonify({
            'lyrics': lyrics,
            'title': song['title'],
            'artist': song['artist'],
            'cached': False
        })
        
    except requests.RequestException as e:
        conn.close()
        return jsonify({'error': f'Failed to fetch lyrics: {str(e)}'}), 500
    except Exception as e:
        conn.close()
        return jsonify({'error': f'Error parsing lyrics: {str(e)}'}), 500

@app.route('/chat')
def chat_page():
    return render_template('chat.html')

@app.route('/api/chat', methods=['POST'])
def chat_api():
    try:
        data = request.json
        query = data.get('query', '')
        conversation_history = data.get('history', [])
        
        if not query:
            return jsonify({'error': 'No query provided'}), 400
        
        # Get or create chat handler
        handler = get_chat_handler()
        
        # Process the chat
        result = handler.chat(query, conversation_history)
        
        if 'error' in result:
            return jsonify(result), 500
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat/suggestions')
def chat_suggestions():
    handler = get_chat_handler()
    return jsonify({'suggestions': handler.get_suggestions()})

@app.route('/api/vectorize/status')
def vectorize_status():
    try:
        handler = get_chat_handler()
        collection_count = handler.collection.count()
        
        conn = get_db_connection()
        cursor = conn.execute('SELECT COUNT(*) FROM songs WHERE lyrics IS NOT NULL')
        songs_with_lyrics = cursor.fetchone()[0]
        conn.close()
        
        return jsonify({
            'vectorized_chunks': collection_count,
            'songs_with_lyrics': songs_with_lyrics,
            'status': 'ready' if collection_count > 0 else 'needs_vectorization'
        })
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.route('/api/health')
def health_check():
    """Health check endpoint to debug environment variables and API configuration"""
    health_status = {
        'status': 'checking',
        'environment': {},
        'openai': {},
        'database': {},
        'chromadb': {}
    }
    
    # Check environment variables
    api_key = os.getenv('OPENAI_API_KEY')
    health_status['environment'] = {
        'OPENAI_API_KEY_set': bool(api_key),
        'OPENAI_API_KEY_prefix': api_key[:7] + '...' if api_key else None,
        'total_env_vars': len(os.environ),
        'railway_vars': {k: v for k, v in os.environ.items() if k.startswith('RAILWAY_')},
        'port': os.getenv('PORT', 'not set'),
        'secret_key_set': bool(os.getenv('SECRET_KEY'))
    }
    
    # Test OpenAI connection
    try:
        handler = get_chat_handler()
        client = handler._get_openai_client()
        if client:
            # Try a simple API call
            test_response = client.models.list()
            health_status['openai'] = {
                'status': 'connected',
                'client_initialized': True,
                'test_call': 'success'
            }
        else:
            health_status['openai'] = {
                'status': 'failed',
                'client_initialized': False,
                'error': 'Client could not be initialized'
            }
    except Exception as e:
        health_status['openai'] = {
            'status': 'error',
            'error': str(e)
        }
    
    # Check database
    try:
        conn = get_db_connection()
        cursor = conn.execute('SELECT COUNT(*) FROM songs')
        total_songs = cursor.fetchone()[0]
        cursor = conn.execute('SELECT COUNT(*) FROM songs WHERE lyrics IS NOT NULL')
        songs_with_lyrics = cursor.fetchone()[0]
        conn.close()
        
        health_status['database'] = {
            'status': 'connected',
            'total_songs': total_songs,
            'songs_with_lyrics': songs_with_lyrics
        }
    except Exception as e:
        health_status['database'] = {
            'status': 'error',
            'error': str(e)
        }
    
    # Check ChromaDB
    try:
        handler = get_chat_handler()
        collection_count = handler.collection.count()
        health_status['chromadb'] = {
            'status': 'connected',
            'collection_count': collection_count
        }
    except Exception as e:
        health_status['chromadb'] = {
            'status': 'error',
            'error': str(e)
        }
    
    # Overall status
    if (health_status['openai'].get('status') == 'connected' and 
        health_status['database'].get('status') == 'connected'):
        health_status['status'] = 'healthy'
    else:
        health_status['status'] = 'unhealthy'
    
    return jsonify(health_status)

@app.template_filter('format_views')
def format_views(views):
    if views >= 1_000_000:
        return f"{views/1_000_000:.1f}M"
    elif views >= 1_000:
        return f"{views/1_000:.0f}K"
    return str(views)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)