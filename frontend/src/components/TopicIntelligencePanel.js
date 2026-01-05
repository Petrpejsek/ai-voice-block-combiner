import React, { useState, useEffect } from 'react';
import axios from 'axios';

/**
 * TopicCard - Individual topic recommendation card with collapsible details
 */
const TopicCard = ({ item, getRatingColor, getSignalStatusIcon, copyToClipboard }) => {
  const [showDetails, setShowDetails] = useState(true);
  
  return (
    <div className="border border-gray-200 rounded-lg p-5 hover:shadow-md transition-shadow bg-white">
      {/* Header: Topic + Rating + Score */}
      <div className="flex items-start justify-between mb-3">
        <h4 className="text-lg font-bold text-gray-900 flex-1 pr-4">
          {item.topic}
        </h4>
        <div className="flex items-center gap-2 shrink-0">
          <span className={`px-3 py-1 rounded-full text-sm font-bold ${getRatingColor(item.rating_letter)}`}>
            {item.rating_letter}
          </span>
          <span className="text-lg font-bold text-gray-700">
            {item.score_total}/100
          </span>
        </div>
      </div>

      {/* Recommendation Summary (Most Important) - CZECH */}
      <div className="mb-4 p-3 bg-gradient-to-r from-emerald-50 to-teal-50 rounded-md border-l-4 border-emerald-500">
        <p className="text-sm font-medium text-emerald-900">
          {item.recommendation_summary_cs || item.recommendation_summary || 'Doporučeno na základě analýzy signálů a profilu kanálu.'}
        </p>
      </div>

      {/* Opportunity & Risk Columns - CZECH */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        {/* Opportunity */}
        <div className="p-3 bg-green-50 rounded-md">
          <h5 className="text-sm font-bold text-green-800 mb-2 flex items-center gap-1">
            ✅ Výhody
          </h5>
          <ul className="space-y-1">
            {(item.opportunity_bullets_cs || item.opportunity_bullets || ['Sedí do profilu kanálu']).map((bullet, idx) => (
              <li key={idx} className="text-sm text-green-700 flex items-start gap-2">
                <span className="text-green-500 mt-0.5">•</span>
                <span>{bullet}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Risks */}
        <div className="p-3 bg-amber-50 rounded-md">
          <h5 className="text-sm font-bold text-amber-800 mb-2 flex items-center gap-1">
            ⚠️ Rizika
          </h5>
          <ul className="space-y-1">
            {(item.risk_bullets_cs || item.risk_bullets || ['Žádná výrazná rizika']).map((bullet, idx) => (
              <li key={idx} className="text-sm text-amber-700 flex items-start gap-2">
                <span className="text-amber-500 mt-0.5">•</span>
                <span>{bullet}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Farm Brief (EN) - Blue Box (Modern Design) */}
      {item.farm_brief_en && (
        <div className="mb-4 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg border border-blue-200 shadow-sm">
          <div className="flex items-center gap-2 mb-2">
            <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <h5 className="text-xs font-bold text-blue-800 uppercase tracking-wider">
              Farm Brief (EN) — Copy This
            </h5>
          </div>
          <p className="text-sm text-blue-900 leading-relaxed font-medium">
            {item.farm_brief_en}
          </p>
        </div>
      )}

      {/* Hook / Angle */}
      <div className="mb-4 p-3 bg-purple-50 rounded-md">
        <p className="text-sm text-purple-900">
          <span className="font-bold">💡 Hook / Angle:</span> {item.hook_angle || item.suggested_angle || 'N/A'}
        </p>
        {item.why_now && (
          <p className="text-xs text-purple-700 mt-1 opacity-80">
            {item.why_now}
          </p>
        )}
      </div>

      {/* Signal Details (Collapsible) */}
      <div className="mb-3">
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-800 transition-colors"
        >
          <span className="transform transition-transform" style={{ transform: showDetails ? 'rotate(90deg)' : 'rotate(0deg)' }}>
            ▶
          </span>
          <span className="font-medium">Signal Details</span>
          <span className="text-xs text-gray-400">
            (Wiki: {item.signals.wikipedia.score} | YT: {item.signals.youtube.score})
          </span>
        </button>
        
        {showDetails && (
          <div className="mt-3 space-y-3 pl-5 border-l-2 border-gray-200">
            {/* Wikipedia Signal */}
            <div className="text-sm">
              <div className="flex items-center gap-2 mb-1">
                <span>{getSignalStatusIcon(item.signals.wikipedia.status)}</span>
                <span className="font-semibold text-gray-800">Wikipedia</span>
                {item.signals.wikipedia.verdict_cs && (
                  <span className="ml-2 text-xs font-bold">{item.signals.wikipedia.verdict_cs}</span>
                )}
              </div>
              <div className="ml-6 space-y-1 text-gray-600">
                <div className="flex gap-3">
                  <span className="text-gray-500">{item.signals.wikipedia.label || 'N/A'}</span>
                  {item.signals.wikipedia.trend_label && (
                    <span className={`${item.signals.wikipedia.delta_pct > 0 ? 'text-green-600' : item.signals.wikipedia.delta_pct < 0 ? 'text-red-600' : 'text-gray-500'}`}>
                      {item.signals.wikipedia.trend_label}
                    </span>
                  )}
                </div>
                <p className="text-xs italic text-gray-700">
                  {item.signals.wikipedia.interpretation_cs || item.signals.wikipedia.interpretation || item.signals.wikipedia.note}
                </p>
              </div>
            </div>

            {/* YouTube Signal */}
            <div className="text-sm">
              <div className="flex items-center gap-2 mb-1">
                <span>{getSignalStatusIcon(item.signals.youtube.status)}</span>
                <span className="font-semibold text-gray-800">YouTube Competition</span>
                {item.signals.youtube.verdict_cs && (
                  <span className="ml-2 text-xs font-bold">{item.signals.youtube.verdict_cs}</span>
                )}
              </div>
              <div className="ml-6 space-y-1 text-gray-600">
                <div className="flex gap-3">
                  <span className="text-gray-500">{item.signals.youtube.label || 'N/A'}</span>
                  {item.signals.youtube.trend_label && (
                    <span className="text-gray-400 text-xs">{item.signals.youtube.trend_label}</span>
                  )}
                </div>
                <p className="text-xs italic text-gray-700">
                  {item.signals.youtube.interpretation_cs || item.signals.youtube.interpretation || item.signals.youtube.note}
                </p>
                {item.signals.youtube.dominated_by_large_channels && (
                  <span className="inline-block mt-1 px-2 py-0.5 bg-red-100 text-red-700 text-xs rounded">
                    ⚠️ Large channels dominate
                  </span>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Competition Flags (if any) */}
      {item.competition_flags && item.competition_flags.length > 0 && (
        <div className="mb-3">
          <div className="flex flex-wrap gap-2">
            {item.competition_flags.map((flag, idx) => (
              <span
                key={idx}
                className="px-2 py-1 bg-orange-100 text-orange-800 text-xs rounded"
              >
                {flag.replace(/_/g, ' ')}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Copy Button */}
      <div className="flex justify-end pt-2 border-t border-gray-100">
        <button
          onClick={() => copyToClipboard(item)}
          className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm font-medium rounded-md transition-colors flex items-center gap-2"
        >
          📋 Copy to Clipboard
        </button>
      </div>
    </div>
  );
};

/**
 * Topic Intelligence Panel (USA/EN)
 * 
 * Isolated research feature - generates topic recommendations based on:
 * - Wikipedia pageviews (demand signal)
 * - YouTube competition analysis
 * - Google Trends (placeholder for MVP)
 * 
 * NO pipeline integration - results are manual copy only.
 */
const TopicIntelligencePanel = () => {
  // UI State
  const [count, setCount] = useState(20);
  const [windowDays, setWindowDays] = useState(7);
  const [isResearching, setIsResearching] = useState(false);
  const [progressText, setProgressText] = useState('');
  const [results, setResults] = useState(null);
  const [otherIdeas, setOtherIdeas] = useState(null);
  const [error, setError] = useState('');
  const [stats, setStats] = useState(null);
  const [recommendationMode, setRecommendationMode] = useState('momentum');
  
  // Channel Profile State
  const [selectedProfile, setSelectedProfile] = useState('us_history_docs');
  const [profiles, setProfiles] = useState([]);
  const [showProfilesModal, setShowProfilesModal] = useState(false);
  const [isLoadingProfiles, setIsLoadingProfiles] = useState(false);
  
  // LLM Configuration State
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [llmConfig, setLlmConfig] = useState({
    provider: 'openrouter',
    model: 'openai/gpt-4o',
    temperature: 0.7,
    custom_prompt: ''
  });

  // Load profiles on mount
  useEffect(() => {
    loadProfiles();
  }, []);

  const loadProfiles = async () => {
    setIsLoadingProfiles(true);
    try {
      const response = await axios.get('/api/topic-intel/profiles', { timeout: 10000 });
      if (response.data.success) {
        setProfiles(response.data.profiles || []);
      }
    } catch (err) {
      console.error('Failed to load profiles:', err);
      // Set default profiles if backend fails
      setProfiles([
        { id: 'us_history_docs', name: 'US History Docs' },
        { id: 'us_true_crime', name: 'US True Crime' }
      ]);
    } finally {
      setIsLoadingProfiles(false);
    }
  };

  // Start research
  const handleStartResearch = async () => {
    if (isResearching) return;

    setIsResearching(true);
    setError('');
    setResults(null);
    setOtherIdeas(null);
    setStats(null);
    setProgressText('Initializing research...');

    try {
      setProgressText('Collecting seed topics...');
      
      const response = await axios.post('/api/topic-intel/research', {
        count: parseInt(count),
        window_days: parseInt(windowDays),
        profile_id: selectedProfile,
        recommendation_mode: recommendationMode,
        llm_config: {
          provider: llmConfig.provider,
          model: llmConfig.model,
          temperature: llmConfig.temperature,
          custom_prompt: llmConfig.custom_prompt || null
        }
      }, {
        timeout: 300000  // 5 minutes timeout (LLM + API calls can be slow)
      });

      if (response.data.success) {
        setResults(response.data.items || []);
        setOtherIdeas(response.data.other_ideas || []);
        setStats(response.data.stats || null);
        setProgressText('');
        setError('');
      } else {
        setError(response.data.error || 'Research failed');
        setProgressText('');
      }

    } catch (err) {
      console.error('Topic Intelligence error:', err);
      const errorMsg = err.response?.data?.error || err.message || 'Research failed';
      setError(errorMsg);
      setProgressText('');
    } finally {
      setIsResearching(false);
    }
  };

  // Copy card to clipboard
  const copyToClipboard = (item) => {
    // Copy ONLY farm_brief_en
    const text = item.farm_brief_en || `Topic: ${item.topic}\n\n(No farm brief available - please regenerate with updated prompt)`;

    navigator.clipboard.writeText(text).then(() => {
      // Silent copy - no toast notification
    }).catch(err => {
      console.error('Failed to copy:', err);
    });
  };

  // Rating badge color
  const getRatingColor = (rating) => {
    switch (rating) {
      case 'A++': return 'bg-green-600 text-white';
      case 'A': return 'bg-green-500 text-white';
      case 'B': return 'bg-yellow-500 text-white';
      case 'C': return 'bg-orange-500 text-white';
      default: return 'bg-gray-500 text-white';
    }
  };

  // Signal status icon
  const getSignalStatusIcon = (status) => {
    switch (status) {
      case 'ok': return '✅';
      case 'no_data': return 'ℹ️';
      case 'error': return '❌';
      default: return '❓';
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-lg p-6 mt-8">
      {/* Header */}
      <div className="border-b pb-4 mb-6">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-2xl font-bold text-gray-800">
            🔬 Topic Intelligence (US)
          </h2>
          <button
            onClick={() => setShowSettingsModal(true)}
            className="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white text-sm font-medium rounded-md transition-colors flex items-center gap-2"
          >
            ⚙️ LLM Settings
          </button>
        </div>
        <p className="text-sm text-gray-600">
          Manual research only • USA/EN focused recommendations • Results are NOT automatically added to pipeline
        </p>
      </div>

      {/* Controls */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        {/* Channel Profile */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Channel Profile
          </label>
          <select
            value={selectedProfile}
            onChange={(e) => setSelectedProfile(e.target.value)}
            disabled={isResearching || isLoadingProfiles}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          >
            {profiles.map(profile => (
              <option key={profile.id} value={profile.id}>
                {profile.name}
              </option>
            ))}
          </select>
          <button
            onClick={() => setShowProfilesModal(true)}
            disabled={isResearching}
            className="text-xs text-blue-600 hover:text-blue-700 mt-1 disabled:text-gray-400"
          >
            View profile details
          </button>
        </div>

        {/* Count Input */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Number of Recommendations
          </label>
          <input
            type="number"
            min="5"
            max="50"
            value={count}
            onChange={(e) => setCount(e.target.value)}
            disabled={isResearching}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
          <p className="text-xs text-gray-500 mt-1">5-50 topics</p>
        </div>

        {/* Time Window */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Time Window
          </label>
          <select
            value={windowDays}
            onChange={(e) => setWindowDays(e.target.value)}
            disabled={isResearching}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          >
            <option value="7">Last 7 days</option>
            <option value="30">Last 30 days</option>
          </select>
          <p className="text-xs text-gray-500 mt-1">Competition window</p>
        </div>

        {/* Recommendation Mode */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Recommendation Mode
          </label>
          <select
            value={recommendationMode}
            onChange={(e) => setRecommendationMode(e.target.value)}
            disabled={isResearching}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          >
            <option value="momentum">🚀 Momentum (Top Growth Only)</option>
            <option value="balanced">⚖️ Balanced (Growth + Evergreen)</option>
            <option value="evergreen">🌲 Evergreen (Low Competition + Timeless)</option>
          </select>
          <p className="text-xs text-gray-500 mt-1">Filter & scoring strategy</p>
        </div>

        {/* Start Button */}
        <div className="flex items-end">
          <button
            onClick={handleStartResearch}
            disabled={isResearching}
            className="w-full px-6 py-2 bg-blue-600 text-white font-medium rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {isResearching ? 'Researching...' : 'Start Research'}
          </button>
        </div>
      </div>

      {/* Progress */}
      {isResearching && progressText && (
        <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-md">
          <div className="flex items-center">
            <div className="animate-spin h-5 w-5 border-2 border-blue-600 border-t-transparent rounded-full mr-3"></div>
            <span className="text-blue-800">{progressText}</span>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-md">
          <p className="text-red-800 font-medium">Error: {error}</p>
        </div>
      )}

      {/* Stats */}
      {stats && (
        <div className="mb-6 p-4 bg-gray-50 border border-gray-200 rounded-md">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-gray-600">Seeds:</span>
              <span className="font-medium ml-2">{stats.seeds_collected}</span>
            </div>
            <div>
              <span className="text-gray-600">Candidates:</span>
              <span className="font-medium ml-2">{stats.candidates_generated}</span>
            </div>
            <div>
              <span className="text-gray-600">Scored:</span>
              <span className="font-medium ml-2">{stats.candidates_scored}</span>
            </div>
            <div>
              <span className="text-gray-600">Time:</span>
              <span className="font-medium ml-2">{stats.elapsed_seconds}s</span>
            </div>
          </div>
        </div>
      )}

      {/* Results Grid - TOP Recommendations */}
      {results && results.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center gap-3 mb-4">
            <h3 className="text-lg font-semibold text-gray-800">
              ⭐ Top {results.length} Recommendations
            </h3>
            <span className="px-3 py-1 bg-green-100 text-green-800 text-xs font-bold rounded-full">
              GATE PASSED
            </span>
          </div>
          
          {results.map((item, index) => (
            <TopicCard 
              key={index} 
              item={item} 
              getRatingColor={getRatingColor}
              getSignalStatusIcon={getSignalStatusIcon}
              copyToClipboard={copyToClipboard}
            />
          ))}
        </div>
      )}

      {/* Other Ideas (didn't pass gate) */}
      {otherIdeas && otherIdeas.length > 0 && (
        <div className="mt-8 space-y-4">
          <details className="bg-gray-50 rounded-lg p-4">
            <summary className="cursor-pointer text-md font-semibold text-gray-700 flex items-center gap-2">
              <span>💡 Other Ideas ({otherIdeas.length})</span>
              <span className="text-xs text-gray-500 font-normal">Didn't pass gate filters — expand to view</span>
            </summary>
            <div className="mt-4 space-y-4">
              {otherIdeas.map((item, index) => (
                <TopicCard 
                  key={index} 
                  item={item} 
                  getRatingColor={getRatingColor}
                  getSignalStatusIcon={getSignalStatusIcon}
                  copyToClipboard={copyToClipboard}
                />
              ))}
            </div>
          </details>
        </div>
      )}

      {/* No Results */}
      {results && results.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          No recommendations found. Try adjusting parameters.
        </div>
      )}

      {/* LLM Settings Modal */}
      {showSettingsModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            {/* Modal Header */}
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xl font-bold text-gray-800">LLM Configuration</h3>
              <button
                onClick={() => setShowSettingsModal(false)}
                className="text-gray-500 hover:text-gray-700 text-2xl"
              >
                ×
              </button>
            </div>

            {/* Modal Content */}
            <div className="space-y-4">
              {/* Provider (disabled - only OpenRouter) */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Provider
                </label>
                <input
                  type="text"
                  value="OpenRouter"
                  disabled
                  className="w-full px-3 py-2 border border-gray-300 rounded-md bg-gray-100 text-gray-600"
                />
                <p className="text-xs text-gray-500 mt-1">OpenRouter is the only supported provider</p>
              </div>

              {/* Model */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Model
                </label>
                <select
                  value={llmConfig.model}
                  onChange={(e) => setLlmConfig(prev => ({ ...prev, model: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="openai/gpt-4o">openai/gpt-4o (recommended)</option>
                  <option value="openai/gpt-4o-mini">openai/gpt-4o-mini (faster, cheaper)</option>
                  <option value="anthropic/claude-3.5-sonnet">anthropic/claude-3.5-sonnet</option>
                  <option value="anthropic/claude-3-opus">anthropic/claude-3-opus</option>
                  <option value="google/gemini-pro-1.5">google/gemini-pro-1.5</option>
                  <option value="meta-llama/llama-3.1-70b-instruct">meta-llama/llama-3.1-70b-instruct</option>
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  Used for topic expansion (generating candidates from seed topics)
                </p>
              </div>

              {/* Temperature */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Temperature: {llmConfig.temperature}
                </label>
                <input
                  type="range"
                  min="0"
                  max="2"
                  step="0.1"
                  value={llmConfig.temperature}
                  onChange={(e) => setLlmConfig(prev => ({ ...prev, temperature: parseFloat(e.target.value) }))}
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>0.0 (deterministic)</span>
                  <span>1.0 (balanced)</span>
                  <span>2.0 (creative)</span>
                </div>
                <p className="text-xs text-gray-500 mt-2">
                  Higher = more creative/diverse topics. Lower = more focused/consistent topics.
                </p>
              </div>

              {/* Custom Prompt */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Custom Prompt (Optional)
                </label>
                <textarea
                  value={llmConfig.custom_prompt}
                  onChange={(e) => setLlmConfig(prev => ({ ...prev, custom_prompt: e.target.value }))}
                  rows={6}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
                  placeholder="Leave empty to use default prompt. Add custom instructions here to guide topic generation (e.g., 'Focus on 20th century topics' or 'Emphasize scientific discoveries')."
                />
                <p className="text-xs text-gray-500 mt-1">
                  Custom instructions will be appended to the default prompt
                </p>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="flex justify-end gap-3 mt-6 pt-4 border-t">
              <button
                onClick={() => setShowSettingsModal(false)}
                className="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-800 font-medium rounded-md transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  setShowSettingsModal(false);
                  // Config is already saved in state
                }}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md transition-colors"
              >
                Save Settings
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Profile Details Modal */}
      {showProfilesModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-3xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            {/* Modal Header */}
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xl font-bold text-gray-800">Channel Profiles</h3>
              <button
                onClick={() => setShowProfilesModal(false)}
                className="text-gray-500 hover:text-gray-700 text-2xl"
              >
                ×
              </button>
            </div>

            {/* Profiles List */}
            <div className="space-y-6">
              {profiles.map(profile => {
                // Find full profile data (may need to fetch from backend)
                const isSelected = profile.id === selectedProfile;
                
                return (
                  <div
                    key={profile.id}
                    className={`border rounded-lg p-4 ${isSelected ? 'border-blue-500 bg-blue-50' : 'border-gray-200'}`}
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div>
                        <h4 className="text-lg font-semibold text-gray-900">
                          {profile.name}
                          {isSelected && <span className="ml-2 text-sm text-blue-600">(Selected)</span>}
                        </h4>
                        <p className="text-sm text-gray-600">ID: {profile.id}</p>
                      </div>
                      {!isSelected && (
                        <button
                          onClick={() => {
                            setSelectedProfile(profile.id);
                            setShowProfilesModal(false);
                          }}
                          className="px-3 py-1 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-md"
                        >
                          Select
                        </button>
                      )}
                    </div>
                    
                    {profile.content_type && (
                      <div className="mb-2">
                        <span className="text-xs font-medium text-gray-700">Content Type: </span>
                        <span className="text-xs text-gray-600">{profile.content_type}</span>
                      </div>
                    )}
                    
                    {profile.style_notes && (
                      <div className="mb-2">
                        <span className="text-xs font-medium text-gray-700">Style: </span>
                        <span className="text-xs text-gray-600">{profile.style_notes}</span>
                      </div>
                    )}
                    
                    <p className="text-xs text-gray-500 mt-2">
                      Full profile details are applied automatically when researching.
                    </p>
                  </div>
                );
              })}
            </div>

            {/* Modal Footer */}
            <div className="flex justify-end gap-3 mt-6 pt-4 border-t">
              <button
                onClick={() => setShowProfilesModal(false)}
                className="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-800 font-medium rounded-md transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TopicIntelligencePanel;

