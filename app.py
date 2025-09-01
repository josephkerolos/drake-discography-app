from flask import Flask, render_template, request, jsonify
import sqlite3
import os
from math import ceil

app = Flask(__name__)
app.config['DATABASE'] = 'drake_discography.db'

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