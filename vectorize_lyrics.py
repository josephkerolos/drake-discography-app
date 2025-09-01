#!/usr/bin/env python3

import sqlite3
from openai import OpenAI
import chromadb
from chromadb.config import Settings
import os
import sys
import time
import re
from typing import List, Dict
import tiktoken
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OpenAI Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY not set. Please set it in environment variables.")
    sys.exit(1)

try:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    # Test the API key with a simple request
    test_response = openai_client.models.list()
    logger.info("OpenAI client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize OpenAI client: {e}")
    logger.error("Please check your OpenAI API key")
    sys.exit(1)

# Initialize ChromaDB
CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(__file__), 'chroma_db')
chroma_client = chromadb.PersistentClient(
    path=CHROMA_PERSIST_DIR,
    settings=Settings(anonymized_telemetry=False)
)

def chunk_lyrics(text: str, song_title: str, max_lines: int = 8) -> List[Dict]:
    """
    Split lyrics into semantic chunks preserving verses/sections
    """
    if not text:
        return []
    
    chunks = []
    lines = text.split('\n')
    current_chunk = []
    current_line_start = 1
    
    for i, line in enumerate(lines):
        # Check if this is a section break (empty line or chorus/verse marker)
        is_section_break = (
            line.strip() == '' or 
            any(marker in line.lower() for marker in ['[chorus', '[verse', '[intro', '[outro', '[bridge', '[hook'])
        )
        
        if is_section_break and current_chunk:
            # Save current chunk
            chunk_text = '\n'.join(current_chunk)
            if chunk_text.strip():
                chunks.append({
                    'text': chunk_text,
                    'lines': f"{current_line_start}-{current_line_start + len(current_chunk) - 1}",
                    'song': song_title
                })
            current_chunk = []
            current_line_start = i + 2
        else:
            current_chunk.append(line)
            
            # Force break if chunk gets too large
            if len(current_chunk) >= max_lines:
                chunk_text = '\n'.join(current_chunk)
                if chunk_text.strip():
                    chunks.append({
                        'text': chunk_text,
                        'lines': f"{current_line_start}-{current_line_start + len(current_chunk) - 1}",
                        'song': song_title
                    })
                current_chunk = []
                current_line_start = i + 2
    
    # Save any remaining chunk
    if current_chunk:
        chunk_text = '\n'.join(current_chunk)
        if chunk_text.strip():
            chunks.append({
                'text': chunk_text,
                'lines': f"{current_line_start}-{current_line_start + len(current_chunk) - 1}",
                'song': song_title
            })
    
    return chunks

def get_embedding(text: str, model: str = "text-embedding-3-large") -> List[float]:
    """Get embedding from OpenAI API"""
    try:
        response = openai_client.embeddings.create(
            model=model,
            input=text,
            encoding_format="float"
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Error getting embedding: {e}")
        return None

def batch_get_embeddings(texts: List[str], model: str = "text-embedding-3-large") -> List[List[float]]:
    """Get embeddings for multiple texts in batch"""
    try:
        response = openai_client.embeddings.create(
            model=model,
            input=texts,
            encoding_format="float"
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        logger.error(f"Error getting batch embeddings: {e}")
        return [None] * len(texts)

def vectorize_database():
    """Main function to vectorize all lyrics in the database"""
    
    # Connect to SQLite database
    conn = sqlite3.connect('drake_discography.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get or create collection
    try:
        collection = chroma_client.get_collection("drake_lyrics")
        print("Found existing collection, will update with new entries")
    except:
        collection = chroma_client.create_collection(
            name="drake_lyrics",
            metadata={"description": "Drake discography lyrics embeddings"}
        )
        print("Created new collection")
    
    # Get all songs with lyrics
    cursor.execute('''
        SELECT id, title, artist, lyrics, url, views
        FROM songs
        WHERE lyrics IS NOT NULL
        ORDER BY views DESC
    ''')
    songs = cursor.fetchall()
    
    print(f"Found {len(songs)} songs with lyrics to process")
    
    all_chunks = []
    all_metadata = []
    all_ids = []
    
    # Process each song
    for song in songs:
        # Create chunks for this song
        chunks = chunk_lyrics(
            song['lyrics'], 
            f"{song['title']} - {song['artist']}"
        )
        
        for i, chunk in enumerate(chunks):
            chunk_id = f"song_{song['id']}_chunk_{i}"
            
            # Prepare metadata
            metadata = {
                'song_id': song['id'],
                'title': song['title'],
                'artist': song['artist'],
                'chunk_index': i,
                'lines': chunk['lines'],
                'url': song['url'] or '',
                'views': song['views'],
                'full_name': f"{song['title']} - {song['artist']}"
            }
            
            all_chunks.append(chunk['text'])
            all_metadata.append(metadata)
            all_ids.append(chunk_id)
    
    print(f"Created {len(all_chunks)} total chunks")
    
    # Process in batches of 100
    batch_size = 100
    total_processed = 0
    
    for i in range(0, len(all_chunks), batch_size):
        batch_end = min(i + batch_size, len(all_chunks))
        batch_texts = all_chunks[i:batch_end]
        batch_metadata = all_metadata[i:batch_end]
        batch_ids = all_ids[i:batch_end]
        
        print(f"Processing batch {i//batch_size + 1} ({i+1}-{batch_end} of {len(all_chunks)})")
        
        # Get embeddings
        embeddings = batch_get_embeddings(batch_texts)
        
        # Filter out any failed embeddings
        valid_items = [
            (text, emb, meta, id_) 
            for text, emb, meta, id_ in zip(batch_texts, embeddings, batch_metadata, batch_ids)
            if emb is not None
        ]
        
        if valid_items:
            texts, embeddings, metadatas, ids = zip(*valid_items)
            
            # Add to ChromaDB
            collection.add(
                embeddings=list(embeddings),
                documents=list(texts),
                metadatas=list(metadatas),
                ids=list(ids)
            )
            
            total_processed += len(valid_items)
            print(f"  Added {len(valid_items)} chunks to vector database")
        
        # Rate limiting
        time.sleep(0.5)
    
    print(f"\n✅ Vectorization complete!")
    print(f"Total chunks processed: {total_processed}")
    print(f"Collection size: {collection.count()}")
    
    # Test query
    print("\n🧪 Testing with sample query...")
    test_query = "When Drake talks about his mother"
    test_embedding = get_embedding(test_query)
    
    if test_embedding:
        results = collection.query(
            query_embeddings=[test_embedding],
            n_results=3
        )
        
        print(f"Query: '{test_query}'")
        print("Top 3 results:")
        for i, (doc, meta) in enumerate(zip(results['documents'][0], results['metadatas'][0]), 1):
            print(f"\n{i}. {meta['full_name']} (lines {meta['lines']})")
            print(f"   Preview: {doc[:100]}...")
    
    conn.close()

if __name__ == '__main__':
    print("Drake Lyrics Vectorization")
    print("="*50)
    vectorize_database()