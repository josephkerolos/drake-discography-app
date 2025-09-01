# Railway Deployment Instructions for Drake AI Chat

## Prerequisites
You need to set the OpenAI API key in Railway environment variables.

## Step 1: Deploy to Railway
1. Visit: https://railway.app/new/github/josephkerolos/drake-discography-app
2. Click "Deploy Now"
3. Wait for initial deployment (will fail - that's normal)

## Step 2: Set Environment Variables
1. In Railway dashboard, go to your project
2. Click on the service
3. Go to "Variables" tab
4. Add these environment variables:

```
OPENAI_API_KEY=your_openai_api_key_here
SECRET_KEY=generate_a_random_secret_key_here
PORT=5000
```

**Important**: Use your OpenAI API key from https://platform.openai.com/api-keys

## Step 3: Redeploy
1. After setting environment variables, click "Redeploy"
2. Wait 2-3 minutes for deployment

## Step 4: Generate Domain
1. Go to "Settings" tab
2. Under "Domains", click "Generate Domain"
3. Your app will be live!

## Step 5: Initialize Vector Database
Once deployed, the vectorization will need to run once:
1. The app will work immediately with basic lyrics
2. For full AI chat functionality, vectorization runs automatically on first use

## Features Available
- **Browse Database**: View all 986 Drake songs
- **Search & Filter**: Find specific songs and artists
- **View Lyrics**: Click any song to see full lyrics
- **AI Chat**: Ask questions about Drake's lyrics with GPT-4o
- **Semantic Search**: Find lyrics by meaning, not just keywords

## Troubleshooting
- If chat doesn't work: Check OPENAI_API_KEY is set correctly
- If deployment fails: Check logs in Railway dashboard
- Database is included, no setup needed

## Important Notes
- First chat query may take 10-15 seconds to initialize
- Subsequent queries will be much faster (<2 seconds)
- The app includes 75%+ of all Drake lyrics pre-fetched