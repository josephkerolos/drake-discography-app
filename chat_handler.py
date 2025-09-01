#!/usr/bin/env python3

from openai import OpenAI
import chromadb
from chromadb.config import Settings
import os
from typing import List, Dict, Optional
import json
import tiktoken
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ChromaDB setup
CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(__file__), 'chroma_db')

class LyricsChatHandler:
    def __init__(self):
        """Initialize the chat handler with ChromaDB and OpenAI"""
        # Lazy initialization for OpenAI client
        self._openai_client = None
        self._openai_initialized = False
        
        self.client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Try to get or create collection
        try:
            self.collection = self.client.get_collection("drake_lyrics")
        except:
            # Create collection if it doesn't exist
            self.collection = self.client.create_collection(
                name="drake_lyrics",
                metadata={"description": "Drake discography lyrics embeddings"}
            )
        
        # Initialize encoder with fallback
        try:
            self.encoder = tiktoken.encoding_for_model("gpt-4o")
        except:
            self.encoder = tiktoken.get_encoding("cl100k_base")
        
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

    def _get_openai_client(self):
        """Get or initialize the OpenAI client lazily"""
        if not self._openai_initialized:
            self._openai_initialized = True
            api_key = os.getenv('OPENAI_API_KEY')
            
            if not api_key:
                logger.error("OPENAI_API_KEY not found in environment variables")
                logger.error(f"Available env vars: {list(os.environ.keys())}")
                self._openai_client = None
            else:
                try:
                    self._openai_client = OpenAI(api_key=api_key)
                    logger.info(f"OpenAI client initialized with key starting with: {api_key[:7]}...")
                except Exception as e:
                    logger.error(f"Failed to create OpenAI client: {e}")
                    self._openai_client = None
        
        return self._openai_client
    
    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for a text using OpenAI"""
        client = self._get_openai_client()
        if not client:
            logger.error("OpenAI client not available. Check your API key.")
            return None
            
        try:
            response = client.embeddings.create(
                model="text-embedding-3-large",
                input=text,
                encoding_format="float"
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error getting embedding: {e}")
            return None

    def search_lyrics(self, query: str, n_results: int = 10) -> Dict:
        """Search for relevant lyrics chunks using semantic similarity"""
        query_embedding = self.get_embedding(query)
        
        if not query_embedding:
            error_msg = "Failed to process query. Please check if the OpenAI API key is configured correctly."
            logger.error(error_msg)
            return {"error": error_msg}
        
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
        """Generate a response using latest GPT model with the retrieved context"""
        
        # Build context string
        context_parts = []
        for i, result in enumerate(context):
            if not result['is_duplicate']:  # Avoid duplicate songs in context
                context_parts.append(
                    f"[{result['song']} - Lines {result['lines']}]:\n{result['text']}"
                )
        
        context_str = "\n\n---\n\n".join(context_parts[:8])  # Limit to top 8 unique songs
        
        # Count tokens to ensure we stay within limits
        try:
            context_tokens = len(self.encoder.encode(context_str))
            if context_tokens > 3000:
                # Truncate context if too long
                context_parts = context_parts[:5]
                context_str = "\n\n---\n\n".join(context_parts)
        except:
            # If encoder fails, use character count estimate
            if len(context_str) > 12000:
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
            client = self._get_openai_client()
            if not client:
                logger.error("OpenAI client not initialized")
                return "Error: OpenAI API is not configured properly. Please check your API key."
                
            # Try latest model first
            try:
                response = client.chat.completions.create(
                    model="gpt-4-turbo-2024-04-09",  # Latest available GPT-4 model
                    messages=messages,
                    temperature=0.7,
                    max_tokens=1000,
                    stream=False
                )
            except Exception as e1:
                logger.warning(f"Failed with gpt-4-turbo: {e1}")
                # Fallback to GPT-4o if newer model not available
                try:
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=messages,
                        temperature=0.7,
                        max_tokens=1000,
                        stream=False
                    )
                except Exception as e2:
                    logger.warning(f"Failed with gpt-4o: {e2}")
                    # Final fallback to GPT-3.5
                    response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=messages,
                        temperature=0.7,
                        max_tokens=1000,
                        stream=False
                    )
            
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return f"Error generating response: {str(e)}. Please ensure your OpenAI API key is valid."

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