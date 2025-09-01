#!/usr/bin/env python3

import openai
import chromadb
from chromadb.config import Settings
import os
from typing import List, Dict, Optional
import json
import tiktoken

# OpenAI Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable must be set")
openai.api_key = OPENAI_API_KEY

# ChromaDB setup
CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(__file__), 'chroma_db')

class LyricsChatHandler:
    def __init__(self):
        """Initialize the chat handler with ChromaDB and OpenAI"""
        self.client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_collection("drake_lyrics")
        self.encoder = tiktoken.encoding_for_model("gpt-4o")
        
        # System prompt for the AI
        self.system_prompt = """You are an expert on Drake's discography with access to a comprehensive database of his lyrics. 
Your role is to answer questions about Drake's music, themes, lyrics, and artistic evolution based ONLY on the lyrics provided to you.

Key instructions:
1. Always cite specific songs when referencing lyrics
2. Use exact quotes when possible, but be careful not to reproduce entire songs
3. Focus on analysis, themes, and insights rather than just repeating lyrics
4. If asked about something not in the provided context, say you don't have that information
5. Be concise but thorough in your analysis
6. When multiple songs address the same theme, compare and contrast them

Format your citations as: [Song Title - Artist] at the end of relevant sentences."""

    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for a text using OpenAI"""
        try:
            response = openai.embeddings.create(
                model="text-embedding-3-large",
                input=text,
                encoding_format="float"
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Error getting embedding: {e}")
            return None

    def search_lyrics(self, query: str, n_results: int = 10) -> Dict:
        """Search for relevant lyrics chunks using semantic similarity"""
        query_embedding = self.get_embedding(query)
        
        if not query_embedding:
            return {"error": "Failed to process query"}
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )
        
        # Format results
        formatted_results = []
        seen_songs = set()
        
        for doc, metadata, distance in zip(
            results['documents'][0], 
            results['metadatas'][0],
            results['distances'][0]
        ):
            song_key = f"{metadata['title']}-{metadata['artist']}"
            
            formatted_results.append({
                'text': doc,
                'song': metadata['full_name'],
                'title': metadata['title'],
                'artist': metadata['artist'],
                'lines': metadata['lines'],
                'url': metadata['url'],
                'distance': distance,
                'is_duplicate': song_key in seen_songs
            })
            seen_songs.add(song_key)
        
        return formatted_results

    def generate_response(self, query: str, context: List[Dict], 
                         conversation_history: Optional[List[Dict]] = None) -> str:
        """Generate a response using GPT-4o with the retrieved context"""
        
        # Build context string
        context_parts = []
        for i, result in enumerate(context):
            if not result['is_duplicate']:  # Avoid duplicate songs in context
                context_parts.append(
                    f"[{result['song']} - Lines {result['lines']}]:\n{result['text']}"
                )
        
        context_str = "\n\n---\n\n".join(context_parts[:8])  # Limit to top 8 unique songs
        
        # Count tokens to ensure we stay within limits
        context_tokens = len(self.encoder.encode(context_str))
        if context_tokens > 3000:
            # Truncate context if too long
            context_parts = context_parts[:5]
            context_str = "\n\n---\n\n".join(context_parts)
        
        # Build messages
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Context lyrics:\n\n{context_str}\n\n---\n\nUser question: {query}"}
        ]
        
        # Add conversation history if provided
        if conversation_history:
            for msg in conversation_history[-4:]:  # Keep last 4 exchanges
                messages.append(msg)
        
        try:
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
                stream=False
            )
            
            return response.choices[0].message.content
        except Exception as e:
            return f"Error generating response: {str(e)}"

    def chat(self, query: str, conversation_history: Optional[List[Dict]] = None) -> Dict:
        """Main chat function that orchestrates search and response generation"""
        
        # Search for relevant lyrics
        search_results = self.search_lyrics(query, n_results=15)
        
        if isinstance(search_results, dict) and 'error' in search_results:
            return search_results
        
        # Generate response
        response = self.generate_response(query, search_results, conversation_history)
        
        # Extract citations from search results
        citations = []
        seen_songs = set()
        for result in search_results[:10]:
            song_key = f"{result['title']}-{result['artist']}"
            if song_key not in seen_songs:
                citations.append({
                    'title': result['title'],
                    'artist': result['artist'],
                    'url': result['url'],
                    'lines': result['lines']
                })
                seen_songs.add(song_key)
        
        return {
            'response': response,
            'citations': citations[:5],  # Return top 5 unique citations
            'query': query
        }

    def get_suggestions(self) -> List[str]:
        """Return suggested queries for users"""
        return [
            "When does Drake mention his mother Sandra?",
            "How does Drake talk about Toronto in his music?",
            "What are Drake's thoughts on fame and success?",
            "Find references to relationships and trust issues",
            "How has Drake's style evolved from 2010 to now?",
            "What does Drake say about his competition?",
            "When does Drake reference his Jewish heritage?",
            "What are the recurring themes in Drake's music?",
            "How does Drake describe his rise to fame?",
            "Find all mentions of specific cities and places"
        ]

# Singleton instance
chat_handler = None

def get_chat_handler():
    """Get or create the chat handler instance"""
    global chat_handler
    if chat_handler is None:
        chat_handler = LyricsChatHandler()
    return chat_handler