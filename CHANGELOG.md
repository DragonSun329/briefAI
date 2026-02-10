# CHANGELOG

All notable changes to the briefAI project, consolidated from legacy status docs.

---

## October 27, 2025

### Phase 3: Streamlit Cloud Deployment — COMPLETE
Created `app.py` (380-line Streamlit web app), added GitHub auto-push to `main.py`, configured Streamlit Cloud deployment with secrets management. Web interface provides CEO briefing view with search (Entity, Topic, Keyword) and article cards.

### Phase A: Chatbox Enhancement — COMPLETE
Enhanced chatbox and search with deep article analysis. Improved system prompts to extract central arguments and supporting evidence, added cross-article synthesis, and increased response depth ~30-40%.

### LLM Provider Fix
Fixed `ProviderSwitcher` missing `query()` method causing chatbox errors. Replaced hardcoded Anthropic client with `ProviderSwitcher` (Kimi/Moonshot), properly handling rate limits with automatic fallback to OpenRouter.

### UI Redesign
Complete Streamlit UI overhaul — unified sidebar search/chat, moved search results from hidden Tab 2 to main area, simplified layout.

### Article Parsing & Display Fixes
Fixed article parser missing source/URL data due to regex issues. Rewrote parsing logic with better pattern matching for metadata extraction (来源, URL fields).

### Chatbox Provider Integration Fix
Fixed `'KimiProvider' object has no attribute 'query'` — `ProviderSwitcher.query()` was calling `provider.query()` instead of `provider.chat()`. Properly handled return tuple `(response, usage)`.

### Search & Chatbox Architecture Analysis
Identified limitations: search restricted to current week's briefing only, chatbox receives only markdown summary (missing full article data, scores, entities). `context_retriever` module exists but unused in UI.

### LLM Error Diagnosis
Investigated persistent chatbox errors. Code in GitHub was correct (`provider.chat()`) but Streamlit Cloud was caching old deployment. Solution: force reboot on Streamlit Cloud.

### Streamlit Deployment Guide
Created full deployment guide: GitHub repo setup → Streamlit Cloud connection → secrets configuration → verification steps.

### Streamlit Fixes
Fixed three critical issues: chatbox API failure (Anthropic → ProviderSwitcher), search results hidden (moved to main area), PDF Unicode crash (removed PDF export).

### Deployment Verification
Checklist for Streamlit Cloud deployment: update secrets (remove `ANTHROPIC_API_KEY`, add Kimi/OpenRouter keys), reboot app, verify chatbox and search.

### Repository Cleanup
Deleted 36 legacy markdown files, 6 test/temp scripts, and 3 misc files. Organized documentation.
