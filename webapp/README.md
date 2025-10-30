# Webapp - AI Briefing Report Viewer & Ask Function

This directory contains the **Streamlit web interface** for viewing AI briefing reports and asking questions about articles.

## Purpose

Provide an interactive web interface to:
1. Browse all generated briefing reports
2. Search reports by date, keywords, or topics
3. Ask questions about articles using the AI-powered ask function
4. Access full article content and paywallbuster links
5. View 5D scores and deep analysis for each article

## Running the Webapp

### Quick Start

```bash
cd webapp
./run_webapp.sh
```

This will start the Streamlit server at **http://localhost:8501**

### Manual Run

```bash
cd webapp
streamlit run app.py
```

### Options

```bash
streamlit run app.py --server.port 8502 --server.headless true
```

## Features

### 1. Report Browsing

- View all generated reports sorted by date
- Beautiful Markdown rendering with syntax highlighting
- Automatic article parser supporting 3 format versions:
  - FORMAT V1: `## N. Title` (legacy)
  - FORMAT V2: `### N. Title` (mid-2024)
  - FORMAT V3: `#### N. [Title](URL)` (current)

### 2. Search & Filter

- Search by keywords, dates, or topics
- Filter by business categories
- Sort by 5D scores (Market Impact, Competitive Impact, etc.)

### 3. Ask Function (AI-Powered Q&A)

The ask function provides intelligent answers to questions about briefing articles using a **5-stage context enrichment pipeline**:

#### Stage 1: Lexical Search (Current Briefing)
- Fast keyword matching on current report
- FREE, instant results

#### Stage 2: Lexical Search (Historical Articles)
- Searches 4 weeks of historical articles
- FREE, fast keyword matching

#### Stage 3: Semantic Search (Conditional)
- Only activated if <3 articles found
- Uses ChromaDB vector database
- Finds semantically similar articles

#### Stage 4: Entity Background Enrichment
- Provides company/technology context
- Enhances understanding of entities mentioned

#### Stage 5: Full Article + Paywallbuster
- Fetches complete article content
- Generates paywallbuster links for paywalled sources
- Example: `https://www.paywallbuster.com/?url=<article_url>`

#### LLM Provider Strategy

The ask function uses **Kimi (Moonshot AI)** as the primary provider:
- Fast response time (~1-2 seconds)
- Reliable availability
- Good Chinese language support
- Fallback to OpenRouter if needed

### 4. Article Cards

Each article displays:
- Title and source
- 5D weighted score
- Publication date
- 500-600 character deep analysis
- Link to original article
- Paywallbuster link (for paywalled sources)

## Architecture

### Components

- **app.py** - Main Streamlit application
- **components/article_qa_agent.py** - AI-powered Q&A system

### Dependencies

Imports from `../shared/`:
- `utils/` - LLM providers, context retriever, semantic search
- `config/` - providers.json for LLM configuration
- `data/reports/` - Generated briefing reports

## Configuration

### Provider Configuration

Edit `../config/providers.json` to:
- Configure LLM providers (Kimi, OpenRouter)
- Adjust fallback strategy
- Set model preferences

### Streamlit Configuration

Edit `.streamlit/config.toml` to:
- Change theme colors
- Adjust server settings
- Configure caching behavior

## Usage Examples

### Browse Latest Report

1. Start webapp: `./run_webapp.sh`
2. Select latest report from dropdown
3. Scroll through articles

### Ask Questions

1. Type question in ask box (e.g., "What are the latest developments in GPT-4?")
2. Wait 2-5 seconds for AI response
3. View answer with source citations

### Search Historical Articles

1. Use sidebar filters
2. Enter keywords or date range
3. Browse filtered results

## Troubleshooting

**Ask function returns "Error code: 401"?**
- Check `.env` file has valid `KIMI_API_KEY` or `OPENROUTER_API_KEY`
- Verify API key has quota remaining
- Check logs in `../logs/webapp.log`

**Ask function returns "Failed to complete task: LLM Query"?**
- Daily rate limit may be hit (50 requests/day for OpenRouter free tier)
- Switch to backup API key if configured
- Wait 24 hours for limit reset

**Reports not showing?**
- Check `../data/reports/` directory exists
- Verify reports have `.md` extension
- Ensure reports follow expected format

**Slow response times?**
- Semantic search can be slow for large databases
- Consider reducing search scope
- Check network connectivity

## Deployment

### Local Development

```bash
streamlit run app.py --logger.level=debug
```

### Production Deployment

Deploy on Streamlit Cloud (free tier available):

1. Push to GitHub
2. Connect Streamlit Cloud to repository
3. Configure secrets (API keys)
4. Deploy!

Alternatively, deploy on your own server:

```bash
# Install dependencies
pip install -r ../requirements.txt

# Run as background service
nohup streamlit run app.py --server.port 8501 --server.headless true &
```

## Monitoring

Check logs in: `../logs/webapp.log`

Monitor Streamlit metrics:
- Active users
- Query response times
- API usage

## Future Enhancements

- User authentication
- Report annotations and bookmarks
- Email notifications for new reports
- Multi-language support (English, Spanish, etc.)
- Export reports to PDF or Word
