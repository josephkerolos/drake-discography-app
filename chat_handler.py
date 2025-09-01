#!/usr/bin/env python3

from openai import OpenAI, DefaultHttpxClient
import httpx
import chromadb
from chromadb.config import Settings
import os
from typing import List, Dict, Optional, Tuple
import json
import tiktoken
import logging
from dotenv import load_dotenv
import time
import random
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

# Disable ChromaDB telemetry completely
os.environ['ANONYMIZED_TELEMETRY'] = 'false'
os.environ['CHROMA_TELEMETRY'] = 'false'

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
        
        # Simple embedding cache (query -> (embedding, timestamp))
        self._embedding_cache = {}
        self._cache_ttl = timedelta(minutes=5)
        
        self.client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=False,
                is_persistent=True
            )
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

CRITICAL INSTRUCTIONS:
1. ACCURACY IS PARAMOUNT - Only cite lyrics that are EXACTLY in the provided context
2. Always cite specific songs with exact titles when referencing lyrics
3. Use direct quotes from the provided lyrics, marking them with quotation marks
4. If the provided context doesn't contain relevant information, clearly state: "I don't have lyrics about that topic in the provided context"
5. Focus on themes and patterns across multiple songs when available
6. Be specific about which lines or verses you're referring to
7. Never make up or paraphrase lyrics - use only what's provided
8. When analyzing themes, reference multiple songs if applicable

Format your citations as: [Song Title - Artist] at the end of relevant sentences.
Always indicate line numbers when available (e.g., "Lines 5-7").

Remember: You can ONLY discuss lyrics that are in the provided context. Do not use general knowledge about Drake's music."""

    def _get_openai_client(self):
        """Get or initialize the OpenAI client with Railway-optimized settings"""
        # Always check for the current API key
        current_api_key = os.getenv('OPENAI_API_KEY')
        
        # Fix: Always retry if client is None or key changed
        if not self._openai_client or not self._openai_initialized or \
           (self._openai_client and hasattr(self._openai_client, 'api_key') and \
            self._openai_client.api_key != current_api_key):
            
            if not current_api_key:
                logger.error("OPENAI_API_KEY not found in environment variables")
                logger.error(f"Available env vars: {list(os.environ.keys())}")
                self._openai_client = None
                self._openai_initialized = True
                return None
            
            # Try to initialize with retries for Railway connectivity issues
            max_retries = 3
            retry_delay = 1
            
            for attempt in range(max_retries):
                try:
                    # Create custom HTTP client with Railway-optimized settings
                    http_client = DefaultHttpxClient(
                        timeout=httpx.Timeout(
                            timeout=60.0,  # Total timeout
                            connect=15.0,  # Connection timeout (longer for Railway)
                            read=30.0,     # Read timeout
                            write=10.0,    # Write timeout
                            pool=5.0       # Pool timeout
                        ),
                        limits=httpx.Limits(
                            max_connections=10,
                            max_keepalive_connections=5,
                            keepalive_expiry=30
                        ),
                        # Add headers to identify Railway traffic
                        headers={
                            'User-Agent': 'Drake-Discography-Railway/1.0',
                            'X-Platform': 'Railway'
                        },
                        verify=True
                    )
                    
                    self._openai_client = OpenAI(
                        api_key=current_api_key,
                        http_client=http_client,
                        max_retries=2  # OpenAI's built-in retry
                    )
                    
                    # Test the connection
                    test_response = self._openai_client.models.list()
                    logger.info(f"OpenAI client initialized successfully on attempt {attempt + 1}")
                    logger.info(f"Using API key: {current_api_key[:10]}...")
                    self._openai_initialized = True
                    return self._openai_client
                    
                except httpx.TimeoutException as e:
                    logger.warning(f"Timeout connecting to OpenAI (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        logger.error("Failed to connect to OpenAI after all retries (timeout)")
                        self._openai_client = None
                        
                except httpx.ConnectError as e:
                    logger.warning(f"Connection error to OpenAI (attempt {attempt + 1}/{max_retries}): {e}")
                    logger.info("This may be due to Railway's shared IPs being rate-limited by OpenAI")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        logger.error("Failed to connect to OpenAI after all retries (connection error)")
                        self._openai_client = None
                        
                except Exception as e:
                    logger.error(f"Unexpected error initializing OpenAI client (attempt {attempt + 1}/{max_retries}): {e}")
                    logger.error(f"Error type: {type(e).__name__}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        self._openai_client = None
            
            self._openai_initialized = True
        
        return self._openai_client
    
    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for a text using OpenAI with retry logic and caching"""
        # Check cache first
        now = datetime.now()
        if text in self._embedding_cache:
            embedding, timestamp = self._embedding_cache[text]
            if now - timestamp < self._cache_ttl:
                logger.debug(f"Using cached embedding for query: {text[:50]}...")
                return embedding
            else:
                # Remove expired cache entry
                del self._embedding_cache[text]
        
        client = self._get_openai_client()
        if not client:
            logger.error("OpenAI client not available after retries")
            return None
        
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                response = client.embeddings.create(
                    model="text-embedding-3-large",
                    input=text,
                    encoding_format="float"
                )
                embedding = response.data[0].embedding
                
                # Cache the embedding
                self._embedding_cache[text] = (embedding, now)
                
                # Clean old cache entries if cache gets too large
                if len(self._embedding_cache) > 100:
                    # Remove oldest entries
                    sorted_cache = sorted(self._embedding_cache.items(), key=lambda x: x[1][1])
                    for key, _ in sorted_cache[:20]:  # Remove 20 oldest
                        del self._embedding_cache[key]
                
                return embedding
                
            except httpx.TimeoutException as e:
                logger.warning(f"Embedding timeout (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay + random.uniform(0, 0.5))  # Add jitter
                    retry_delay *= 2
                else:
                    logger.error("Failed to get embedding after all retries")
                    return None
                    
            except Exception as e:
                logger.error(f"Error getting embedding (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay + random.uniform(0, 0.5))
                    retry_delay *= 2
                else:
                    return None

    def search_lyrics(self, query: str, n_results: int = 20) -> Dict:
        """Search for relevant lyrics chunks using semantic similarity"""
        query_embedding = self.get_embedding(query)
        
        if not query_embedding:
            error_msg = "Failed to get embeddings from OpenAI. This may be due to Railway connectivity issues with OpenAI's servers."
            logger.error(error_msg)
            logger.info("Tip: Railway's shared IPs may be rate-limited by OpenAI. Try again in a few moments.")
            return {"error": error_msg}
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )
        
        # Format results (removed broken distance filter)
        formatted_results = []
        seen_songs = set()
        all_distances = []
        
        for doc, metadata, distance in zip(
            results['documents'][0], 
            results['metadatas'][0],
            results['distances'][0]
        ):
            all_distances.append(distance)
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
        
        # Sort by relevance (lower distance = more relevant)
        formatted_results.sort(key=lambda x: x['distance'])
        
        # Log distance information for debugging
        if all_distances:
            logger.info(f"Query distances - Min: {min(all_distances):.2f}, Max: {max(all_distances):.2f}, Avg: {sum(all_distances)/len(all_distances):.2f}")
        
        logger.info(f"Found {len(formatted_results)} results for query: {query[:50]}...")
        if formatted_results:
            logger.info(f"Best match: {formatted_results[0]['song']} (distance: {formatted_results[0]['distance']:.2f})")
            # Log top 3 matches for debugging
            for i, result in enumerate(formatted_results[:3]):
                logger.debug(f"Match {i+1}: {result['song']} - Lines {result['lines']} (distance: {result['distance']:.2f})")
        
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
        
        context_str = "\n\n---\n\n".join(context_parts[:12])  # Increased to top 12 unique songs for better context
        
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
        
        client = self._get_openai_client()
        if not client:
            logger.error("OpenAI client not initialized after retries")
            return "Error: Unable to connect to OpenAI. Railway may have connectivity issues with OpenAI's servers. Please try again in a few moments."
        
        # Try with retries for Railway connectivity issues
        max_retries = 3
        retry_delay = 1
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Try GPT-5 model as requested
                try:
                    response = client.chat.completions.create(
                        model="gpt-5-2025-08-07",  # GPT-5 as requested
                        messages=messages,
                        # temperature=1 is default for GPT-5, removed explicit setting
                        max_completion_tokens=1500,  # GPT-5 uses max_completion_tokens
                        stream=False
                    )
                    logger.info("Using model: gpt-5-2025-08-07")
                    return response.choices[0].message.content
                    
                except Exception as e1:
                    if attempt == 0:  # Only try fallback models on first attempt
                        logger.warning(f"Failed with gpt-5-2025-08-07: {e1}")
                        # Fallback to GPT-4o if GPT-5 not available
                        try:
                            response = client.chat.completions.create(
                                model="gpt-4o",
                                messages=messages,
                                temperature=0.7,
                                max_tokens=1500,
                                stream=False
                            )
                            logger.info("Using fallback model: gpt-4o")
                            return response.choices[0].message.content
                            
                        except Exception as e2:
                            logger.warning(f"Failed with gpt-4o: {e2}")
                            # Final fallback
                            response = client.chat.completions.create(
                                model="gpt-3.5-turbo",
                                messages=messages,
                                temperature=0.7,
                                max_tokens=1500,
                                stream=False
                            )
                            logger.info("Using fallback model: gpt-3.5-turbo")
                            return response.choices[0].message.content
                    else:
                        raise  # Re-raise to trigger retry logic
                        
            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(f"Chat completion timeout (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay + random.uniform(0, 0.5))
                    retry_delay *= 2
                    
            except httpx.ConnectError as e:
                last_error = e
                logger.warning(f"Connection error during chat (attempt {attempt + 1}/{max_retries}): {e}")
                logger.info("Railway's shared IPs may be experiencing rate limiting from OpenAI")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay + random.uniform(0, 0.5))
                    retry_delay *= 2
                    
            except Exception as e:
                last_error = e
                logger.error(f"Unexpected error during chat (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay + random.uniform(0, 0.5))
                    retry_delay *= 2
        
        # All retries failed
        logger.error(f"Failed to generate response after {max_retries} attempts")
        if isinstance(last_error, httpx.TimeoutException):
            return "Error: Request timed out. Railway is having trouble connecting to OpenAI. Please try again."
        elif isinstance(last_error, httpx.ConnectError):
            return "Error: Cannot connect to OpenAI. Railway's servers may be temporarily blocked. Please try again in a few moments."
        else:
            return f"Error: Unable to generate response. {str(last_error) if last_error else 'Unknown error'}"

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
    # Only create new handler if it doesn't exist or if OpenAI client failed
    # This prevents constant ChromaDB reinitialization while still allowing retry
    if chat_handler is None or (hasattr(chat_handler, '_openai_client') and chat_handler._openai_client is None):
        logger.info("Creating new chat handler instance")
        chat_handler = LyricsChatHandler()
    return chat_handler