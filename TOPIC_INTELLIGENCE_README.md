# Topic Intelligence Assistant - Quick Start Guide

## 🎯 Overview

The **Topic Intelligence Assistant** is an isolated research feature that generates USA/EN-focused topic recommendations for documentary content. It analyzes:

- 📊 **Wikipedia Pageviews** (demand signal)
- 🎥 **YouTube Competition** (saturation analysis)
- 📈 **Google Trends** (MVP: placeholder, future integration)

**Important:** This feature is **100% isolated** from the episode pipeline. Results are for manual review only and are NOT automatically added to your production workflow.

## 🚀 Quick Setup (3 Steps)

### Step 1: Enable Feature Flag

Add to `backend/.env`:

```bash
TOPIC_INTEL_ENABLED=true
```

### Step 2: Verify OpenAI API Key

Ensure `backend/.env` contains:

```bash
OPENAI_API_KEY=your_openai_api_key_here
```

(Used for topic expansion with GPT-4o)

### Step 3: Restart Backend

```bash
cd backend
python3 app.py
```

## 📝 Usage

### Via UI (Recommended)

1. Open frontend: `http://localhost:4000`
2. Scroll to the bottom of the page
3. Look for **"🔬 Topic Intelligence (US)"** panel
4. Configure:
   - **Number of Recommendations:** 5-50 (default: 20)
   - **Time Window:** 7d or 30d (default: 7d)
5. Click **"Start Research"**
6. Wait ~30-60 seconds (depending on count)
7. Review results and copy interesting topics to clipboard

### Via API (Advanced)

```bash
curl -X POST http://localhost:50000/api/topic-intel/research \
  -H "Content-Type: application/json" \
  -d '{
    "count": 20,
    "window_days": 7
  }'
```

**Response format:**

```json
{
  "success": true,
  "request_id": "ti_abc123",
  "generated_at": "2026-01-01T12:00:00Z",
  "locale": "US",
  "language": "en-US",
  "items": [
    {
      "topic": "The Last Hours of Anne Boleyn",
      "rating_letter": "A++",
      "score_total": 94,
      "why_now": "Tudor history trending on Netflix...",
      "suggested_angle": "Minute-by-minute thriller...",
      "signals": {
        "google_trends": {"status": "no_data", "score": 0, "note": "Not configured"},
        "wikipedia": {"status": "ok", "score": 87, "note": "Strong growth (+45.2%)..."},
        "youtube": {"status": "ok", "score": 78, "note": "Low competition..."}
      },
      "competition_flags": ["MODERATE_COMPETITION"],
      "sources": ["https://en.wikipedia.org/wiki/Anne_Boleyn"]
    }
  ],
  "stats": {...}
}
```

## 🧪 Testing

Run the automated test suite:

```bash
./test_topic_intelligence.sh
```

This will verify:
- ✅ Backend health
- ✅ Feature flag enforcement
- ✅ Input validation
- ✅ Full research request
- ✅ UI accessibility

## 🔧 Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TOPIC_INTEL_ENABLED` | `false` | Enable/disable feature |
| `TOPIC_INTEL_CACHE_TTL` | `10800` | Cache TTL in seconds (3 hours) |
| `WIKIPEDIA_API_BASE_URL` | `https://wikimedia.org/...` | Wikipedia API endpoint |
| `YOUTUBE_API_KEY` | (none) | Optional: enables YouTube signals |
| `OPENAI_API_KEY` | (none) | Required: for topic expansion |

### Optional: YouTube API Integration

For better competition analysis and seed topics:

1. Get API key: https://console.cloud.google.com/
2. Add to `backend/.env`:
   ```bash
   YOUTUBE_API_KEY=your_youtube_api_key_here
   ```
3. Restart backend

Without YouTube API:
- ✅ Feature still works
- ✅ Uses static seed list
- ⚠️ YouTube signals show "not configured"

## 📊 Understanding Ratings

### Rating Scale

- **A++** (90-100): Exceptional opportunity - high demand, low competition
- **A** (80-89): Strong opportunity - good momentum
- **B** (70-79): Decent opportunity - worth considering
- **C** (<70): Challenging - saturated or low interest

### Scoring Formula

```
Final Score = Demand (50%) + Competition (30%) + Retention Fit (20%)

Where:
- Demand = Wikipedia pageviews + growth
- Competition = Inverse YouTube saturation
- Retention Fit = Archetype keyword matching
```

## 🎭 Built-in Archetypes

The system optimizes for these documentary styles:

1. Final Days / Last Hours
2. Betrayal & Power
3. Forbidden / Hidden History
4. Disaster as Thriller
5. Trial / Execution / Scandal
6. Mystery / Vanished
7. War Turning Points
8. Empire Collapse
9. Genius vs. System
10. Plagues & Panic
11. Conspiracy (Evidence-based)
12. Survival Stories

Topics matching these archetypes receive bonus scoring.

## 🚨 Troubleshooting

### "Feature not enabled" error

**Solution:** Add `TOPIC_INTEL_ENABLED=true` to `backend/.env` and restart backend.

### "OpenAI API key not set" error

**Solution:** Add `OPENAI_API_KEY=your_key` to `backend/.env` and restart backend.

### "No recommendations found"

**Possible causes:**
- LLM failed to generate candidates → Check OpenAI API key/quotas
- All candidates filtered out → Try different time window
- Network issues → Check Wikipedia/YouTube API accessibility

**Solution:** Check backend logs for detailed error messages.

### Research takes too long (>2 minutes)

**Causes:**
- Large request count (40-50) with cold cache
- YouTube API rate limiting
- LLM processing time

**Solutions:**
- Start with smaller counts (10-20)
- Results are cached for 3 hours
- Subsequent requests are much faster

### Panel not visible in UI

**Check:**
1. Frontend running: `http://localhost:4000`
2. Scroll to bottom of page
3. Check browser console for errors
4. Clear browser cache and refresh

## 📁 File Structure

**Backend (new files):**
- `backend/topic_intel_providers.py` - Signal providers
- `backend/topic_intel_service.py` - Main service logic
- `backend/app.py` - Added endpoint: `/api/topic-intel/research`

**Frontend (new files):**
- `frontend/src/components/TopicIntelligencePanel.js` - UI component

**Configuration:**
- `backend/env_example.txt` - Updated with Topic Intel section
- `test_topic_intelligence.sh` - E2E test script

**Total:** ~1,200 lines of new code, fully isolated from pipeline.

## 🔒 Isolation Guarantees

This feature:
- ✅ Does NOT create/modify projects
- ✅ Does NOT trigger episode generation
- ✅ Does NOT access pipeline modules
- ✅ Uses separate service layer
- ✅ Results stored in-memory only (no database)
- ✅ Can be disabled via feature flag

## 📈 Performance Notes

### First Request (Cold Cache)
- Seeds: ~2-3 seconds
- LLM expansion: ~10-20 seconds
- Signal fetching: ~20-40 seconds (parallel)
- Scoring: ~1 second
- **Total: 30-60 seconds** for 20 topics

### Subsequent Requests (Warm Cache)
- **Total: 15-30 seconds** (Wikipedia/YouTube cached)

### Rate Limits
- Wikipedia: No limit (official API)
- YouTube: ~10,000 requests/day (free tier)
- OpenAI: Depends on your plan

## 🎯 Best Practices

1. **Start small:** Use count=10 for initial tests
2. **Review patterns:** Look for A++ and A ratings first
3. **Check signals:** Verify Wikipedia growth and YouTube competition
4. **Copy strategically:** Use "Copy to Clipboard" for top picks
5. **Time windows:** 
   - 7d = current trends (reactive)
   - 30d = stable patterns (strategic)

## 🔮 Future Enhancements

### MVP (Current)
- ✅ Wikipedia pageviews
- ✅ YouTube competition
- ⚠️ Google Trends (placeholder)
- ✅ Static + YouTube seed sources

### Roadmap
- [ ] Google Trends integration (pytrends or official API)
- [ ] Custom archetype editor (UI)
- [ ] Export to CSV/JSON
- [ ] Historical tracking (trend over time)
- [ ] Multi-language support (currently USA/EN only)

## 📞 Support

For issues or questions:
1. Check backend logs: `backend/backend_server.log`
2. Run test script: `./test_topic_intelligence.sh`
3. Review this guide's troubleshooting section

---

**Last Updated:** January 2026  
**Feature Status:** ✅ Production Ready (MVP)  
**Isolation Level:** 🔒 100% (No pipeline integration)



