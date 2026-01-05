import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import MusicLibraryModal from './MusicLibraryModal';
import { toDisplayString } from '../utils/display';

const VideoProductionPipeline = ({ 
  onOpenApiManagement
}) => {
  const EPISODE_STORAGE_KEY = 'script_episode_id';

  // Inputs
  const [topic, setTopic] = useState('');
  const [language, setLanguage] = useState('en');  // Default: English
  const [targetMinutes, setTargetMinutes] = useState(12);
  const [channelProfile, setChannelProfile] = useState('default');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [openaiConfigured, setOpenaiConfigured] = useState(null);
  const [openrouterConfigured, setOpenrouterConfigured] = useState(null);
  const [defaultsSnapshot, setDefaultsSnapshot] = useState(null);
  const [defaultsStatus, setDefaultsStatus] = useState(''); // "Saved ✓" | "Unsaved changes" | ""
  const [isSavingDefaults, setIsSavingDefaults] = useState(false);
  const [isLoadingDefaults, setIsLoadingDefaults] = useState(false);

  // Per-step LLM config (stored per episode on backend for reproducibility)
  const [researchConfig, setResearchConfig] = useState({
    provider: 'openai',
    model: 'gpt-4o',
    temperature: 0.4,
    prompt_template: ''
  });
  const [narrativeConfig, setNarrativeConfig] = useState({
    provider: 'openai',
    model: 'gpt-4o',
    temperature: 0.4,
    prompt_template: ''
  });
  const [validatorConfig, setValidatorConfig] = useState({
    provider: 'openai',
    model: 'gpt-4o',
    temperature: 0.4,
    prompt_template: ''
  });
  const [ttsFormatConfig, setTtsFormatConfig] = useState({
    provider: 'openai',
    model: 'gpt-4o',
    temperature: 0.4,
    prompt_template: ''
  });
  const [fdaConfig, setFdaConfig] = useState({
    provider: 'openai',
    model: 'gpt-4o-mini',
    temperature: 0.2,
    prompt_template: ''
  });
  const [visualAssistantConfig, setVisualAssistantConfig] = useState({
    provider: 'openai',
    model: 'gpt-4o',
    temperature: 0.3,
    prompt_template: ''
  });

  // Raw output modal
  const [rawModal, setRawModal] = useState({ open: false, title: '', data: null });

  const OPENAI_MODELS = [
    'gpt-4o',
    'gpt-4o-mini',
    'gpt-4-turbo',
    'gpt-3.5-turbo',
  ];

  const OPENROUTER_MODELS = [
    'openai/chatgpt-4o-latest',
    'openai/gpt-5.2',
    'google/gemini-2.5-pro',
    'google/gemini-3-pro-preview',
    'openai/gpt-4o',
    'openai/gpt-4o-mini',
    'anthropic/claude-3.5-sonnet',
    'meta-llama/llama-3.1-70b-instruct',
  ];

  const ModelField = ({ value, onChange, disabled, provider }) => {
    const models = (provider === 'openrouter') ? OPENROUTER_MODELS : OPENAI_MODELS;
    return (
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-2 py-2 border border-gray-300 rounded-md text-sm"
        disabled={disabled}
      >
        {models.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
    );
  };

  // Server state (source of truth)
  const [episodeId, setEpisodeId] = useState(() => {
    try {
      return localStorage.getItem(EPISODE_STORAGE_KEY) || '';
    } catch (e) {
      return '';
    }
  });
  const [scriptState, setScriptState] = useState(null);

  // UI state
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState('');
  const [showTtsPreview, setShowTtsPreview] = useState(false);
  const pollRef = useRef(null);
  const videoPollRef = useRef(null);
  const videoPollTimeoutRef = useRef(null);

  // Convenience alias (backend may legitimately return null until TTS step is complete)
  const ttsPkg = scriptState?.tts_ready_package ?? null;

  // TTS Generation state
  const [ttsState, setTtsState] = useState({
    status: 'idle', // idle | generating | done | error
    progress: 0,
    currentBlock: 0,
    totalBlocks: 0,
    generatedFiles: [],
    error: null
  });
  const [showAudioFiles, setShowAudioFiles] = useState(false); // Collapsible pro audio soubory

  // Background Music (global library)
  const [showMusicLibrary, setShowMusicLibrary] = useState(false);
  const [selectedGlobalMusic, setSelectedGlobalMusic] = useState(null);
  const [autoSelectedMusic, setAutoSelectedMusic] = useState(null);
  // Background music gain (dB). Voiceover is reference; negative values keep music under narration.
  // Load from localStorage or default to -24
  const [musicBgGainDb, setMusicBgGainDb] = useState(() => {
    const saved = localStorage.getItem('musicBgGainDb');
    return saved !== null ? Number(saved) : -24;
  });

  // AAR Search Queries (user overrides)
  const [userSearchQueries, setUserSearchQueries] = useState([]);
  const [autoSearchQueries, setAutoSearchQueries] = useState([]);
  const [episodePoolQueries, setEpisodePoolQueries] = useState([]);
  const [excludedAutoQueries, setExcludedAutoQueries] = useState([]);
  const [searchQueryInput, setSearchQueryInput] = useState('');
  const [searchQuerySaving, setSearchQuerySaving] = useState(false);
  const [searchQueryError, setSearchQueryError] = useState('');

  const normalizeQuery = (q) => {
    try {
      if (!q) return '';
      return String(q).trim().split(/\s+/).join(' ');
    } catch (e) {
      return '';
    }
  };

  const extractShotPlanScenes = (state) => {
    try {
      const md = state?.metadata;
      const wrapper = md?.shot_plan;
      const scenes =
        wrapper?.shot_plan?.scenes ||
        state?.shot_plan?.scenes ||
        [];
      return Array.isArray(scenes) ? scenes : [];
    } catch (e) {
      return [];
    }
  };

  // NOTE: Auto queries are sourced from backend (/api/video/search-queries/<episode_id>)
  // because backend also tracks excluded_auto_queries. If we derive from shot_plan directly,
  // excluded auto-badges would "come back" after refresh and AAR would keep using them.

  const loadSearchQueries = async (epId) => {
    if (!epId) return;
    try {
      const res = await axios.get(`/api/video/search-queries/${epId}`, { timeout: 10000 });
      if (res?.data?.success) {
        setUserSearchQueries(Array.isArray(res.data.user_queries) ? res.data.user_queries : []);
        setAutoSearchQueries(Array.isArray(res.data.auto_queries) ? res.data.auto_queries : []);
        setEpisodePoolQueries(Array.isArray(res.data.episode_pool_queries) ? res.data.episode_pool_queries : []);
        setExcludedAutoQueries(Array.isArray(res.data.excluded_auto_queries) ? res.data.excluded_auto_queries : []);
      }
    } catch (e) {
      // Do not fail silently → user needs to know why refresh does nothing.
      setSearchQueryError(e?.response?.data?.error || e?.message || 'Nepodařilo se načíst search queries');
    }
  };

  const addUserSearchQuery = async () => {
    const q = normalizeQuery(searchQueryInput);
    if (!episodeId) return;
    if (!q) return;
    setSearchQueryError('');
    setSearchQuerySaving(true);
    try {
      const res = await axios.post(`/api/video/search-queries/${episodeId}`, { query: q }, { timeout: 10000 });
      if (!res?.data?.success) {
        throw new Error(res?.data?.error || 'Nepodařilo se uložit query');
      }
      setSearchQueryInput('');
      setUserSearchQueries(Array.isArray(res.data.user_queries) ? res.data.user_queries : []);
      setAutoSearchQueries(Array.isArray(res.data.auto_queries) ? res.data.auto_queries : []);
      setEpisodePoolQueries(Array.isArray(res.data.episode_pool_queries) ? res.data.episode_pool_queries : []);
      setExcludedAutoQueries(Array.isArray(res.data.excluded_auto_queries) ? res.data.excluded_auto_queries : []);
      // Refresh state so AAR sees the updated script_state immediately
      await refreshState(episodeId);
    } catch (e) {
      setSearchQueryError(e?.response?.data?.error || e?.message || 'Nepodařilo se uložit query');
    } finally {
      setSearchQuerySaving(false);
    }
  };

  const removeUserSearchQuery = async (q) => {
    const nq = normalizeQuery(q);
    if (!episodeId || !nq) return;
    setSearchQueryError('');
    setSearchQuerySaving(true);
    try {
      const res = await axios.delete(`/api/video/search-queries/${episodeId}`, {
        data: { query: nq },
        timeout: 10000
      });
      if (!res?.data?.success) {
        throw new Error(res?.data?.error || 'Nepodařilo se odebrat query');
      }
      setUserSearchQueries(Array.isArray(res.data.user_queries) ? res.data.user_queries : []);
      setAutoSearchQueries(Array.isArray(res.data.auto_queries) ? res.data.auto_queries : []);
      setEpisodePoolQueries(Array.isArray(res.data.episode_pool_queries) ? res.data.episode_pool_queries : []);
      setExcludedAutoQueries(Array.isArray(res.data.excluded_auto_queries) ? res.data.excluded_auto_queries : []);
      await refreshState(episodeId);
    } catch (e) {
      setSearchQueryError(e?.response?.data?.error || e?.message || 'Nepodařilo se odebrat query');
    } finally {
      setSearchQuerySaving(false);
    }
  };

  const formatDuration = (seconds) => {
    const s = Number(seconds);
    if (!Number.isFinite(s) || s < 0) return '—';
    const minutes = Math.floor(s / 60);
    const remainingSeconds = Math.floor(s % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  const getTtsBlockCount = (pkg) => {
    try {
      if (!pkg) return 0;
      // Preferred: chapters[].narration_blocks[]
      const chapters = Array.isArray(pkg.chapters) ? pkg.chapters : [];
      let n = 0;
      chapters.forEach((ch) => {
        const blocks = Array.isArray(ch?.narration_blocks) ? ch.narration_blocks : [];
        n += blocks.length;
      });
      // Legacy fallback: pkg.narration_blocks[]
      if (n === 0 && Array.isArray(pkg.narration_blocks)) return pkg.narration_blocks.length;
      // Another fallback: pkg.tts_segments[]
      if (n === 0 && Array.isArray(pkg.tts_segments)) return pkg.tts_segments.length;
      return n;
    } catch (e) {
      return 0;
    }
  };

  // Auto-select music when script is ready
  const autoSelectMusic = async () => {
    if (!scriptState?.tts_ready_package) return;

    try {
      // Determine mood/tags from script context
      const scriptTopic = scriptState?.episode_input?.topic || scriptState?.topic || '';
      const estimatedDuration = scriptState?.tts_ready_package?.estimated_duration_seconds || 0;

      // Simple heuristics for mood detection (can be improved with LLM)
      let preferredMood = 'neutral';
      let preferredTags = [];

      // Dark/mysterious topics
      if (scriptTopic.toLowerCase().match(/dark|mystery|crime|war|death|murder/i)) {
        preferredMood = 'dark';
        preferredTags = ['cinematic', 'dramatic'];
      }
      // Uplifting topics
      else if (scriptTopic.toLowerCase().match(/hope|future|innovation|discover|success/i)) {
        preferredMood = 'uplifting';
        preferredTags = ['ambient', 'electronic'];
      }
      // Dramatic topics
      else if (scriptTopic.toLowerCase().match(/battle|conflict|intense|crisis/i)) {
        preferredMood = 'dramatic';
        preferredTags = ['orchestral', 'cinematic'];
      }
      // Default: peaceful/ambient
      else {
        preferredMood = 'peaceful';
        preferredTags = ['ambient', 'minimal'];
      }

      const res = await axios.post('/api/music/library/select-auto', {
        preferred_mood: preferredMood,
        preferred_tags: preferredTags,
        // IMPORTANT: do NOT require long tracks.
        // Backend loops background music with FFmpeg (-stream_loop -1), so short tracks are valid.
        // min_duration_sec intentionally omitted.
        context: {
          topic: scriptTopic,
          duration: estimatedDuration
        }
      }, { timeout: 10000 });

      if (res.data?.success && res.data.selected_track) {
        setAutoSelectedMusic(res.data.selected_track);
        setSelectedGlobalMusic(res.data.selected_track);
        // Persist selection for this episode so compilation uses it deterministically
        if (episodeId) {
          try {
            await axios.post(`/api/projects/${episodeId}/music/select-global`, {
              selected_track: res.data.selected_track
            }, { timeout: 10000 });
          } catch (e) {
            // Non-critical; compilation builder can still auto-select server-side
            console.warn('Auto-selected music could not be persisted:', e);
          }
        }
      }
    } catch (e) {
      console.warn('Auto-select music failed:', e);
      // Not critical, just log
    }
  };

  // NOTE: We intentionally do not auto-run autoSelectMusic().
  // Users found automatic actions confusing; we keep it as an explicit button ("🤖 Auto-vybrat hudbu").

  // Hydrate selected_global_music from script_state on load
  useEffect(() => {
    if (scriptState?.selected_global_music) {
      setSelectedGlobalMusic(scriptState.selected_global_music);
    }
    // Only load from script_state if there's a saved value (user explicitly changed it for this episode)
    // Otherwise, keep the localStorage default loaded during useState initialization
    if (scriptState?.music_bg_gain_db !== undefined && scriptState?.music_bg_gain_db !== null) {
      const v = Number(scriptState.music_bg_gain_db);
      if (Number.isFinite(v)) {
        setMusicBgGainDb(v);
        // Also update localStorage so it persists across projects
        localStorage.setItem('musicBgGainDb', v);
      }
    }
  }, [scriptState]);

  // If backend state changes and TTS package disappears, ensure UI doesn't keep trying to render TTS preview.
  useEffect(() => {
    if (!ttsPkg && showTtsPreview) {
      setShowTtsPreview(false);
    }
  }, [ttsPkg, showTtsPreview]);

  const handleMusicLibrarySelect = async (track) => {
    setSelectedGlobalMusic(track);
    setAutoSelectedMusic(null); // Clear auto-selection when manually selected
    
    // Save to script_state
    if (episodeId) {
      try {
        await axios.post(`/api/projects/${episodeId}/music/select-global`, {
          selected_track: track
        }, { timeout: 10000 });
      } catch (e) {
        console.error('Failed to save selected music:', e);
        // Non-critical, just log
      }
    }
  };
  
  // Video Compilation state  
  const [videoCompilationState, setVideoCompilationState] = useState({
    status: 'idle', // idle | running | done | error
    progress: 0,
    currentStep: '',
    error: null,
    outputPath: null,
  });

  // Archive Preview state (for AAR stats)
  const [archiveStats, setArchiveStats] = useState(null);
  const [archiveStatsLoading, setArchiveStatsLoading] = useState(false);
  const [archivePreviewMode, setArchivePreviewMode] = useState(false); // true when AAR-only preview is running

  // AAR Step-by-Step State
  const [aarStep, setAarStep] = useState('idle'); // idle | queries_generated | search_completed | llm_completed
  const [aarQueries, setAarQueries] = useState([]); // Generated queries (user can edit)
  const [aarQueryChecked, setAarQueryChecked] = useState({}); // {query: bool} - checkboxes
  const [aarRawResults, setAarRawResults] = useState(null); // Raw search results (before LLM)
  const [aarManualSelection, setAarManualSelection] = useState({ videos: {}, images: {} }); // Manual selection checkboxes
  const [aarLoading, setAarLoading] = useState(false);
  const [aarError, setAarError] = useState('');
  const [visualCandidates, setVisualCandidates] = useState(null);
  const [visualCandidatesLoading, setVisualCandidatesLoading] = useState(false);
  const [showVisualCandidates, setShowVisualCandidates] = useState(false);
  const [selectedBeatAssets, setSelectedBeatAssets] = useState({}); // { "scene_id:block_id": archive_item_id }
  
  // Episode Pool view (show ALL found assets, not just per-beat subset)
  const [episodePool, setEpisodePool] = useState(null);
  const [episodePoolLoading, setEpisodePoolLoading] = useState(false);
  const [showEpisodePool, setShowEpisodePool] = useState(false);
  const [selectedPoolAssets, setSelectedPoolAssets] = useState(new Set()); // Set of archive_item_id
  const [episodePoolView, setEpisodePoolView] = useState('selected'); // 'selected' | 'unique' | 'raw'
  
  // Visual Assistant state (LLM Vision reranking)
  const [visualAssistantRunning, setVisualAssistantRunning] = useState(false);
  const [visualAssistantResults, setVisualAssistantResults] = useState(null);
  const [showBeforeAfter, setShowBeforeAfter] = useState(false);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const stopVideoPolling = () => {
    if (videoPollRef.current) {
      clearInterval(videoPollRef.current);
      videoPollRef.current = null;
    }
    if (videoPollTimeoutRef.current) {
      clearTimeout(videoPollTimeoutRef.current);
      videoPollTimeoutRef.current = null;
    }
  };

  // Episode Pool asset selection handlers
  const togglePoolAssetSelection = (assetId) => {
    setSelectedPoolAssets(prev => {
      const newSet = new Set(prev);
      if (newSet.has(assetId)) {
        newSet.delete(assetId);
      } else {
        newSet.add(assetId);
      }
      return newSet;
    });
  };

  const selectAllPoolAssets = (assetType) => {
    if (!episodePool?.pool) return;
    const assets = assetType === 'videos' ? episodePool.pool.videos : episodePool.pool.images;
    setSelectedPoolAssets(prev => {
      const newSet = new Set(prev);
      (assets || []).forEach(a => {
        if (a.archive_item_id) newSet.add(a.archive_item_id);
      });
      return newSet;
    });
  };

  const deselectAllPoolAssets = () => {
    setSelectedPoolAssets(new Set());
  };

  const resetForNewRun = () => {
    const hasActiveWork =
      isStarting ||
      ttsState?.status === 'generating' ||
      videoCompilationState?.status === 'running' ||
      (scriptStatus || '').startsWith('RUNNING_');

    const ok = !hasActiveWork
      ? true
      : window.confirm(
          'Pipeline právě běží. Opravdu chceš resetovat UI a začít nový běh?\\n\\n' +
          'Pozn.: běh na serveru se tím nemusí zastavit, ale UI se vyčistí.'
        );
    if (!ok) return;

    stopPolling();
    stopVideoPolling();

    // Clear episode-specific state
    setError('');
    setRawModal({ open: false, title: '', data: null });
    setShowTtsPreview(false);
    setShowAudioFiles(false);

    setTtsState({
      status: 'idle',
      progress: 0,
      currentBlock: 0,
      totalBlocks: 0,
      generatedFiles: [],
      error: null,
    });

    setVideoCompilationState({
      status: 'idle',
      progress: 0,
      currentStep: '',
      error: null,
      outputPath: null,
    });

    setSelectedGlobalMusic(null);
    setAutoSelectedMusic(null);

    setScriptState(null);
    setIsStarting(false);

    // Remove persisted episode_id so the next load is a clean page
    setEpisodeId('');
    try {
      localStorage.removeItem(EPISODE_STORAGE_KEY);
    } catch (e) {
      // ignore
    }
  };
  
  // Video Compilation generation
  const generateVideoCompilation = async (opts = {}) => {
    if (!episodeId || !scriptState) {
      setVideoCompilationState(prev => ({...prev, status: 'error', error: 'Episode ID není dostupný'}));
      return;
    }

    stopVideoPolling();
    
    setVideoCompilationState({
      status: 'running',
      progress: 10,
      currentStep: (opts?.mode === 'cb_only') ? 'Remixing music (CB only)...' : 'Starting AAR + CB pipeline...',
      error: null,
      outputPath: null,
    });
    
    try {
      // Call backend API to start compilation
      const response = await axios.post('/api/video/compile', {
        episode_id: episodeId,
        music_bg_gain_db: musicBgGainDb,
        ...(opts?.mode ? { mode: opts.mode } : {})
      }, { timeout: 10000 });
      
      if (!response.data.success) {
        throw new Error(response.data.error || 'Failed to start video compilation');
      }
      
      // Start polling for progress
      setVideoCompilationState(prev => ({...prev, progress: 20, currentStep: 'Compilation started, polling for progress...'}));
      
      // Poll script state for updates
      videoPollRef.current = setInterval(async () => {
        try {
          const stateRes = await axios.get(`/api/script/state/${episodeId}`);
          const state = stateRes.data.data;
          
          const aarStep = state?.steps?.asset_resolver;
          const cbStep = state?.steps?.compilation_builder;
          
          // Update progress based on step status
          if (aarStep?.status === 'RUNNING') {
            // Show detailed AAR progress
            const aarOutput = state?.asset_resolver_output;
            let aarProgress = '🔍 Hledám videa na archive.org...';
            if (aarOutput && aarOutput.total_scenes) {
              aarProgress = `🔍 Hledám videa (${aarOutput.scenes_with_assets || 0}/${aarOutput.total_scenes} scén zpracováno)`;
            }
            setVideoCompilationState(prev => ({...prev, progress: 40, currentStep: aarProgress}));
          } else if (aarStep?.status === 'DONE' && cbStep?.status === 'RUNNING') {
            // Get CB progress details (real-time from backend)
            const cbProgress = state?.compilation_progress;
            let progressMsg = '🎬 Stahuji a vyřezávám videa...';
            let progressPct = 50;
            
            if (cbProgress && cbProgress.message) {
              progressMsg = cbProgress.message;
              progressPct = 50 + (cbProgress.percent || 0) / 2; // CB is 50-100% of total
            } else {
              // Fallback: show AAR summary
              const aarOutput = state?.asset_resolver_output;
              if (aarOutput) {
                // total_assets_resolved = assignments across scenes (can be > unique pool size)
                progressMsg = `🎬 Stahuji a vyřezávám videa... (přiřazení: ${aarOutput.total_assets_resolved || 0})`;
              }
            }
            
            setVideoCompilationState(prev => ({
              ...prev, 
              progress: progressPct, 
              currentStep: progressMsg,
              cbDetails: cbProgress?.details || null  // Store detailed progress
            }));
          } else if (cbStep?.status === 'DONE') {
            // Compilation complete!
            stopVideoPolling();
            const videoPath = state.compilation_video_path;
            
            // Převeď absolutní cestu na API endpoint
            let videoUrl = videoPath;
            if (videoPath) {
              const filename = videoPath.split('/').pop(); // Získej jen název souboru
              videoUrl = `http://localhost:50000/api/video/stream/${filename}`;
            }
            
            setVideoCompilationState({
              status: 'done',
              progress: 100,
              currentStep: 'Complete!',
              error: null,
              outputPath: videoUrl,
            });
            // Refresh script state
            await refreshState(episodeId);
          } else if (aarStep?.status === 'ERROR' || cbStep?.status === 'ERROR') {
            stopVideoPolling();
            const error = aarStep?.error || cbStep?.error || 'Unknown error';
            setVideoCompilationState(prev => ({
              ...prev,
              status: 'error',
              error: error
            }));
          }
        } catch (pollError) {
          console.error('Polling error:', pollError);
        }
      }, 3000); // Poll every 3 seconds
      
      // Set timeout to stop polling after 60 minutes (large projects can take longer)
      videoPollTimeoutRef.current = setTimeout(() => {
        stopVideoPolling();
        setVideoCompilationState(prev => {
          if (prev.status === 'running') {
            return {...prev, status: 'error', error: 'Timeout - process took too long (60 min)'};
          }
          return prev;
        });
      }, 60 * 60 * 1000);
      
    } catch (e) {
      // Handle 409 Conflict (compilation already running) gracefully → switch to polling mode
      if (e.response?.status === 409) {
        console.log('⚠️ Compilation already running, entering polling mode...');
        stopVideoPolling();
        setVideoCompilationState({
          status: 'running',
          progress: 10,
          currentStep: 'Kompilace již běží...',
          error: null,
          outputPath: null
        });
        
        // Start the same polling logic as the success path
        videoPollRef.current = setInterval(async () => {
          try {
            const stateRes = await axios.get(`/api/script/state/${episodeId}`);
            const state = stateRes.data.data;
            
            const aarStep = state?.steps?.asset_resolver;
            const cbStep = state?.steps?.compilation_builder;
            
            // Update progress based on step status
            if (aarStep?.status === 'RUNNING') {
              // Show detailed AAR progress
              const aarOutput = state?.asset_resolver_output;
              let aarProgress = '🔍 Hledám videa na archive.org...';
              if (aarOutput && aarOutput.total_scenes) {
                aarProgress = `🔍 Hledám videa (${aarOutput.scenes_with_assets || 0}/${aarOutput.total_scenes} scén zpracováno)`;
              }
              setVideoCompilationState(prev => ({...prev, progress: 40, currentStep: aarProgress, status: 'running'}));
            } else if (aarStep?.status === 'DONE' && cbStep?.status === 'RUNNING') {
              // Get AAR details
              const aarOutput = state?.asset_resolver_output;
              let aarDetails = '';
              if (aarOutput) {
                const assignments = aarOutput.total_assets_resolved || 0;
                const scenes = aarOutput.total_scenes || 0;
                const poolUnique = aarOutput.pool_unique_total_assets;
                const poolSelected = aarOutput.pool_selected_total_assets;
                const rawTotal = aarOutput.pool_raw_total_assets;
                const extra = [
                  (poolUnique != null ? `unique: ${poolUnique}` : null),
                  (poolSelected != null ? `pool: ${poolSelected}` : null),
                  (rawTotal != null ? `raw: ${rawTotal}` : null),
                ].filter(Boolean).join(', ');
                aarDetails = ` (přiřazení: ${assignments} / scény: ${scenes}${extra ? ` / ${extra}` : ''})`;
              }
              setVideoCompilationState(prev => ({...prev, progress: 70, currentStep: `🎬 Stahuji a vyřezávám videa, skládám kompilaci...${aarDetails}`, status: 'running'}));
            } else if (cbStep?.status === 'DONE') {
              // Compilation complete!
              stopVideoPolling();
              const videoPath = state.compilation_video_path;
              
              // Převeď absolutní cestu na API endpoint
              let videoUrl = videoPath;
              if (videoPath) {
                const filename = videoPath.split('/').pop(); // Získej jen název souboru
                videoUrl = `http://localhost:50000/api/video/stream/${filename}`;
              }
              
              setVideoCompilationState({
                status: 'done',
                progress: 100,
                currentStep: 'Complete!',
                error: null,
                outputPath: videoUrl,
              });
              // Refresh script state
              await refreshState(episodeId);
            } else if (aarStep?.status === 'ERROR' || cbStep?.status === 'ERROR') {
              stopVideoPolling();
              const error = aarStep?.error || cbStep?.error || 'Unknown error';
              setVideoCompilationState(prev => ({
                ...prev,
                status: 'error',
                error: error
              }));
            }
          } catch (pollError) {
            console.error('Polling error:', pollError);
          }
        }, 3000); // Poll every 3 seconds
        
        // Set timeout to stop polling after 60 minutes (large projects can take longer)
        videoPollTimeoutRef.current = setTimeout(() => {
          stopVideoPolling();
          setVideoCompilationState(prev => {
            if (prev.status === 'running') {
              return {...prev, status: 'error', error: 'Timeout - process took too long (60 min)'};
            }
            return prev;
          });
        }, 60 * 60 * 1000);
      } else {
        setVideoCompilationState(prev => ({
          ...prev,
          status: 'error',
          error: e.response?.data?.error || e.message || 'Chyba při generování videa'
        }));
      }
    }
  };

  // AAR STEP-BY-STEP FUNCTIONS
  const aarStep1GenerateQueries = async () => {
    if (!episodeId) {
      alert('Episode ID není dostupný');
      return;
    }
    
    setAarLoading(true);
    setAarError('');
    
    try {
      const response = await axios.post(`/api/aar/step1-generate-queries/${episodeId}`, {}, { timeout: 15000 });
      
      if (!response.data.success) {
        throw new Error(response.data.error || 'Query generation failed');
      }
      
      const queries = response.data.queries || [];
      setAarQueries(queries);
      setAarStep('queries_generated');
      
      // Initialize checkboxes (all checked by default)
      const checked = {};
      queries.forEach(q => {
        checked[q] = true;
      });
      setAarQueryChecked(checked);
      
      console.log(`✅ AAR Step 1: Generated ${queries.length} queries`);
      
    } catch (e) {
      setAarError(e?.response?.data?.error || e?.message || 'Query generation failed');
      console.error(`❌ AAR Step 1 failed:`, e?.response?.data?.error || e?.message);
    } finally {
      setAarLoading(false);
    }
  };

  const aarStep2Search = async () => {
    if (!episodeId) {
      alert('Episode ID není dostupný');
      return;
    }
    
    // Get checked queries
    const selectedQueries = aarQueries.filter(q => aarQueryChecked[q] === true);
    
    if (selectedQueries.length === 0) {
      alert('❌ Musíš vybrat alespoň jeden query!');
      return;
    }
    
    setAarLoading(true);
    setAarError('');
    
    try {
      // #region agent log (hypothesis H4)
      fetch('http://127.0.0.1:7242/ingest/d36edf10-e9b4-4dcd-a9ef-c1a2da89c79a',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'frontend/src/components/VideoProductionPipeline.js:aarStep2Search',message:'Step2 Search Now clicked',data:{episodeId:String(episodeId||''),selectedQueriesCount:Number(selectedQueries?.length||0),firstQuery:String((selectedQueries&&selectedQueries[0])||'').slice(0,160)},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'H4'})}).catch(()=>{});
      // #endregion
      // AAR Step2 can be slow (multi-source, multiple queries). Use a long timeout.
      const response = await axios.post(
        `/api/aar/step2-search/${episodeId}`,
        { queries: selectedQueries },
        { timeout: 10 * 60 * 1000 } // 10 min
      );
      
      if (!response.data.success) {
        throw new Error(response.data.error || 'Search failed');
      }

      // #region agent log (hypothesis H4)
      fetch('http://127.0.0.1:7242/ingest/d36edf10-e9b4-4dcd-a9ef-c1a2da89c79a',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'frontend/src/components/VideoProductionPipeline.js:aarStep2Search',message:'Step2 Search response',data:{episodeId:String(episodeId||''),success:Boolean(response?.data?.success),videoCandidates:Number(response?.data?.stats?.total_video_candidates||0),imageCandidates:Number(response?.data?.stats?.total_image_candidates||0)},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'H4'})}).catch(()=>{});
      // #endregion
      
      setAarRawResults(response.data);
      setAarStep('search_completed');
      
      const stats = response.data.stats || {};
      console.log(`✅ AAR Step 2: Search completed - Videos: ${stats.total_video_candidates || 0}, Images: ${stats.total_image_candidates || 0}`);
      
    } catch (e) {
      setAarError(e?.response?.data?.error || e?.message || 'Search failed');
      console.error(`❌ AAR Step 2 failed:`, e?.response?.data?.error || e?.message);
    } finally {
      setAarLoading(false);
    }
  };

  const aarStep3LLMCheck = async () => {
    if (!episodeId) {
      alert('Episode ID není dostupný');
      return;
    }
    
    setAarLoading(true);
    setAarError('');
    
    try {
      // Check if user made manual selection
      const selectedVideoIds = Object.keys(aarManualSelection.videos || {}).filter(k => aarManualSelection.videos[k]);
      const selectedImageIds = Object.keys(aarManualSelection.images || {}).filter(k => aarManualSelection.images[k]);
      const hasManualSelection = selectedVideoIds.length > 0 || selectedImageIds.length > 0;
      
      const response = await axios.post(`/api/aar/step3-llm-check/${episodeId}`, {
        manual_selection: hasManualSelection ? {
          video_ids: selectedVideoIds,
          image_ids: selectedImageIds,
        } : null
      }, { timeout: 600000 }); // 10 min for LLM (81 items = ~7-8 min)
      
      if (!response.data.success) {
        throw new Error(response.data.error || 'LLM check failed');
      }
      
      setAarStep('llm_completed');
      
      const stats = response.data.stats || {};
      console.log(`✅ AAR Step 3: LLM Quality Check completed - Pool videos: ${stats.pool_videos || 0}, Pool images: ${stats.pool_images || 0}${hasManualSelection ? ' (manual selection applied)' : ''}`);
      
      // Reload archive stats to show final pool
      await loadArchiveStats();
      await refreshState(episodeId);
      
    } catch (e) {
      setAarError(e?.response?.data?.error || e?.message || 'LLM check failed');
      console.error(`❌ AAR Step 3 failed:`, e?.response?.data?.error || e?.message);
    } finally {
      setAarLoading(false);
    }
  };

  // Archive Preview (AAR only) - finds videos/images without downloading
  const previewArchiveVideos = async () => {
    if (!episodeId || !scriptState) {
      alert('Episode ID není dostupný');
      return;
    }

    // #region agent log (hypothesis C)
    fetch('http://127.0.0.1:7242/ingest/d36edf10-e9b4-4dcd-a9ef-c1a2da89c79a',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'frontend/src/components/VideoProductionPipeline.js:previewArchiveVideos',message:'User triggered Preview Videa (AAR only)',data:{episodeId:String(episodeId||''),stateTopic:String(scriptState?.topic||scriptState?.episode_input?.topic||''),selectedTitle:String(scriptState?.selected_title||'')},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'C'})}).catch(()=>{});
    // #endregion

    stopVideoPolling();
    setArchivePreviewMode(true);
    setArchiveStats(null);
    
    setVideoCompilationState({
      status: 'running',
      progress: 10,
      currentStep: 'Hledám videa a obrázky na archive.org (AAR)...',
      error: null,
      outputPath: null,
    });
    
    try {
      // Call backend API with mode: "aar_only"
      const response = await axios.post('/api/video/compile', {
        episode_id: episodeId,
        mode: 'aar_only'
      }, { timeout: 10000 });

      // #region agent log (hypothesis C)
      fetch('http://127.0.0.1:7242/ingest/d36edf10-e9b4-4dcd-a9ef-c1a2da89c79a',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'frontend/src/components/VideoProductionPipeline.js:previewArchiveVideos',message:'Preview Videa start response',data:{episodeId:String(episodeId||''),success:Boolean(response?.data?.success),mode:String(response?.data?.mode||''),error:String(response?.data?.error||'')},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'C'})}).catch(()=>{});
      // #endregion
      
      if (!response.data.success) {
        throw new Error(response.data.error || 'Failed to start AAR preview');
      }
      
      // Start polling for AAR progress
      setVideoCompilationState(prev => ({...prev, progress: 20, currentStep: 'AAR běží, hledám kandidáty...'}));
      
      // Poll script state for AAR completion
      videoPollRef.current = setInterval(async () => {
        try {
          const stateRes = await axios.get(`/api/script/state/${episodeId}`);
          const state = stateRes.data.data;
          
          const aarStep = state?.steps?.asset_resolver;
          
          // Update progress based on AAR status
          if (aarStep?.status === 'DONE') {
            stopVideoPolling();
            setVideoCompilationState({
              status: 'idle',
              progress: 100,
              currentStep: '',
              error: null,
              outputPath: null,
            });
            setArchivePreviewMode(false);
            // Load stats
            await loadArchiveStats();
            // Refresh script state
            await refreshState(episodeId);
          } else if (aarStep?.status === 'ERROR') {
            stopVideoPolling();
            setVideoCompilationState({
              status: 'error',
              progress: 0,
              currentStep: '',
              error: aarStep?.error || 'AAR failed',
              outputPath: null,
            });
            setArchivePreviewMode(false);
          } else if (aarStep?.status === 'RUNNING') {
            const rawPct = Number(aarStep.progress);
            const pct = Number.isFinite(rawPct) ? Math.max(0, Math.min(99, rawPct)) : 10;
            setVideoCompilationState(prev => ({
              ...prev,
              progress: Math.max(prev.progress || 0, pct),
              currentStep: aarStep?.message || `Hledám videa... ${Math.round(pct)}%`
            }));
          }
        } catch (pollError) {
          console.error('Polling error:', pollError);
        }
      }, 2000); // Poll every 2 seconds
      
      // Set timeout to stop polling after 30 minutes (preview can be slower on large projects)
      videoPollTimeoutRef.current = setTimeout(() => {
        // On timeout: do NOT blindly fail. First check server state once.
        (async () => {
          try {
            const stateRes = await axios.get(`/api/script/state/${episodeId}`);
            const state = stateRes.data.data;
            const aarStep = state?.steps?.asset_resolver;
            if (aarStep?.status === 'DONE') {
              stopVideoPolling();
              setVideoCompilationState({
                status: 'idle',
                progress: 100,
                currentStep: '',
                error: null,
                outputPath: null,
              });
              setArchivePreviewMode(false);
              await loadArchiveStats();
              await refreshState(episodeId);
              return;
            }
            if (aarStep?.status === 'ERROR') {
              stopVideoPolling();
              setVideoCompilationState({
                status: 'error',
                progress: 0,
                currentStep: '',
                error: aarStep?.error || 'AAR failed',
                outputPath: null,
              });
              setArchivePreviewMode(false);
              return;
            }
          } catch (e) {
            // ignore
          }
          stopVideoPolling();
          setVideoCompilationState(prev => ({
            ...prev,
            status: 'error',
            error: 'Timeout - AAR preview trval příliš dlouho (30 min). Zkuste to znovu, nebo zkontrolujte logy serveru.',
          }));
          setArchivePreviewMode(false);
        })();
      }, 30 * 60 * 1000);
      
    } catch (e) {
      stopVideoPolling();
      setVideoCompilationState({
        status: 'error',
        progress: 0,
        currentStep: '',
        error: e.response?.data?.error || e.message || 'Chyba při AAR preview',
        outputPath: null,
      });
      setArchivePreviewMode(false);
    }
  };

  // Load archive stats from manifest
  const loadArchiveStats = async () => {
    if (!episodeId) return;
    
    setArchiveStatsLoading(true);
    try {
      const response = await axios.get(`/api/video/archive-stats/${episodeId}`);
      if (response.data.success) {
        setArchiveStats(response.data.stats);
      } else {
        setArchiveStats(null);
      }
    } catch (e) {
      console.error('Failed to load archive stats:', e);
      setArchiveStats(null);
    } finally {
      setArchiveStatsLoading(false);
    }
  };

  const loadVisualCandidates = async () => {
    if (!episodeId) return;
    setVisualCandidatesLoading(true);
    try {
      const res = await axios.get(`/api/video/visual-candidates/${episodeId}`, { timeout: 60000 });
      if (res.data?.success) {
        setVisualCandidates(res.data);
        // If Visual Assistant already ran in the past, manifest can contain metadata.
        // Hydrate UI so analysis badges + "analyzed X candidates" persist after reload.
        try {
          const md = res.data?.assistant_metadata;
          const analyzed = md ? Number(md.total_candidates_analyzed) : NaN;
          if (Number.isFinite(analyzed) && analyzed > 0) {
            setVisualAssistantResults((prev) => {
              if (prev?.total_analyzed) return prev;
              return {
                success: true,
                total_analyzed: analyzed,
                total_beats: Number(md.total_beats) || 0,
                model: md.model,
              };
            });
          }
        } catch (e) {
          // non-fatal
        }
        try {
          const sel = {};
          (res.data.scenes || []).forEach((sc) => {
            (sc.beats || []).forEach((b) => {
              const sid = sc.scene_id;
              const bid = b.block_id;
              const s = String(b.selected_asset_id || '').trim();
              if (sid && bid && s) {
                sel[`${sid}:${bid}`] = s;
              }
            });
          });
          setSelectedBeatAssets(sel);
        } catch (e) {
          // non-fatal
        }
      } else {
        setVisualCandidates(null);
      }
    } catch (e) {
      console.error('Failed to load visual candidates:', e);
      setVisualCandidates(null);
    } finally {
      setVisualCandidatesLoading(false);
    }
  };

  const loadEpisodePool = async () => {
    if (!episodeId) return;
    setEpisodePoolLoading(true);
    try {
      const res = await axios.get(`/api/video/episode-pool/${episodeId}`, { timeout: 30000 });
      if (res.data?.success) {
        setEpisodePool(res.data);
      }
    } catch (e) {
      console.error('Failed to load episode pool:', e);
    } finally {
      setEpisodePoolLoading(false);
    }
  };

  const selectManifestAsset = async ({ sceneId, blockId, archiveItemId }) => {
    if (!episodeId) return;
    try {
      await axios.post(
        `/api/video/manifest/select-asset/${episodeId}`,
        {
          scene_id: sceneId,
          block_id: blockId,
          archive_item_id: archiveItemId || null,
        },
        { timeout: 15000 }
      );
      const key = `${sceneId}:${blockId}`;
      setSelectedBeatAssets((prev) => {
        const next = { ...(prev || {}) };
        if (archiveItemId) next[key] = String(archiveItemId);
        else delete next[key];
        return next;
      });
    } catch (e) {
      console.error('Failed to set selected manifest asset:', e);
      setError(e.response?.data?.error || e.message || 'Nepodařilo se uložit výběr do manifestu');
    }
  };

  // Visual Assistant (LLM Vision reranking)
  const runVisualAssistant = async () => {
    console.log('🎨 Visual Assistant: Starting...', {
      episodeId,
      archiveStats: archiveStats?.manifest_exists,
      visualAssistantConfig
    });
    
    if (!episodeId) {
      setError('Chybí episode_id');
      console.error('❌ Visual Assistant: Missing episode_id');
      return;
    }
    
    setVisualAssistantRunning(true);
    setError('');
    
    try {
      const payload = {
        model: visualAssistantConfig.model,
        temperature: visualAssistantConfig.temperature,
        custom_prompt: visualAssistantConfig.prompt_template || null,
        max_analyze_per_beat: 5
      };
      
      console.log('🎨 Visual Assistant: Sending request...', payload);
      
      const res = await axios.post(
        `/api/video/visual-assistant/${episodeId}`,
        payload,
        { timeout: 600000 } // 10 min timeout (Vision API může být pomalé)
      );
      
      console.log('✅ Visual Assistant: Response received', res.data);
      
      if (res.data?.success) {
        setVisualAssistantResults(res.data);
        setShowBeforeAfter(true);
        
        // Reload candidates to show reranked results
        await loadVisualCandidates();
      } else {
        setError(res.data?.error || 'Visual Assistant selhal');
        console.error('❌ Visual Assistant: Request failed', res.data);
      }
    } catch (e) {
      console.error('❌ Visual Assistant error:', e);
      console.error('Error details:', {
        message: e.message,
        response: e.response?.data,
        status: e.response?.status
      });
      setError(e.response?.data?.error || e.message || 'Visual Assistant selhal');
    } finally {
      setVisualAssistantRunning(false);
      console.log('🎨 Visual Assistant: Finished');
    }
  };

  // TTS Voice-over generation
  const generateVoiceOver = async () => {
    if (!scriptState?.tts_ready_package) {
      setError('Nejprve vygenerujte scénář s TTS formátováním');
      return;
    }
    if (!episodeId) {
      setError('Chybí episode_id – nejdřív vytvořte/načtěte projekt');
      return;
    }

    setTtsState({
      status: 'generating',
      progress: 0,
      currentBlock: 0,
      totalBlocks: getTtsBlockCount(scriptState.tts_ready_package),
      generatedFiles: [],
      error: null
    });
    setError('');

    try {
      console.log('🎙️ Starting TTS generation...');
      
      const response = await axios.post('/api/tts/generate', {
        episode_id: episodeId,
        tts_ready_package: scriptState.tts_ready_package
      }, {
        timeout: 1800000 // 30 minut pro velké projekty
      });

      console.log('🎙️ TTS Response:', response.data);

      if (response.data.success) {
        setTtsState({
          status: 'done',
          progress: 100,
          currentBlock: response.data.total_blocks || 0,
          totalBlocks: response.data.total_blocks || 0,
          // Prefer structured info if available; fallback to filenames
          generatedFiles: response.data.generated_files_info || response.data.generated_files || [],
          error: null
        });
        // Persisted files are stored server-side → refresh state to be reload-safe
        try {
          await refreshState(episodeId);
        } catch (e) {
          // ignore; UI already updated
        }
      } else {
        throw new Error(response.data.error || 'TTS generování selhalo');
      }
    } catch (err) {
      console.error('❌ TTS Error:', err);
      const errorMsg = err.response?.data?.error || err.message || 'Neznámá chyba při TTS generování';
      setTtsState(prev => ({
        ...prev,
        status: 'error',
        error: errorMsg
      }));
      setError(errorMsg);
    }
  };

  const fetchState = async (epId) => {
    const res = await axios.get(`/api/script/state/${epId}`, { timeout: 30000 });
    if (!res.data?.success) {
      throw new Error(res.data?.error || 'Nepodařilo se načíst script state');
    }
    return res.data.data;
  };

  const refreshState = async (epId) => {
    const state = await fetchState(epId);
    setScriptState(state);
    // Best-effort: load persisted user query overrides
    try {
      await loadSearchQueries(epId);
    } catch (e) {
      // ignore
    }
    // Best-effort: load archive stats if manifest exists
    try {
      await loadArchiveStats();
    } catch (e) {
      // ignore
    }
    
    // Hydratace TTS stavu z uložených dat
    // IMPORTANT: allow hydration even when script_status === 'ERROR' (voiceover can still exist and should unlock compilation/retry)
    if (state?.tts_ready_package) {
      // Zkontroluj, jestli existují MP3 soubory
      try {
        const projectsRes = await axios.get(`/api/projects/${epId}`, { timeout: 10000 });
        const mp3Files = projectsRes.data?.mp3_files || [];
        
        if (mp3Files.length > 0) {
          // MP3 soubory existují → TTS je hotovo
          setTtsState({
            status: 'done',
            progress: 100,
            currentBlock: mp3Files.length,
            totalBlocks: getTtsBlockCount(state.tts_ready_package),
            generatedFiles: mp3Files,
            error: null
          });
        } else {
          // MP3 neexistují → TTS ještě nebylo spuštěno
          setTtsState({
            status: 'idle',
            progress: 0,
            currentBlock: 0,
            totalBlocks: getTtsBlockCount(state.tts_ready_package),
            generatedFiles: [],
            error: null
          });
        }
      } catch (e) {
        console.warn('⚠️ Nepodařilo se načíst MP3 soubory:', e);
        // Fallback: předpokládej, že TTS ještě nebylo spuštěno
        setTtsState({
          status: 'idle',
          progress: 0,
          currentBlock: 0,
          totalBlocks: getTtsBlockCount(state.tts_ready_package),
          generatedFiles: [],
          error: null
        });
      }
    }
    
    // Hydratace video compilation stavu
    if (state?.compilation_video_path) {
      const filename = state.compilation_video_path.split('/').pop();
      const videoUrl = `http://localhost:50000/api/video/stream/${filename}`;
      
      setVideoCompilationState({
        status: 'done',
        progress: 100,
        currentStep: 'Complete!',
        error: null,
        outputPath: videoUrl,
      });
    }
    
    return state;
  };

  const startPolling = (epId) => {
    stopPolling();
    // Throttle expensive query reloads while pipeline is running.
    let lastQueriesReloadAt = 0;
    pollRef.current = setInterval(async () => {
      try {
        const state = await fetchState(epId);
        setScriptState(state);

        // IMPORTANT: While pipeline is RUNNING, queries may appear later (after FDA or after AAR writes manifest).
        // Refreshing script_state alone is not enough — we must reload /api/video/search-queries to update UI.
        const fdaDone =
          (state?.steps?.footage_director?.status || '').toString().toUpperCase() === 'DONE';
        const hasEpisodePoolQueries = Array.isArray(episodePoolQueries) && episodePoolQueries.length > 0;
        const now = Date.now();
        if (!hasEpisodePoolQueries && fdaDone && now - lastQueriesReloadAt > 4000) {
          lastQueriesReloadAt = now;
          try {
            await loadSearchQueries(epId);
          } catch (e) {
            // handled inside loadSearchQueries
          }
        }

        if (state?.script_status === 'DONE' || state?.script_status === 'ERROR') {
          stopPolling();
        }
      } catch (e) {
        // keep polling; show last error
        setError(e.message || 'Chyba při polling script state');
      }
    }, 1200);
  };

  // Reload-safe hydration
  useEffect(() => {
    let cancelled = false;

    const hydrate = async () => {
      if (!episodeId) return;
      try {
        const state = await refreshState(episodeId);
        if (cancelled) return;
        if (state?.script_status?.startsWith('RUNNING_')) {
          startPolling(episodeId);
        }
      } catch (e) {
        if (cancelled) return;
        setError(e.message || 'Chyba při hydrataci');
      }
    };

    hydrate();
    return () => {
      cancelled = true;
      stopPolling();
      stopVideoPolling();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [episodeId]);

  // Removed per-episode music loading (now using global library)

  const normalizeDefaultsForApi = () => ({
    research: {
      provider: researchConfig.provider,
      model: researchConfig.model,
      temperature: researchConfig.temperature,
      prompt_template: researchConfig.prompt_template?.trim() ? researchConfig.prompt_template : null
    },
    narrative: {
      provider: narrativeConfig.provider,
      model: narrativeConfig.model,
      temperature: narrativeConfig.temperature,
      prompt_template: narrativeConfig.prompt_template?.trim() ? narrativeConfig.prompt_template : null
    },
    validation: {
      provider: validatorConfig.provider,
      model: validatorConfig.model,
      temperature: validatorConfig.temperature,
      prompt_template: validatorConfig.prompt_template?.trim() ? validatorConfig.prompt_template : null
    },
    tts_format: {
      provider: ttsFormatConfig.provider,
      model: ttsFormatConfig.model,
      temperature: ttsFormatConfig.temperature,
      prompt_template: ttsFormatConfig.prompt_template?.trim() ? ttsFormatConfig.prompt_template : null
    },
    footage_director: {
      provider: fdaConfig.provider,
      model: fdaConfig.model,
      temperature: fdaConfig.temperature,
      prompt_template: fdaConfig.prompt_template?.trim() ? fdaConfig.prompt_template : null
    },
    visual_assistant: {
      provider: visualAssistantConfig.provider,
      model: visualAssistantConfig.model,
      temperature: visualAssistantConfig.temperature,
      prompt_template: visualAssistantConfig.prompt_template?.trim() ? visualAssistantConfig.prompt_template : null
    }
  });

  const applyDefaultsToUi = (defaults) => {
    const r = defaults?.research || {};
    const n = defaults?.narrative || {};
    const v = defaults?.validation || {};
    const t = defaults?.tts_format || {};
    const f = defaults?.footage_director || {};
    const va = defaults?.visual_assistant || {};

    setResearchConfig({
      provider: r.provider || 'openai',
      model: r.model || 'gpt-4o',
      temperature: typeof r.temperature === 'number' ? r.temperature : 0.4,
      prompt_template: r.prompt_template || ''
    });
    setNarrativeConfig({
      provider: n.provider || 'openai',
      model: n.model || 'gpt-4o',
      temperature: typeof n.temperature === 'number' ? n.temperature : 0.4,
      prompt_template: n.prompt_template || ''
    });
    setValidatorConfig({
      provider: v.provider || 'openai',
      model: v.model || 'gpt-4o',
      temperature: typeof v.temperature === 'number' ? v.temperature : 0.4,
      prompt_template: v.prompt_template || ''
    });
    setTtsFormatConfig({
      provider: t.provider || 'openai',
      model: t.model || 'gpt-4o',
      temperature: typeof t.temperature === 'number' ? t.temperature : 0.4,
      prompt_template: t.prompt_template || ''
    });
    setFdaConfig({
      provider: f.provider || 'openai',
      model: f.model || 'gpt-4o-mini',
      temperature: typeof f.temperature === 'number' ? f.temperature : 0.2,
      prompt_template: f.prompt_template || ''
    });
    setVisualAssistantConfig({
      provider: va.provider || 'openai',
      model: va.model || 'gpt-4o',
      temperature: typeof va.temperature === 'number' ? va.temperature : 0.3,
      prompt_template: va.prompt_template || ''
    });
  };

  const loadDefaults = async () => {
    setIsLoadingDefaults(true);
    setError('');
    try {
      const res = await axios.get('/api/settings/llm_defaults', { timeout: 30000 });
      if (!res.data?.success) throw new Error(res.data?.error || 'Nepodařilo se načíst defaults');
      const defaults = res.data.data;
      applyDefaultsToUi(defaults);
      const snapshot = {
        research: defaults?.research || {},
        narrative: defaults?.narrative || {},
        validation: defaults?.validation || {},
        tts_format: defaults?.tts_format || {},
        footage_director: defaults?.footage_director || {},
        visual_assistant: defaults?.visual_assistant || {}
      };
      setDefaultsSnapshot(snapshot);
      setDefaultsStatus('Saved ✓');
    } catch (e) {
      setError(e.message || 'Chyba při načítání defaults');
    } finally {
      setIsLoadingDefaults(false);
    }
  };

  const saveDefaults = async () => {
    setIsSavingDefaults(true);
    setError('');
    try {
      const payload = normalizeDefaultsForApi();
      const res = await axios.post('/api/settings/llm_defaults', payload, { timeout: 30000 });
      if (!res.data?.success) throw new Error(res.data?.error || 'Nepodařilo se uložit defaults');
      // snapshot becomes the persisted defaults
      setDefaultsSnapshot(payload);
      setDefaultsStatus('Saved ✓');
    } catch (e) {
      setError(e.message || 'Chyba při ukládání defaults');
    } finally {
      setIsSavingDefaults(false);
    }
  };

  const resetPromptTemplates = () => {
    setResearchConfig((p) => ({ ...p, prompt_template: '' }));
    setNarrativeConfig((p) => ({ ...p, prompt_template: '' }));
    setValidatorConfig((p) => ({ ...p, prompt_template: '' }));
    setTtsFormatConfig((p) => ({ ...p, prompt_template: '' }));
    setFdaConfig((p) => ({ ...p, prompt_template: '' }));
    setVisualAssistantConfig((p) => ({ ...p, prompt_template: '' }));
  };

  // Load defaults + OpenAI server-side status on first mount
  useEffect(() => {
    let cancelled = false;
    const boot = async () => {
      try {
        const statusRes = await axios.get('/api/settings/openai_status', { timeout: 20000 });
        if (!cancelled && statusRes.data?.success) {
          setOpenaiConfigured(!!statusRes.data.configured);
        }
      } catch (e) {
        if (!cancelled) setOpenaiConfigured(false);
      }
      try {
        const statusRes = await axios.get('/api/settings/openrouter_status', { timeout: 20000 });
        if (!cancelled && statusRes.data?.success) {
          setOpenrouterConfigured(!!statusRes.data.configured);
        }
      } catch (e) {
        if (!cancelled) setOpenrouterConfigured(false);
      }
      await loadDefaults();
    };
    boot();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Dirty flag: compare current UI configs vs defaultsSnapshot
  useEffect(() => {
    if (!defaultsSnapshot) return;
    const current = normalizeDefaultsForApi();
    const same = JSON.stringify(current) === JSON.stringify(defaultsSnapshot);
    setDefaultsStatus(same ? 'Saved ✓' : 'Unsaved changes');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [researchConfig, narrativeConfig, validatorConfig, defaultsSnapshot]);

  const onGenerateScript = async () => {
    setError('');
    if (!topic.trim()) {
      setError('Zadejte téma');
      return;
    }
    const neededProviders = new Set([
      (researchConfig.provider || 'openai').toLowerCase(),
      (narrativeConfig.provider || 'openai').toLowerCase(),
      (validatorConfig.provider || 'openai').toLowerCase(),
      (ttsFormatConfig.provider || 'openai').toLowerCase()
    ]);
    if (neededProviders.has('openrouter') && !openrouterConfigured) {
      setError('OpenRouter API klíč není nastaven na serveru');
      return;
    }
    if (neededProviders.has('openai') && !openaiConfigured) {
      setError('OpenAI API klíč není nastaven na serveru');
      return;
    }

    setIsStarting(true);
    stopPolling();

    try {
      const res = await axios.post(
        '/api/script/generate',
        {
          topic: topic.trim(),
          language,
          target_minutes: targetMinutes,
          channel_profile: channelProfile,
          research_config: normalizeDefaultsForApi().research,
          narrative_config: normalizeDefaultsForApi().narrative,
          validator_config: normalizeDefaultsForApi().validation,
          tts_format_config: normalizeDefaultsForApi().tts_format,
          footage_director_config: normalizeDefaultsForApi().footage_director
        },
        { timeout: 60000 }
      );

      if (!res.data?.success) {
        throw new Error(res.data?.error || 'Nepodařilo se spustit script pipeline');
      }

      const epId = res.data.episode_id;
      setEpisodeId(epId);
      try {
        localStorage.setItem(EPISODE_STORAGE_KEY, epId);
      } catch (e) {
        // ignore
      }

      await refreshState(epId);
      startPolling(epId);
    } catch (e) {
      setError(e.message || 'Chyba při spuštění');
    } finally {
      setIsStarting(false);
    }
  };

  const onRetryStep = async (stepKey) => {
    if (!episodeId) return;
    setError('');
    try {
      const res = await axios.post(
        '/api/script/retry-step',
        { episode_id: episodeId, step: stepKey },
        { timeout: 10000 }
      );
      if (!res.data?.success) {
        throw new Error(res.data?.error || 'Retry selhal');
      }
      await refreshState(episodeId);
      startPolling(episodeId);
    } catch (e) {
      setError(e.message || 'Chyba při retry');
    }
  };

  const onRetryWritingApplyPatch = async () => {
    if (!episodeId) return;
    setError('');
    try {
      const res = await axios.post(`/api/script/retry/narrative/${episodeId}`, {}, { timeout: 10000 });
      if (!res.data?.success) throw new Error(res.data?.error || 'Retry writing selhal');
      await refreshState(episodeId);
      startPolling(episodeId);
    } catch (e) {
      setError(e.message || 'Chyba při retry writing');
    }
  };

  const onRetryValidationOnly = async () => {
    if (!episodeId) return;
    setError('');
    try {
      const res = await axios.post(`/api/script/retry/validation/${episodeId}`, {}, { timeout: 10000 });
      if (!res.data?.success) throw new Error(res.data?.error || 'Retry validation selhal');
      await refreshState(episodeId);
      startPolling(episodeId);
    } catch (e) {
      setError(e.message || 'Chyba při retry validation');
    }
  };

  const steps = scriptState?.steps || {};
  const scriptStatus = scriptState?.script_status || 'IDLE';
  const isRunning = scriptStatus.startsWith('RUNNING_') || isStarting;
  const factChecked = scriptState?.validation_result?.status === 'PASS';
  const pipelineWarnings = Array.isArray(scriptState?.pipeline_warnings) ? scriptState.pipeline_warnings : [];
  const stepWarningsCount = Object.values(steps || {}).reduce((acc, st) => {
    const w = st?.warnings;
    return acc + (Array.isArray(w) ? w.length : 0);
  }, 0);
  const warningsCount = Math.max(pipelineWarnings.length, stepWarningsCount);
  const scriptStatusLabel = (scriptStatus === 'DONE' && warningsCount > 0)
    ? `DONE + WARNINGS (${warningsCount})`
    : scriptStatus;

  const getStepConfigMeta = (key) => {
    // Returns { provider, model } if known
    if (!scriptState) return null;
    if (key === 'research') return scriptState?.research_config || null;
    if (key === 'narrative') return scriptState?.narrative_config || null;
    if (key === 'validation') return scriptState?.validator_config || null;
    if (key === 'tts_format') return scriptState?.tts_format_config || null;
    if (key === 'footage_director') return scriptState?.footage_director_config || null;
    return null;
  };

  const getRawForStepKey = (key) => {
    if (!scriptState) return null;
    if (key === 'research') return scriptState?.research_raw_output || null;
    if (key === 'narrative') return scriptState?.narrative_raw_output || null;
    if (key === 'validation') return scriptState?.validation_raw_output || null;
    if (key === 'composer') return scriptState?.script_package || null;
    if (key === 'tts_format') return scriptState?.tts_format_raw_output || null;
    if (key === 'footage_director') return scriptState?.shot_plan || null;
    // fallback: show full state slice if unknown key
    return { step: key, step_state: steps?.[key] || null };
  };

  const openRawForStep = (label, key) => {
    const data = getRawForStepKey(key);
    setRawModal({
      open: true,
      title: `Raw output: ${label}`,
      data
    });
  };

  const copyAllRawOutputs = async () => {
    if (!scriptState) {
      setError('Žádný script state k exportu');
      return;
    }

    const allSteps = [
      'research', 'narrative', 'validation', 'composer', 'tts_format', 'footage_director',
      'asset_resolver', 'compilation_builder'
    ];

    const exportData = {
      episode_id: episodeId || null,
      script_status: scriptStatus,
      exported_at: new Date().toISOString(),
      steps: {}
    };

    allSteps.forEach(key => {
      const stepState = steps[key] || null;
      const rawOutput = getRawForStepKey(key);
      const config = getStepConfigMeta(key);
      
      exportData.steps[key] = {
        status: stepState?.status || 'N/A',
        config: config || null,
        error: stepState?.error || null,
        raw_output: rawOutput
      };
    });

    // Add additional metadata
    exportData.metadata = {
      episode_input: scriptState?.episode_input || null,
      validation_result: scriptState?.validation_result || null,
      tts_ready_package: scriptState?.tts_ready_package || null,
      shot_plan: scriptState?.shot_plan || null
    };

    try {
      const jsonString = JSON.stringify(exportData, null, 2);
      await navigator.clipboard.writeText(jsonString);
      setError('');
      // Show success feedback (you could also use a toast)
      const oldError = error;
      setError('✅ Všechny raw outputs zkopírovány do clipboardu!');
      setTimeout(() => setError(oldError), 3000);
    } catch (e) {
      setError('Chyba při kopírování: ' + e.message);
    }
  };

  const errorSteps = Object.entries(steps || {}).filter(([, st]) => (st?.status || '') === 'ERROR');
  const shotPlanScenesCount = (() => {
    const sp = scriptState?.shot_plan;
    if (!sp) return 0;
    if (Array.isArray(sp?.scenes)) return sp.scenes.length;
    if (sp?.shot_plan && Array.isArray(sp.shot_plan?.scenes)) return sp.shot_plan.scenes.length;
    return 0;
  })();
  const hasShotPlan = shotPlanScenesCount > 0;
  const hasVoiceover = (ttsState?.generatedFiles || []).length > 0;
  const canCompile = !!episodeId && hasShotPlan && hasVoiceover;
  const compiledMusicFilename =
    scriptState?.compilation_builder_output?.compilation_report?.music?.selected_track?.filename ||
    scriptState?.compilation_builder_output?.music_report?.selected_track?.filename ||
    null;
  const selectedMusicFilename = selectedGlobalMusic?.filename || null;
  const needsMusicRemix = !!videoCompilationState.outputPath && !!selectedMusicFilename && selectedMusicFilename !== compiledMusicFilename;

  const renderStepRow = (label, key) => {
    const st = steps?.[key];
    const status = st?.status || 'IDLE';
    
    // For validation, show status correctly (DONE is DONE, even if result is FAIL)
    // FAIL result just means Composer won't run, but Validation step itself completed successfully
    const icon =
      status === 'DONE' ? '✅' : status === 'ERROR' ? '❌' : status === 'RUNNING' ? '🔄' : '⏸️';
    const canRaw = status === 'DONE' || status === 'ERROR';
    const canRetry = status === 'ERROR' && ['research', 'narrative', 'validation', 'composer', 'tts_format', 'footage_director'].includes(key);
    const validationFailed = (scriptState?.validation_result?.status === 'FAIL');

    // Retry should be shown only on FAIL/ERROR.
    // - For most steps: only when step status === ERROR
    // - For validation FAIL: dedicated buttons below (writing-apply-patch primary)
    const showRetry = canRetry;
    const validationIssues = (scriptState?.validation_result?.issues || []);
    const firstIssue = validationIssues[0] || null;
    const patchInstructions = scriptState?.validation_result?.patch_instructions || '';
    const narrativeAttempts = (scriptState?.attempts?.narrative ?? 0);
    const canFixWithNarrativeRetry = (validationFailed && narrativeAttempts < 2 && !!patchInstructions);

    const onOpenRaw = () => openRawForStep(label, key);

    return (
      <>
        <div className="flex items-center justify-between py-2 border-b border-gray-100">
          <div className="text-sm text-gray-800">
            {label}
            {key === 'validation' && status === 'DONE' && validationFailed && (
              <span className="ml-2 text-xs text-orange-600">
                (FAIL: {validationIssues.length} issue{validationIssues.length === 1 ? '' : 's'} – needs PASS for Composer)
              </span>
            )}
            {key === 'composer' && status === 'IDLE' && validationFailed && steps?.validation?.status === 'DONE' && (
              <span className="ml-2 text-xs text-gray-500">(blocked by Validation FAIL)</span>
            )}
          </div>
          <div className="flex items-center gap-2">
          {key === 'validation' && status === 'DONE' && validationFailed && (
            <>
              <button
                onClick={onRetryWritingApplyPatch}
                disabled={!canFixWithNarrativeRetry || isRunning}
                className={`px-2 py-1 rounded text-xs border transition-colors ${
                  (!canFixWithNarrativeRetry || isRunning)
                    ? 'bg-gray-100 border-gray-200 text-gray-400 cursor-not-allowed'
                    : 'bg-purple-100 border-purple-300 text-purple-800 hover:bg-purple-200'
                }`}
                title={
                  canFixWithNarrativeRetry
                    ? 'Spustí znovu Writing (apply patch) a pak automaticky Validation → Packaging'
                    : 'Manual fix required (narrative retry budget exhausted)'
                }
              >
                🔁 Retry writing (apply patch)
              </button>
              <button
                onClick={onRetryValidationOnly}
                disabled={isRunning}
                className={`px-2 py-1 rounded text-xs border transition-colors ${
                  isRunning
                    ? 'bg-gray-100 border-gray-200 text-gray-400 cursor-not-allowed'
                    : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
                }`}
                title="Pouze znovu spustí Validation nad aktuálním draft_script (pro debug / po ručních úpravách)"
              >
                🔄 Retry validation
              </button>
            </>
          )}
          {showRetry && (
            <button
              onClick={() => onRetryStep(key)}
              className="px-2 py-1 rounded text-xs bg-orange-100 border border-orange-300 text-orange-800 hover:bg-orange-200 transition-colors"
            >
              🔄 Retry
            </button>
          )}
          <button
            onClick={onOpenRaw}
            disabled={!canRaw}
            className={`px-2 py-1 rounded text-xs border transition-colors ${
              canRaw
                ? 'bg-white border-gray-300 text-gray-800 hover:bg-gray-50'
                : 'bg-gray-100 border-gray-200 text-gray-400 cursor-not-allowed'
            }`}
          >
            Raw output
          </button>
          <div className="text-sm">
            <span className="mr-2">{icon}</span>
            <span className="text-gray-600">{status}</span>
          </div>
          </div>
        </div>
        {key === 'validation' && status === 'DONE' && validationFailed && firstIssue?.message && (
          <div className="pb-2 pl-0">
            <div className="text-xs text-orange-700 mt-1">
              First issue: <span className="font-mono">{firstIssue.issue_id || '—'}</span>{' '}
              {firstIssue.block_id ? `(block ${firstIssue.block_id})` : ''} — {firstIssue.message}
            </div>
            {!canFixWithNarrativeRetry && (
              <div className="text-xs text-orange-700 mt-1">
                <span className="font-semibold">Manual fix required</span> — narrative attempts: {narrativeAttempts}.{' '}
                {patchInstructions ? (
                  <span>Patch: <span className="font-mono">{patchInstructions}</span></span>
                ) : (
                  <span>Patch instructions nejsou k dispozici.</span>
                )}
              </div>
            )}
          </div>
        )}
      </>
    );
  };

  return (
    <div className="bg-white rounded-lg shadow-sm p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-xl font-semibold text-gray-900 flex items-center">
            <span className="w-8 h-8 bg-purple-100 rounded-lg flex items-center justify-center mr-3">
              <span className="text-purple-600 text-lg">📝</span>
            </span>
            Generování textu
          </h3>
          <p className="text-sm text-gray-600">Stabilní pipeline: Research → Writing → Validating → Packaging → TTS → Footage Director</p>
        </div>
        <div className="flex space-x-3">
          <button
            onClick={resetForNewRun}
            className="px-4 py-2 bg-gray-900 text-white rounded-md hover:bg-black transition-colors text-sm"
            title="Vyčistí UI a smaže uložené episode_id (nový běh na čisté stránce)"
          >
            🧹 Nový běh (reset)
          </button>
          {scriptState && (
            <button
              onClick={copyAllRawOutputs}
              className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors text-sm"
              title="Zkopíruje strukturovaný JSON se všemi raw outputs (research, narrative, validation, TTS, FDA, AAR, CB) do clipboardu"
            >
              📋 Kopírovat všechny raw outputs
            </button>
          )}
          <button
            onClick={onOpenApiManagement}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors text-sm"
          >
            🔧 API Management
          </button>
        </div>
      </div>

      {/* Status Bar */}
      <div className="mb-6 p-3 bg-gray-50 border border-gray-200 rounded-lg">
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center space-x-4">
            <div className={`flex items-center ${openaiConfigured ? 'text-green-600' : 'text-red-600'}`}>
              <div className={`w-2 h-2 rounded-full mr-2 ${openaiConfigured ? 'bg-green-500' : 'bg-red-500'}`}></div>
              OpenAI API {openaiConfigured ? 'configured' : 'missing'}
            </div>
            <div className={`flex items-center ${openrouterConfigured ? 'text-green-600' : 'text-red-600'}`}>
              <div className={`w-2 h-2 rounded-full mr-2 ${openrouterConfigured ? 'bg-green-500' : 'bg-red-500'}`}></div>
              OpenRouter API {openrouterConfigured ? 'configured' : 'missing'}
            </div>
            <div className="flex items-center text-gray-600">
              <div className="w-2 h-2 rounded-full mr-2 bg-gray-400"></div>
              episode_id: {episodeId || '—'}
            </div>
          </div>
          <div className="text-gray-600">
            status: <span className="font-medium">{scriptStatus}</span>
          </div>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-red-700 text-sm">❌ {toDisplayString(error)}</p>
        </div>
      )}

      {/* Script ERROR details (show which step + which provider/model + message) */}
      {scriptState && scriptStatus === 'ERROR' && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1">
              <div className="text-sm font-semibold text-red-900 mb-1">
                Pipeline je ve stavu ERROR (episode_id: <span className="font-mono">{episodeId || '—'}</span>)
              </div>
              <div className="text-xs text-red-800">
                Níže jsou konkrétní kroky s chybou. Klikněte na <span className="font-medium">Raw output</span> u daného kroku (v sekci Průběh) pro detaily.
              </div>
            </div>
            <button
              onClick={() => {
                setRawModal({
                  open: true,
                  title: 'Pipeline ERROR details',
                  data: {
                    episode_id: episodeId,
                    script_status: scriptStatus,
                    steps: steps,
                    episode_input: scriptState?.episode_input || null,
                  }
                });
              }}
              className="px-3 py-1.5 rounded text-xs bg-white border border-red-300 text-red-800 hover:bg-red-100 transition-colors"
              title="Zobrazí souhrn všech kroků (status + error) v modalu"
            >
              Zobrazit detail
            </button>
          </div>

          {errorSteps.length > 0 ? (
            <div className="mt-3 space-y-2">
              {errorSteps.map(([key, st]) => {
                const cfg = getStepConfigMeta(key);
                const provider = cfg?.provider || (key === 'asset_resolver' || key === 'compilation_builder' ? 'system' : '—');
                const model = cfg?.model || (key === 'asset_resolver' || key === 'compilation_builder' ? 'internal' : '—');
                const msg = toDisplayString(st?.error) || '—';
                return (
                  <div key={key} className="p-3 bg-white border border-red-200 rounded">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-gray-900">
                          {key} <span className="text-xs text-gray-500">(provider: <span className="font-mono">{provider}</span>, model: <span className="font-mono">{model}</span>)</span>
                        </div>
                        <div className="text-xs text-red-800 mt-1 break-words">
                          error: <span className="font-mono">{msg}</span>
                        </div>
                      </div>
                      <button
                        onClick={() => openRawForStep(key, key)}
                        className="px-2 py-1 rounded text-xs bg-white border border-gray-300 text-gray-800 hover:bg-gray-50"
                        title="Otevřít raw output pro tento krok"
                      >
                        Raw output
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="mt-3 text-xs text-red-800">
              Nemám v `steps` žádný krok se stavem ERROR — to obvykle znamená, že ERROR status je globální. Klikněte na „Zobrazit detail“.
            </div>
          )}
        </div>
      )}

      {/* Form */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div className="md:col-span-2">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Téma *
          </label>
          <textarea
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Např. Nikola Tesla a válka proudů"
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Jazyk
          </label>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
          >
            <option value="cs">Čeština (cs)</option>
            <option value="en">English (en)</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Cílová délka (minuty)
          </label>
          <input
            type="number"
            value={targetMinutes}
            onChange={(e) => setTargetMinutes(parseInt(e.target.value || '0', 10))}
            min="1"
            max="120"
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
          />
        </div>

        <div className="md:col-span-2">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Channel profile
          </label>
          <input
            type="text"
            value={channelProfile}
            onChange={(e) => setChannelProfile(e.target.value)}
            placeholder="default"
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
          />
        </div>
      </div>

      {/* Advanced per-step configs */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <button
            onClick={() => setShowAdvanced((v) => !v)}
            className="text-sm text-purple-700 hover:text-purple-900"
          >
            {showAdvanced ? 'Skrýt' : 'Zobrazit'} pokročilé nastavení (Pipeline kroky 1–7)
          </button>
          {defaultsStatus && (
            <div className={`text-sm ${defaultsStatus === 'Saved ✓' ? 'text-green-700' : 'text-amber-700'}`}>
              {defaultsStatus}
            </div>
          )}
        </div>

        {showAdvanced && (
          <div className="mt-3 p-4 bg-gray-50 border border-gray-200 rounded-lg space-y-6">
            {/* Defaults actions */}
            <div className="flex flex-wrap gap-2 items-center justify-between">
              <div className="flex gap-2">
                <button
                  onClick={saveDefaults}
                  disabled={isSavingDefaults}
                  className={`px-3 py-2 rounded-md text-sm text-white ${
                    isSavingDefaults ? 'bg-gray-400 cursor-not-allowed' : 'bg-green-600 hover:bg-green-700'
                  }`}
                >
                  Save defaults
                </button>
                <button
                  onClick={loadDefaults}
                  disabled={isLoadingDefaults}
                  className={`px-3 py-2 rounded-md text-sm text-white ${
                    isLoadingDefaults ? 'bg-gray-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700'
                  }`}
                >
                  Load defaults
                </button>
                <button
                  onClick={resetPromptTemplates}
                  className="px-3 py-2 rounded-md text-sm bg-white border border-gray-300 text-gray-800 hover:bg-gray-50"
                >
                  Reset templates
                </button>
              </div>
            </div>

            {/* Used for this episode (read-only) */}
            {episodeId && scriptState && (
              <div className="bg-white border border-gray-200 rounded p-3">
                <div className="text-sm font-semibold text-gray-800 mb-2">Config used in this run (episode)</div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                  <div className="p-2 bg-gray-50 border border-gray-200 rounded">
                    <div className="text-xs text-gray-500 mb-1">1. Research</div>
                    <div className="font-mono text-xs">
                      provider: {scriptState?.research_config?.provider || '—'}<br />
                      model: {scriptState?.research_config?.model || '—'}<br />
                      temp: {scriptState?.research_config?.temperature ?? '—'}<br />
                      template: {scriptState?.research_config?.prompt_template ? 'custom' : 'default'}
                    </div>
                  </div>
                  <div className="p-2 bg-gray-50 border border-gray-200 rounded">
                    <div className="text-xs text-gray-500 mb-1">2. Narrative</div>
                    <div className="font-mono text-xs">
                      provider: {scriptState?.narrative_config?.provider || '—'}<br />
                      model: {scriptState?.narrative_config?.model || '—'}<br />
                      temp: {scriptState?.narrative_config?.temperature ?? '—'}<br />
                      template: {scriptState?.narrative_config?.prompt_template ? 'custom' : 'default'}
                    </div>
                  </div>
                  <div className="p-2 bg-gray-50 border border-gray-200 rounded">
                    <div className="text-xs text-gray-500 mb-1">3. Validation</div>
                    <div className="font-mono text-xs">
                      provider: {scriptState?.validator_config?.provider || '—'}<br />
                      model: {scriptState?.validator_config?.model || '—'}<br />
                      temp: {scriptState?.validator_config?.temperature ?? '—'}<br />
                      template: {scriptState?.validator_config?.prompt_template ? 'custom' : 'default'}
                    </div>
                  </div>
                  <div className="p-2 bg-gray-50 border border-gray-200 rounded">
                    <div className="text-xs text-gray-500 mb-1">5. TTS Format</div>
                    <div className="font-mono text-xs">
                      provider: {scriptState?.tts_format_config?.provider || '—'}<br />
                      model: {scriptState?.tts_format_config?.model || '—'}<br />
                      temp: {scriptState?.tts_format_config?.temperature ?? '—'}<br />
                      template: {scriptState?.tts_format_config?.prompt_template ? 'custom' : 'default'}
                    </div>
                  </div>
                  <div className="p-2 bg-gray-50 border border-gray-200 rounded">
                    <div className="text-xs text-gray-500 mb-1">6. Footage Director</div>
                    <div className="font-mono text-xs">
                      provider: {scriptState?.footage_director_config?.provider || '—'}<br />
                      model: {scriptState?.footage_director_config?.model || '—'}<br />
                      temp: {scriptState?.footage_director_config?.temperature ?? '—'}<br />
                      template: {scriptState?.footage_director_config?.prompt_template ? 'custom' : 'default'}
                    </div>
                  </div>
                  <div className="p-2 bg-purple-50 border border-purple-200 rounded">
                    <div className="text-xs text-purple-600 font-medium mb-1">✨ 7. Visual Assistant</div>
                    <div className="font-mono text-xs">
                      provider: {scriptState?.visual_assistant_config?.provider || '—'}<br />
                      model: {scriptState?.visual_assistant_config?.model || '—'}<br />
                      temp: {scriptState?.visual_assistant_config?.temperature ?? '—'}<br />
                      template: {scriptState?.visual_assistant_config?.prompt_template ? 'custom' : 'default'}
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div className="text-xs text-gray-600">
              Prompt template placeholders:
              <div className="mt-1 font-mono text-[11px] text-gray-700">
                Research: {'{topic} {language} {target_minutes} {channel_profile}'}<br />
                Narrative: {'{research_report_json} {channel_profile} {patch_instructions}'}<br />
                Validation: {'{research_report_json} {draft_script_json}'}
              </div>
            </div>

            {/* Research */}
            <div className="bg-white border border-gray-200 rounded p-3">
              <div className="text-sm font-semibold text-gray-800 mb-3">1) Research (LLM)</div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Provider</label>
                  <select
                    value={researchConfig.provider}
                    onChange={(e) => setResearchConfig((p) => ({ ...p, provider: e.target.value }))}
                    className="w-full px-2 py-2 border border-gray-300 rounded-md text-sm"
                  >
                    <option value="openai">openai</option>
                    <option value="openrouter">openrouter</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Model</label>
                  <ModelField
                    value={researchConfig.model}
                    onChange={(model) => setResearchConfig((p) => ({ ...p, model }))}
                    disabled={false}
                    provider={researchConfig.provider}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Temperature</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="2"
                    value={researchConfig.temperature}
                    onChange={(e) => setResearchConfig((p) => ({ ...p, temperature: parseFloat(e.target.value) }))}
                    className="w-full px-2 py-2 border border-gray-300 rounded-md text-sm"
                  />
                </div>
                <div className="md:col-span-3">
                  <label className="block text-xs text-gray-600 mb-1">Prompt template (optional)</label>
                  <textarea
                    value={researchConfig.prompt_template}
                    onChange={(e) => setResearchConfig((p) => ({ ...p, prompt_template: e.target.value }))}
                    rows={6}
                    className="w-full px-2 py-2 border border-gray-300 rounded-md text-sm font-mono"
                    placeholder="(ponech prázdné = použije se default prompt)"
                  />
                </div>
              </div>
            </div>

            {/* Narrative */}
            <div className="bg-white border border-gray-200 rounded p-3">
              <div className="text-sm font-semibold text-gray-800 mb-3">2) Writing / Narrative (LLM)</div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Provider</label>
                  <select
                    value={narrativeConfig.provider}
                    onChange={(e) => setNarrativeConfig((p) => ({ ...p, provider: e.target.value }))}
                    className="w-full px-2 py-2 border border-gray-300 rounded-md text-sm"
                  >
                    <option value="openai">openai</option>
                    <option value="openrouter">openrouter</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Model</label>
                  <ModelField
                    value={narrativeConfig.model}
                    onChange={(model) => setNarrativeConfig((p) => ({ ...p, model }))}
                    disabled={false}
                    provider={narrativeConfig.provider}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Temperature</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="2"
                    value={narrativeConfig.temperature}
                    onChange={(e) => setNarrativeConfig((p) => ({ ...p, temperature: parseFloat(e.target.value) }))}
                    className="w-full px-2 py-2 border border-gray-300 rounded-md text-sm"
                  />
                </div>
                <div className="md:col-span-3">
                  <label className="block text-xs text-gray-600 mb-1">Prompt template (optional)</label>
                  <textarea
                    value={narrativeConfig.prompt_template}
                    onChange={(e) => setNarrativeConfig((p) => ({ ...p, prompt_template: e.target.value }))}
                    rows={6}
                    className="w-full px-2 py-2 border border-gray-300 rounded-md text-sm font-mono"
                    placeholder="(ponech prázdné = použije se default prompt)"
                  />
                </div>
              </div>
            </div>

            {/* Validator */}
            <div className="bg-white border border-gray-200 rounded p-3">
              <div className="text-sm font-semibold text-gray-800 mb-3">3) Fact Validation (LLM)</div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Provider</label>
                  <select
                    value={validatorConfig.provider}
                    onChange={(e) => setValidatorConfig((p) => ({ ...p, provider: e.target.value }))}
                    className="w-full px-2 py-2 border border-gray-300 rounded-md text-sm"
                  >
                    <option value="openai">openai</option>
                    <option value="openrouter">openrouter</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Model</label>
                  <ModelField
                    value={validatorConfig.model}
                    onChange={(model) => setValidatorConfig((p) => ({ ...p, model }))}
                    disabled={false}
                    provider={validatorConfig.provider}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Temperature</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="2"
                    value={validatorConfig.temperature}
                    onChange={(e) => setValidatorConfig((p) => ({ ...p, temperature: parseFloat(e.target.value) }))}
                    className="w-full px-2 py-2 border border-gray-300 rounded-md text-sm"
                  />
                </div>
                <div className="md:col-span-3">
                  <label className="block text-xs text-gray-600 mb-1">Prompt template (optional)</label>
                  <textarea
                    value={validatorConfig.prompt_template}
                    onChange={(e) => setValidatorConfig((p) => ({ ...p, prompt_template: e.target.value }))}
                    rows={6}
                    className="w-full px-2 py-2 border border-gray-300 rounded-md text-sm font-mono"
                    placeholder="(ponech prázdné = použije se default prompt)"
                  />
                </div>
              </div>
            </div>

            {/* TTS Formatting */}
            <div className="bg-white border border-gray-200 rounded p-3">
              <div className="text-sm font-semibold text-gray-800 mb-3">5) TTS Formatting (LLM)</div>
              <div className="text-xs text-gray-500 mb-3">Formátuje hotový scénář pro TTS (pauzy, intonace). Nepřepisuje obsah.</div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Provider</label>
                  <select
                    value={ttsFormatConfig.provider}
                    onChange={(e) => setTtsFormatConfig((p) => ({ ...p, provider: e.target.value }))}
                    className="w-full px-2 py-2 border border-gray-300 rounded-md text-sm"
                  >
                    <option value="openai">openai</option>
                    <option value="openrouter">openrouter</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Model</label>
                  <ModelField
                    value={ttsFormatConfig.model}
                    onChange={(model) => setTtsFormatConfig((p) => ({ ...p, model }))}
                    disabled={false}
                    provider={ttsFormatConfig.provider}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Temperature</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="2"
                    value={ttsFormatConfig.temperature}
                    onChange={(e) => setTtsFormatConfig((p) => ({ ...p, temperature: parseFloat(e.target.value) }))}
                    className="w-full px-2 py-2 border border-gray-300 rounded-md text-sm"
                  />
                </div>
                <div className="md:col-span-3">
                  <label className="block text-xs text-gray-600 mb-1">Prompt template (optional)</label>
                  <textarea
                    value={ttsFormatConfig.prompt_template}
                    onChange={(e) => setTtsFormatConfig((p) => ({ ...p, prompt_template: e.target.value }))}
                    rows={6}
                    className="w-full px-2 py-2 border border-gray-300 rounded-md text-sm font-mono"
                    placeholder="(ponech prázdné = použije se default prompt)"
                  />
                </div>
              </div>
            </div>

            {/* Footage Director Assistant (FDA) */}
            <div className="bg-white border border-gray-200 rounded p-3">
              <div className="text-sm font-semibold text-gray-800 mb-3">6) Footage Director (LLM-assisted)</div>
              <div className="text-xs text-gray-500 mb-3">
                LLM asistent který generuje shot_plan (scény, keywords, shot_types) ze tts_ready_package. 
                Používá LLM pro kreativní rozhodnutí + deterministickou validaci allowlistů.
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Provider</label>
                  <select
                    value={fdaConfig.provider}
                    onChange={(e) => setFdaConfig((p) => ({ ...p, provider: e.target.value }))}
                    className="w-full px-2 py-2 border border-gray-300 rounded-md text-sm"
                  >
                    <option value="openai">openai</option>
                    <option value="openrouter">openrouter</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Model</label>
                  <ModelField
                    value={fdaConfig.model}
                    onChange={(model) => setFdaConfig((p) => ({ ...p, model }))}
                    disabled={false}
                    provider={fdaConfig.provider}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Temperature</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="2"
                    value={fdaConfig.temperature}
                    onChange={(e) => setFdaConfig((p) => ({ ...p, temperature: parseFloat(e.target.value) }))}
                    className="w-full px-2 py-2 border border-gray-300 rounded-md text-sm"
                  />
                </div>
                <div className="md:col-span-3">
                  <label className="block text-xs text-gray-600 mb-1">Prompt template (optional)</label>
                  <textarea
                    value={fdaConfig.prompt_template}
                    onChange={(e) => setFdaConfig((p) => ({ ...p, prompt_template: e.target.value }))}
                    rows={6}
                    className="w-full px-2 py-2 border border-gray-300 rounded-md text-sm font-mono"
                    placeholder="(ponech prázdné = použije se default prompt)"
                  />
                </div>
              </div>
            </div>

            {/* Visual Assistant (LLM Vision) */}
            <div className="bg-white border border-purple-300 rounded p-3">
              <div className="text-sm font-semibold text-gray-800 mb-3">
                ✨ 7) Visual Assistant (LLM Vision) 
                <span className="ml-2 text-xs font-normal text-purple-600 bg-purple-50 px-2 py-0.5 rounded">NOVÝ</span>
              </div>
              <div className="text-xs text-gray-500 mb-3">
                LLM s vision capability analyzuje náhledy kandidátů z archivů a vybírá nejlepší shodu pro každou scénu.
                Detekuje: text v obraze, relevanci k obsahu, kvalitu záznamu.
                Používá se po AAR (Preview Videa) - před kompilací finálního videa.
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Provider</label>
                  <select
                    value={visualAssistantConfig.provider}
                    onChange={(e) => setVisualAssistantConfig((p) => ({ ...p, provider: e.target.value }))}
                    className="w-full px-2 py-2 border border-gray-300 rounded-md text-sm"
                  >
                    <option value="openai">openai</option>
                    <option value="openrouter">openrouter</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Model</label>
                  <ModelField
                    value={visualAssistantConfig.model}
                    onChange={(model) => setVisualAssistantConfig((p) => ({ ...p, model }))}
                    disabled={false}
                    provider={visualAssistantConfig.provider}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Temperature</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="2"
                    value={visualAssistantConfig.temperature}
                    onChange={(e) => setVisualAssistantConfig((p) => ({ ...p, temperature: parseFloat(e.target.value) }))}
                    className="w-full px-2 py-2 border border-gray-300 rounded-md text-sm"
                  />
                </div>
                <div className="md:col-span-3">
                  <label className="block text-xs text-gray-600 mb-1">Prompt template (optional)</label>
                  <textarea
                    value={visualAssistantConfig.prompt_template}
                    onChange={(e) => setVisualAssistantConfig((p) => ({ ...p, prompt_template: e.target.value }))}
                    rows={6}
                    className="w-full px-2 py-2 border border-gray-300 rounded-md text-sm font-mono"
                    placeholder="(ponech prázdné = použije se default prompt pro vision analysis)"
                  />
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Generate Button */}
      <div className="flex justify-center mb-6">
        <button
          onClick={onGenerateScript}
          disabled={!topic.trim() || isRunning}
          className={`px-8 py-3 rounded-lg font-medium text-white transition-colors ${
            !topic.trim() || isRunning
              ? 'bg-gray-400 cursor-not-allowed'
              : 'bg-purple-600 hover:bg-purple-700'
          }`}
        >
          {isRunning ? '🔄 Generuji…' : 'Vygenerovat scénář'}
        </button>
      </div>

      {/* Progress / Steps */}
      <div className="mb-6 p-4 bg-gray-50 border border-gray-200 rounded-lg">
        <div className="flex items-center justify-between mb-3">
          <div className="text-sm font-semibold text-gray-800">Průběh</div>
          <div className="text-xs text-gray-600">
            narrative attempts: <span className="font-medium">{scriptState?.attempts?.narrative ?? 0}</span>
          </div>
        </div>
        {renderStepRow('Research…', 'research')}
        {renderStepRow('Writing…', 'narrative')}
        {renderStepRow('Validating…', 'validation')}
        {renderStepRow('Packaging…', 'composer')}
        {renderStepRow('TTS Formatting…', 'tts_format')}
        {renderStepRow('Footage Director…', 'footage_director')}
      </div>

      {/* Raw output modal */}
      {rawModal.open && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg max-w-4xl w-full max-h-[85vh] overflow-hidden shadow-lg">
            <div className="p-4 border-b border-gray-200 flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-900">{rawModal.title}</div>
              <div className="flex items-center gap-2">
                {rawModal.data && (
                  <>
                    <button
                      onClick={() => {
                        const jsonText = JSON.stringify(rawModal.data.response_json || rawModal.data, null, 2);
                        navigator.clipboard.writeText(jsonText).then(() => {
                          alert('JSON zkopírován do schránky');
                        }).catch(() => {
                          alert('Chyba při kopírování');
                        });
                      }}
                      className="px-3 py-1 text-xs bg-blue-100 border border-blue-300 text-blue-800 rounded hover:bg-blue-200 transition-colors"
                    >
                      📋 Copy JSON
                    </button>
                    <button
                      onClick={() => {
                        const textContent = rawModal.data.response_text || JSON.stringify(rawModal.data, null, 2);
                        navigator.clipboard.writeText(textContent).then(() => {
                          alert('Text zkopírován do schránky');
                        }).catch(() => {
                          alert('Chyba při kopírování');
                        });
                      }}
                      className="px-3 py-1 text-xs bg-green-100 border border-green-300 text-green-800 rounded hover:bg-green-200 transition-colors"
                    >
                      📋 Copy Text
                    </button>
                  </>
                )}
                <button
                  onClick={() => setRawModal({ open: false, title: '', data: null })}
                  className="text-gray-500 hover:text-gray-700 text-xl leading-none"
                >
                  ×
                </button>
              </div>
            </div>
            <div className="p-4 overflow-auto max-h-[75vh]">
              {!rawModal.data ? (
                <div className="text-sm text-gray-600">Žádná raw data k dispozici.</div>
              ) : (
                <div className="space-y-4">
                  {/* If it's a raw_output object */}
                  {rawModal.data?.prompt_used && (
                    <>
                      <div>
                        <div className="text-xs text-gray-500 mb-1">Request metadata</div>
                        <div className="text-sm text-gray-800">
                          provider: <span className="font-mono">{rawModal.data.provider}</span>, model:{' '}
                          <span className="font-mono">{rawModal.data.model}</span>, temperature:{' '}
                          <span className="font-mono">{rawModal.data.temperature}</span>, timestamp:{' '}
                          <span className="font-mono">{rawModal.data.timestamp}</span>
                        </div>
                      </div>
                      {rawModal.data?.provider_meta && (
                        <div>
                          <div className="text-xs text-gray-500 mb-1">Provider meta (debug)</div>
                          <pre className="text-xs bg-gray-50 border border-gray-200 rounded p-3 overflow-auto whitespace-pre-wrap">
                            {JSON.stringify(rawModal.data.provider_meta, null, 2)}
                          </pre>
                        </div>
                      )}
                      <div>
                        <div className="text-xs text-gray-500 mb-1">Prompt template (stored)</div>
                        <pre className="text-xs bg-gray-50 border border-gray-200 rounded p-3 overflow-auto whitespace-pre-wrap">
                          {rawModal.data.prompt_template}
                        </pre>
                      </div>
                      <div>
                        <div className="text-xs text-gray-500 mb-1">Prompt used</div>
                        <pre className="text-xs bg-gray-50 border border-gray-200 rounded p-3 overflow-auto whitespace-pre-wrap">
                          {rawModal.data.prompt_used}
                        </pre>
                      </div>
                      <div>
                        <div className="text-xs text-gray-500 mb-1">Response JSON</div>
                        <pre className="text-xs bg-gray-50 border border-gray-200 rounded p-3 overflow-auto whitespace-pre-wrap">
                          {JSON.stringify(rawModal.data.response_json, null, 2)}
                        </pre>
                      </div>
                      <div>
                        <div className="text-xs text-gray-500 mb-1">Response text</div>
                        <pre className="text-xs bg-gray-50 border border-gray-200 rounded p-3 overflow-auto whitespace-pre-wrap">
                          {rawModal.data.response_text}
                        </pre>
                      </div>
                    </>
                  )}

                  {/* Else fallback: show JSON */}
                  {!rawModal.data?.prompt_used && (
                    <div>
                      <div className="text-xs text-gray-500 mb-1">Data</div>
                      <pre className="text-xs bg-gray-50 border border-gray-200 rounded p-3 overflow-auto whitespace-pre-wrap">
                        {JSON.stringify(rawModal.data, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Result Preview */}
      {scriptState && (scriptState.script_status === 'DONE' || scriptState.script_status === 'ERROR') && (
        <div className="p-4 border border-gray-200 rounded-lg">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <div className="text-sm font-semibold text-gray-800">Preview</div>
              {ttsPkg && (
                <button
                  onClick={() => setShowTtsPreview(!showTtsPreview)}
                  className="px-2 py-1 text-xs bg-blue-100 border border-blue-300 text-blue-800 rounded hover:bg-blue-200 transition-colors"
                >
                  {showTtsPreview ? '📄 Show Script' : '🎤 Show TTS-ready'}
                </button>
              )}
            </div>
            <div>
              {factChecked ? (
                <span className="px-2 py-1 bg-green-100 text-green-800 rounded-full text-xs font-medium">
                  FACT-CHECKED ✅
                </span>
              ) : (
                <span className="px-2 py-1 bg-gray-100 text-gray-700 rounded-full text-xs font-medium">
                  FACT-CHECKED —
                </span>
              )}
            </div>
          </div>

          {showTtsPreview && ttsPkg ? (
            <div>
              <div className="text-xs text-gray-500 mb-3">TTS-ready package (formatted pro voice generation)</div>
              <div className="mb-3">
                <div className="text-xs text-gray-600">
                  Total segments: <span className="font-medium">{ttsPkg?.total_segments || 0}</span>
                  {ttsPkg?.estimated_duration_seconds && (
                    <span className="ml-3">
                      Est. duration: <span className="font-medium">{Math.round(ttsPkg.estimated_duration_seconds / 60)} min</span>
                    </span>
                  )}
                </div>
              </div>
              <div className="space-y-2">
                {(ttsPkg?.tts_segments || []).slice(0, 5).map((seg) => (
                  <div key={seg.segment_id} className="p-3 bg-white border border-gray-200 rounded">
                    <div className="text-xs text-gray-500 mb-1">
                      {seg.segment_id} • pause_before: {seg.pause_before_ms}ms, pause_after: {seg.pause_after_ms}ms
                      {seg.metadata?.speaking_rate && ` • rate: ${seg.metadata.speaking_rate}`}
                    </div>
                    <div className="text-sm text-gray-900 whitespace-pre-wrap mb-2">{seg.text}</div>
                    {seg.tts_formatted_text !== seg.text && (
                      <div className="text-xs text-blue-700 font-mono bg-blue-50 p-2 rounded">
                        TTS: {seg.tts_formatted_text}
                      </div>
                    )}
                  </div>
                ))}
                {(ttsPkg?.tts_segments || []).length > 5 && (
                  <div className="text-xs text-gray-500 text-center">
                    ... a {(ttsPkg?.tts_segments || []).length - 5} dalších segmentů
                  </div>
                )}
              </div>
            </div>
          ) : (
            <>
              {scriptState?.script_package?.selected_title && (
                <div className="mb-3">
                  <div className="text-xs text-gray-500 mb-1">Selected title</div>
                  <div className="text-sm font-medium text-gray-900">{scriptState.script_package.selected_title}</div>
                </div>
              )}

              {scriptState?.draft_script?.hook && (
                <div className="mb-3">
                  <div className="text-xs text-gray-500 mb-1">Hook</div>
                  <div className="text-sm text-gray-900 whitespace-pre-wrap">{scriptState.draft_script.hook}</div>
                </div>
              )}

              {(() => {
                const ch = scriptState?.script_package?.chapters?.[0] || scriptState?.draft_script?.chapters?.[0];
                if (!ch) return null;
                const blocks = ch.narration_blocks || [];
                return (
                  <div>
                    <div className="text-xs text-gray-500 mb-1">1. kapitola</div>
                    <div className="text-sm font-medium text-gray-900 mb-2">{ch.title}</div>
                    <div className="space-y-2">
                      {blocks.slice(0, 3).map((b) => (
                        <div key={b.block_id} className="p-3 bg-white border border-gray-200 rounded">
                          <div className="text-xs text-gray-500 mb-1">
                            {b.block_id} • claim_ids: {(b.claim_ids || []).length}
                          </div>
                          <div className="text-sm text-gray-900 whitespace-pre-wrap">{b.text}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })()}
            </>
          )}
        </div>
      )}

      {/* TTS Voice-over Generation Section */}
      {episodeId && (
        <div className="mt-6 p-4 border border-purple-200 rounded-lg bg-purple-50">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-lg font-semibold text-gray-900">🎙️ Voice-over Generation</h3>
              <p className="text-sm text-gray-600 mt-1">
                Vygenerujte audio soubory z TTS-ready textu pomocí Google Cloud TTS
              </p>
            </div>
          </div>

          {/* Guard: if script isn't ready yet, show why (avoid \"missing section\" UX) */}
          {(!scriptState || !ttsPkg) && (
            <div className="mb-4 p-3 bg-white border border-gray-200 rounded">
              <div className="text-sm font-medium text-gray-900">Ještě není připraven TTS-ready balíček</div>
              <div className="text-xs text-gray-600 mt-1">
                Aktuální status: <span className="font-mono">{scriptStatusLabel || '—'}</span>. Nejdřív dokončete pipeline krok{' '}
                <span className="font-mono">TTS Formatting</span>.
              </div>
            </div>
          )}

          {/* Status Info */}
          {ttsPkg && ttsState.status === 'idle' && (
            <div className="mb-4 p-3 bg-white border border-gray-200 rounded">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium text-gray-900">Ready to generate</div>
                  <div className="text-xs text-gray-600 mt-1">
                    Blocks: <span className="font-medium">{getTtsBlockCount(ttsPkg)}</span>
                    {ttsPkg?.estimated_duration_seconds && (
                      <span className="ml-3">
                        Est. duration: <span className="font-medium">~{Math.round(ttsPkg.estimated_duration_seconds / 60)} min</span>
                      </span>
                    )}
                  </div>
                </div>
                <button
                  onClick={generateVoiceOver}
                  disabled={!ttsPkg || ttsState.status === 'generating'}
                  className="px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors font-medium"
                >
                  🎙️ Vygenerovat Voice-over
                </button>
              </div>
              {scriptState?.script_status === 'ERROR' && (
                <div className="text-xs text-amber-700 mt-2">
                  Poznámka: <span className="font-mono">script_status=ERROR</span>, ale <span className="font-mono">tts_ready_package</span> je k dispozici. Níže (červený box) uvidíte, který krok spadl a proč.
                </div>
              )}
            </div>
          )}

          {/* Generating Progress */}
          {ttsState.status === 'generating' && (
            <div className="mb-4 p-4 bg-white border border-blue-200 rounded">
              <div className="flex items-center justify-between mb-3">
                <div className="text-sm font-medium text-gray-900">🎙️ Generuji audio...</div>
                <div className="text-xs text-gray-600">
                  {ttsState.currentBlock > 0 && `Block ${ttsState.currentBlock}/${ttsState.totalBlocks}`}
                </div>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2.5 mb-2">
                <div 
                  className="bg-blue-600 h-2.5 rounded-full transition-all duration-300" 
                  style={{ width: `${ttsState.progress}%` }}
                ></div>
              </div>
              <div className="text-xs text-gray-600 text-center">
                Prosím počkejte, generování může trvat několik minut...
              </div>
            </div>
          )}

          {/* Error State */}
          {ttsState.status === 'error' && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded">
              <div className="flex items-start gap-3">
                <div className="text-red-600 text-xl">❌</div>
                <div className="flex-1">
                  <div className="text-sm font-medium text-red-900 mb-1">Chyba při generování</div>
                  <div className="text-xs text-red-700">{toDisplayString(ttsState.error)}</div>
                  <button
                    onClick={generateVoiceOver}
                    className="mt-3 px-4 py-1.5 bg-red-600 text-white text-sm rounded hover:bg-red-700 transition-colors"
                  >
                    🔄 Zkusit znovu
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Success - Audio Player */}
          {ttsState.status === 'done' && ttsState.generatedFiles.length > 0 && (
            <div className="space-y-4">
              <div className="p-3 bg-green-50 border border-green-200 rounded">
                <div className="flex items-center gap-2 text-green-800">
                  <span className="text-xl">✅</span>
                  <div>
                    <div className="text-sm font-medium">Voice-over vygenerován!</div>
                    <div className="text-xs mt-0.5">
                      Vytvořeno {ttsState.generatedFiles.length} audio souborů
                      {ttsPkg?.estimated_duration_seconds && (
                        <span className="ml-2">
                          • Celková délka: ~{Math.round(ttsPkg.estimated_duration_seconds / 60)} min
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Audio Files Preview - Collapsible */}
              <div className="bg-white border border-gray-200 rounded-lg">
                {/*
                  generatedFiles může být:
                  - legacy: ["Narrator_0001.mp3", ...]
                  - new: [{ filename, url, size }, ...]
                */}
                {(() => {
                  const audioItems = (ttsState.generatedFiles || []).map((it) => {
                    if (typeof it === 'string') {
                      return { filename: it, url: `/api/download/${it}` };
                    }
                    const fname = it?.filename || it?.name || String(it);
                    const url = it?.url || it?.path || `/api/download/${fname}`;
                    return { filename: fname, url };
                  });

                  const downloadAllHref = '/api/download-all-mp3'; // legacy fallback

                  return (
                    <>
                      <button
                        onClick={() => setShowAudioFiles(!showAudioFiles)}
                        className="w-full p-4 flex items-center justify-between hover:bg-gray-50 transition-colors"
                      >
                        <h4 className="font-medium text-gray-900 flex items-center gap-2">
                          🎵 Vygenerované audio soubory ({ttsState.generatedFiles.length})
                        </h4>
                        <div className="flex items-center gap-3">
                          <a
                            href={downloadAllHref}
                            onClick={(e) => e.stopPropagation()}
                            className="text-sm text-blue-600 hover:text-blue-700"
                          >
                            📥 Stáhnout všechny
                          </a>
                          <span className="text-gray-500">
                            {showAudioFiles ? '▼' : '▶'}
                          </span>
                        </div>
                      </button>

                      {showAudioFiles && (
                        <div className="p-4 pt-0 space-y-3 max-h-96 overflow-y-auto border-t border-gray-200">
                          {audioItems.slice(0, 10).map((item, index) => (
                            <div key={index} className="p-3 border border-gray-200 rounded-lg bg-gray-50">
                              <div className="flex items-center justify-between mb-2">
                                <span className="text-sm font-medium text-gray-900">{item.filename}</span>
                                <a
                                  href={item.url}
                                  download={item.filename}
                                  className="text-blue-600 hover:text-blue-700 text-sm flex items-center gap-1"
                                >
                                  💾 Download
                                </a>
                              </div>
                              <audio
                                controls
                                className="w-full h-8"
                                preload="metadata"
                                style={{ height: '32px' }}
                              >
                                <source src={item.url} type="audio/mpeg" />
                                Váš prohlížeč nepodporuje přehrávání audia.
                              </audio>
                            </div>
                          ))}

                          {ttsState.generatedFiles.length > 10 && (
                            <div className="text-sm text-gray-600 text-center py-2 bg-gray-100 rounded">
                              ... a {ttsState.generatedFiles.length - 10} dalších souborů
                            </div>
                          )}
                        </div>
                      )}
                    </>
                  );
                })()}
              </div>

              {/* Next Steps - Removed old text, moved to Video Compilation section */}
            </div>
          )}
        </div>
      )}
      
      {/* Project Settings: Background Music */}
      {/* Show this BEFORE compilation so users can select/adjust music between TTS and video compilation. */}
      {episodeId && scriptState && (
        <div className="mt-6 p-4 border border-green-200 rounded-lg bg-green-50">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h3 className="text-lg font-semibold text-gray-900">🎵 Background Music</h3>
              <p className="text-sm text-gray-600 mt-1">
                Vyberte hudbu z globální knihovny (nebo ji nechte auto-vybrat). Hudba se přimíchá při kompilaci videa.
              </p>
            </div>
            <button
              onClick={() => setShowMusicLibrary(true)}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors font-medium"
            >
              📚 Otevřít Music Library
            </button>
          </div>

          {/* Background music gain */}
          <div className="mb-3 p-3 border border-gray-200 rounded-lg bg-white">
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-medium text-gray-900">🔊 Hlasitost podkresu</div>
              <div className="text-sm font-mono text-gray-800">{musicBgGainDb} dB</div>
            </div>
            <div className="mt-2">
              <input
                type="range"
                min={-40}
                max={-6}
                step={1}
                value={musicBgGainDb}
                onChange={(e) => {
                  const val = Number(e.target.value);
                  setMusicBgGainDb(val);
                  localStorage.setItem('musicBgGainDb', val);
                }}
                className="w-full"
              />
            </div>
            <div className="mt-1 text-xs text-gray-600">
              Doporučení: -28 až -18 dB. Vyšší hodnota = hlasitější hudba (ale pořád pod voice-overem).
            </div>
          </div>

          {/* Selected/Auto-selected Music Preview */}
          {(selectedGlobalMusic || autoSelectedMusic) && (
            <div className="p-4 border border-gray-200 rounded-lg bg-white">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-sm font-medium text-gray-900">
                      {selectedGlobalMusic ? '✅ Vybraná hudba' : '🤖 Automaticky vybraná hudba'}
                    </span>
                  </div>
                  
                  {(() => {
                    const track = selectedGlobalMusic || autoSelectedMusic;
                    const moodEmojis = {
                      dark: '🌑',
                      uplifting: '✨',
                      dramatic: '⚡',
                      peaceful: '🌊',
                      neutral: '😐'
                    };
                    
                    return (
                      <div>
                        <div className="text-sm text-gray-900 mb-2">
                          {track.original_name || track.filename}
                        </div>
                        
                        <div className="flex flex-wrap gap-1.5 mb-3">
                          <span className="px-2 py-0.5 bg-blue-100 text-blue-800 rounded-full text-xs">
                            {moodEmojis[track.mood] || '😐'} {track.mood}
                          </span>
                          {(track.tags || []).map((tag) => (
                            <span key={tag} className="px-2 py-0.5 bg-purple-100 text-purple-800 rounded-full text-xs">
                              {tag}
                            </span>
                          ))}
                          <span className="px-2 py-0.5 bg-gray-100 text-gray-700 rounded-full text-xs">
                            {formatDuration(track.duration_sec)} • {track.size_mb}MB
                          </span>
                        </div>

                        <audio
                          controls
                          className="w-full h-8"
                          preload="metadata"
                          style={{ height: '32px' }}
                        >
                          <source src={`/api/music/library/download/${track.filename}`} type="audio/mpeg" />
                          Váš prohlížeč nepodporuje přehrávání audia.
                        </audio>
                      </div>
                    );
                  })()}
                </div>

                <button
                  onClick={async () => {
                    setSelectedGlobalMusic(null);
                    setAutoSelectedMusic(null);
                    
                    // Clear from script_state
                    if (episodeId) {
                      try {
                        await axios.post(`/api/projects/${episodeId}/music/select-global`, {
                          selected_track: null
                        }, { timeout: 10000 });
                      } catch (e) {
                        console.error('Failed to clear selected music:', e);
                      }
                    }
                  }}
                  className="px-3 py-1 bg-red-100 text-red-800 text-sm rounded hover:bg-red-200 transition-colors"
                >
                  🗑️ Zrušit
                </button>
              </div>

              {autoSelectedMusic && !selectedGlobalMusic && (
                <div className="mt-3 p-2 bg-blue-50 border border-blue-200 rounded text-xs text-blue-800">
                  💡 <strong>Tip:</strong> Systém automaticky vybral tuto hudbu podle tématu "{scriptState?.episode_input?.topic || scriptState?.topic || '—'}". 
                  Můžete si vybrat jinou v Music Library nebo použít tuto.
                </div>
              )}
            </div>
          )}

          {/* No music selected */}
          {!selectedGlobalMusic && !autoSelectedMusic && (
            <div className="p-4 border border-gray-200 rounded-lg bg-white text-center">
              <div className="text-sm text-gray-600 mb-2">
                Zatím není vybraná žádná hudba
              </div>
              <button
                onClick={autoSelectMusic}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
              >
                🤖 Auto-vybrat hudbu
              </button>
            </div>
          )}

          {videoCompilationState.outputPath && (selectedGlobalMusic || autoSelectedMusic) && needsMusicRemix && (
            <div className="mt-3 p-3 bg-amber-50 border border-amber-200 rounded text-xs text-amber-900">
              <div className="font-medium mb-1">Hudba byla změněna</div>
              <div>
                Aktuální video bylo vygenerováno s hudbou: <span className="font-mono">{compiledMusicFilename || '—'}</span>. Vybráno je: <span className="font-mono">{selectedMusicFilename}</span>.
              </div>
              <div className="mt-2 flex gap-2">
                <button
                  onClick={() => {
                    setVideoCompilationState({
                      status: 'idle',
                      progress: 0,
                      currentStep: '',
                      error: null,
                      outputPath: null,
                    });
                    setTimeout(() => generateVideoCompilation({ mode: 'cb_only' }), 0);
                  }}
                  className="px-3 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors text-xs"
                  title="Rychlý remix hudby bez znovu-resolving assetů (CB only)"
                >
                  🎵 Remix hudby (rychle)
                </button>
              </div>
            </div>
          )}

          <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded text-xs text-blue-800">
            <strong>Jak to funguje:</strong> Systém analyzuje téma a náladu scénáře a automaticky vybere 
            vhodnou hudbu z globální knihovny. Při kompilaci se hudba mixuje zhruba na {musicBgGainDb}dB (nastavitelné výše) s fade-in/out efekty.
          </div>
        </div>
      )}

      {/* Music Library Modal */}
      <MusicLibraryModal
        isOpen={showMusicLibrary}
        onClose={() => setShowMusicLibrary(false)}
        onSelectTrack={handleMusicLibrarySelect}
      />

      {/* Video Compilation Section */}
      {episodeId && (
        <div className="mt-6 p-4 border border-blue-200 rounded-lg bg-blue-50">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-lg font-semibold text-gray-900">🎬 Video Compilation</h3>
              <p className="text-sm text-gray-600 mt-1">
                Spojte audio s archive.org videi do finálního videa
              </p>
            </div>
          </div>

          {/* Search Queries Editor (BEFORE compilation) */}
          {scriptState && (
            <div className="mb-4 p-4 bg-white border border-gray-200 rounded">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="text-sm font-semibold text-gray-900">🔎 Vyhledávací dotazy pro archive.org (AAR)</div>
                  <div className="text-xs text-gray-600 mt-1">
                    Tady vidíš dotazy, podle kterých AAR hledá videa. Můžeš přidat vlastní dotaz (badge) a ten se přidá do vyhledávání.
                  </div>
                  <div className="mt-2 text-[11px] text-blue-800 bg-blue-50 border border-blue-200 rounded p-2">
                    <strong>Jak to číst:</strong> Tyhle badge ovlivňují jen hledání kandidátů (Preview). 
                    Pokud při „🎬 Kompilovat“ uvidíš <span className="font-mono">FDA_VALIDATION_FAILED</span>, je to validace shot plánu z kroku <strong>6) Footage Director</strong> (ne těchto badge) — typicky pomůže dát <strong>Retry Footage Director</strong>.
                  </div>
                </div>
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      setSearchQueryError('');
                      await loadSearchQueries(episodeId);
                      // Also refresh archive stats so the UI can reliably detect manifest existence
                      await loadArchiveStats();
                    } catch (e) {
                      // loadSearchQueries already sets a visible error
                    }
                  }}
                  className="px-3 py-1.5 rounded text-xs bg-white border border-gray-300 text-gray-800 hover:bg-gray-50"
                  title="Načíst uložené user queries z backendu"
                >
                  ↻ Refresh
                </button>
              </div>

              {(() => {
                // NOTE: FDA auto queries are no longer used - AAR is the sole source
                const userQueries = Array.isArray(userSearchQueries) ? userSearchQueries : [];
                const episodePoolQueriesArray = Array.isArray(episodePoolQueries) ? episodePoolQueries : [];
                const hasShotPlanLocal = episodePoolQueriesArray.length > 0;
                return (
                  <div className="mt-3">
                    {/* Legacy fallback removed - use AAR Step-by-Step workflow instead */}

                    {/* Episode Pool Queries (AAR primary queries - shown first!) */}
                    {episodePoolQueriesArray.length > 0 && (
                      <div className="mb-4 p-3 bg-green-50 border-2 border-green-400 rounded">
                        <div className="text-sm font-bold text-green-900 mb-2">
                          ✅ Episode Pool Queries (AAR - PRIMÁRNÍ vyhledávání)
                        </div>
                        <div className="text-xs text-green-800 mb-2">
                          <strong>Tyto dotazy AAR SKUTEČNĚ POUŽIL</strong> pro Episode Pool Mode ({episodePoolQueriesArray.length} queries místo 300+). 
                          Toto jsou dotazy, podle kterých se vyhledávalo!
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {episodePoolQueriesArray.map((q, idx) => (
                            <span
                              key={idx}
                              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs bg-green-200 text-green-900 border border-green-400 font-medium"
                              title="Skutečný episode pool query použitý v AAR"
                            >
                              <span className="font-mono">{q}</span>
                            </span>
                          ))}
                        </div>
                        <div className="mt-2 text-[10px] text-green-700">
                          💡 Pokud vidíš špatné výsledky, problém je v těchto queries - upravuj je pomocí AAR kódu (ne FDA!).
                        </div>
                      </div>
                    )}

                    {/* User queries */}
                    <div className="mt-3">
                      <div className="text-xs font-medium text-gray-800 mb-2">Tvoje dotazy (přidají se do vyhledávání)</div>
                      <div className="flex flex-wrap gap-2">
                        {userQueries.length === 0 && (
                          <div className="text-xs text-gray-500">Žádné vlastní dotazy</div>
                        )}
                        {userQueries.map((q) => (
                          <span
                            key={q}
                            className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs bg-blue-100 text-blue-900 border border-blue-200"
                          >
                            <span className="font-mono">{q}</span>
                            <button
                              onClick={() => removeUserSearchQuery(q)}
                              disabled={searchQuerySaving}
                              className="text-blue-900/70 hover:text-blue-900"
                              title="Odebrat dotaz"
                            >
                              ✕
                            </button>
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Add query */}
                    <div className="mt-3 flex items-center gap-2">
                      <input
                        value={searchQueryInput}
                        onChange={(e) => setSearchQueryInput(e.target.value)}
                        placeholder="Napiš vlastní search query (např. 'Charles Bridge Prague historical photo')"
                        className="flex-1 px-3 py-2 border border-gray-300 rounded text-sm"
                        disabled={searchQuerySaving}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') addUserSearchQuery();
                        }}
                      />
                      <button
                        onClick={addUserSearchQuery}
                        disabled={searchQuerySaving || !normalizeQuery(searchQueryInput)}
                        className={`px-4 py-2 rounded text-sm font-medium ${
                          (searchQuerySaving || !normalizeQuery(searchQueryInput))
                            ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
                            : 'bg-blue-600 text-white hover:bg-blue-700'
                        }`}
                      >
                        ➕ Přidat
                      </button>
                    </div>
                    {searchQueryError && (
                      <div className="mt-2 text-xs text-red-700 bg-red-50 border border-red-200 rounded p-2">
                        {toDisplayString(searchQueryError)}
                      </div>
                    )}

                    {/* NOTE: FDA auto queries removed - AAR is now the SOLE source of search queries */}
                  </div>
                );
              })()}
            </div>
          )}

          {/* Prerequisites / why you cannot compile yet */}
          {!canCompile && (
            <div className="mb-4 p-3 bg-white border border-gray-200 rounded">
              <div className="text-sm font-medium text-gray-900">Nejde spustit kompilaci — chybí prerequisites</div>
              <div className="text-xs text-gray-600 mt-1 space-y-1">
                <div>
                  1) Shot plan: {hasShotPlan ? '✅ OK' : '❌ chybí (nejdřív dokončete Footage Director)'}
                </div>
                <div>
                  2) Voice-over MP3: {hasVoiceover ? '✅ OK' : '❌ chybí (nejdřív vygenerujte Voice-over)'}
                </div>
                <div>
                  Status: <span className="font-mono">{scriptStatus}</span> (na retry kompilace to nevadí, pokud jsou prerequisites splněné)
                </div>
              </div>
              <div className="mt-2 flex gap-2">
                <button
                  onClick={() => refreshState(episodeId)}
                  className="px-3 py-1.5 rounded text-sm bg-white border border-gray-300 text-gray-800 hover:bg-gray-50"
                >
                  ↻ Refresh state
                </button>
              </div>
            </div>
          )}

          {/* Idle State - Two-Step Workflow */}
          {videoCompilationState.status === 'idle' && !archivePreviewMode && (
            <div className="mb-4 p-3 bg-white border border-gray-200 rounded">
              
              {/* AAR STEP-BY-STEP CONTROL PANEL */}
              <div className="mb-4 p-4 bg-gradient-to-br from-purple-50 to-indigo-50 border-2 border-purple-300 rounded-lg">
                <div className="text-sm font-bold text-purple-900 mb-2">
                  🎯 AAR Step-by-Step Control (Preview Mode)
                </div>
                <div className="text-xs text-purple-700 mb-3">
                  Krok za krokem: Queries → Search → LLM Check (plná kontrola nad procesem)
                </div>
                
                {/* STEP 1: Generate Queries */}
                <div className="mb-3 p-3 bg-white border border-purple-200 rounded">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-xs font-medium text-gray-800">
                      {aarStep === 'idle' ? '📝 Step 1: Generate Queries' : '✅ Step 1: Queries Generated'}
                    </div>
                    {aarStep === 'idle' && (
                      <button
                        onClick={aarStep1GenerateQueries}
                        disabled={!canCompile || aarLoading}
                        className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                          !canCompile || aarLoading
                            ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                            : 'bg-purple-600 text-white hover:bg-purple-700'
                        }`}
                      >
                        {aarLoading ? '⏳ Generating...' : '🚀 Generate Queries'}
                      </button>
                    )}
                  </div>
                  
                  {/* Checkbox grid for queries */}
                  {aarQueries.length > 0 && (
                    <div className="mt-2 p-2 bg-purple-50 border border-purple-200 rounded">
                      <div className="text-[11px] text-purple-700 mb-2 font-medium">
                        📋 Select queries to search (uncheck to exclude):
                      </div>
                      
                      {/* Custom query input */}
                      <div className="mb-3 flex gap-2">
                        <input
                          type="text"
                          placeholder="Add custom query..."
                          value={searchQueryInput}
                          onChange={(e) => setSearchQueryInput(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && searchQueryInput.trim()) {
                              const newQuery = searchQueryInput.trim();
                              if (!aarQueries.includes(newQuery)) {
                                setAarQueries([...aarQueries, newQuery]);
                                setAarQueryChecked({ ...aarQueryChecked, [newQuery]: true });
                              }
                              setSearchQueryInput('');
                            }
                          }}
                          className="flex-1 px-2 py-1.5 border border-purple-300 rounded text-xs"
                        />
                        <button
                          onClick={() => {
                            const newQuery = searchQueryInput.trim();
                            if (newQuery && !aarQueries.includes(newQuery)) {
                              setAarQueries([...aarQueries, newQuery]);
                              setAarQueryChecked({ ...aarQueryChecked, [newQuery]: true });
                              setSearchQueryInput('');
                            }
                          }}
                          disabled={!searchQueryInput.trim()}
                          className={`px-3 py-1.5 rounded text-xs font-medium ${
                            searchQueryInput.trim()
                              ? 'bg-purple-600 text-white hover:bg-purple-700'
                              : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                          }`}
                        >
                          ➕ Add
                        </button>
                      </div>
                      
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5 max-h-64 overflow-y-auto">
                        {aarQueries.map((q, idx) => (
                          <label key={idx} className="flex items-center gap-2 text-xs text-gray-700 p-2 bg-white rounded hover:bg-purple-50 cursor-pointer border border-transparent hover:border-purple-300 group">
                            <input
                              type="checkbox"
                              checked={aarQueryChecked[q] === true}
                              onChange={(e) => {
                                setAarQueryChecked({ ...aarQueryChecked, [q]: e.target.checked });
                              }}
                              className="w-4 h-4 text-purple-600"
                            />
                            <span className="flex-1 font-mono text-[11px]">{q}</span>
                            <button
                              onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                const newQueries = aarQueries.filter((_, i) => i !== idx);
                                const newChecked = { ...aarQueryChecked };
                                delete newChecked[q];
                                setAarQueries(newQueries);
                                setAarQueryChecked(newChecked);
                              }}
                              className="opacity-0 group-hover:opacity-100 px-1.5 py-0.5 rounded text-[10px] bg-red-500 text-white hover:bg-red-600"
                              title="Remove query"
                            >
                              ×
                            </button>
                          </label>
                        ))}
                      </div>
                      <div className="mt-2 flex items-center justify-between">
                        <div className="text-[11px] text-purple-700">
                          {Object.values(aarQueryChecked).filter(Boolean).length} / {aarQueries.length} selected
                        </div>
                        <div className="flex gap-2">
                          <button
                            onClick={() => {
                              const allChecked = {};
                              aarQueries.forEach(q => { allChecked[q] = true; });
                              setAarQueryChecked(allChecked);
                            }}
                            className="px-2 py-1 rounded text-[11px] bg-purple-600 text-white hover:bg-purple-700"
                          >
                            Select All
                          </button>
                          <button
                            onClick={() => {
                              const allUnchecked = {};
                              aarQueries.forEach(q => { allUnchecked[q] = false; });
                              setAarQueryChecked(allUnchecked);
                            }}
                            className="px-2 py-1 rounded text-[11px] bg-gray-400 text-white hover:bg-gray-500"
                          >
                            Clear All
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
                
                {/* STEP 2: Search */}
                {(aarStep === 'queries_generated' || aarStep === 'search_completed' || aarStep === 'llm_completed') && (
                  <div className="mb-3 p-3 bg-white border border-purple-200 rounded">
                    <div className="flex items-center justify-between mb-2">
                      <div className="text-xs font-medium text-gray-800">
                        {aarStep === 'queries_generated' ? '🔍 Step 2: Search Archives' : '✅ Step 2: Search Complete'}
                      </div>
                      {aarStep === 'queries_generated' && (
                        <button
                          onClick={aarStep2Search}
                          disabled={aarLoading || Object.values(aarQueryChecked).filter(Boolean).length === 0}
                          className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                            aarLoading || Object.values(aarQueryChecked).filter(Boolean).length === 0
                              ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                              : 'bg-blue-600 text-white hover:bg-blue-700'
                          }`}
                        >
                          {aarLoading ? '⏳ Searching...' : '🔍 Search Now'}
                        </button>
                      )}
                    </div>
                    
                    {aarRawResults && (
                      <div className="mt-2 p-2 bg-blue-50 border border-blue-200 rounded">
                        <div className="text-[11px] text-blue-700 font-medium mb-1">
                          📦 Raw Results (before LLM dedup):
                        </div>
                        <div className="flex gap-4 text-[11px] text-blue-800 mb-2">
                          <div>
                            <span className="font-medium">Videos:</span>{' '}
                            <span className="font-mono">{aarRawResults?.stats?.total_video_candidates || 0}</span>
                          </div>
                          <div>
                            <span className="font-medium">Images:</span>{' '}
                            <span className="font-mono">{aarRawResults?.stats?.total_image_candidates || 0}</span>
                          </div>
                          <div>
                            <span className="font-medium">Queries:</span>{' '}
                            <span className="font-mono">{aarRawResults?.stats?.queries_executed || 0}</span>
                          </div>
                        </div>
                        
                        {/* Collapsible preview of raw results */}
                        <details className="mt-2">
                          <summary className="cursor-pointer text-[11px] text-blue-700 font-medium hover:text-blue-900">
                            🔍 Prohlédnout raw results (klikni pro rozbalení)
                          </summary>
                          <div className="mt-2 max-h-96 overflow-y-auto">
                            {/* Raw Videos */}
                            {aarRawResults.raw_video_candidates && aarRawResults.raw_video_candidates.length > 0 && (
                              <div className="mb-3">
                                <div className="text-[10px] font-medium text-blue-800 mb-2">📹 Videos ({aarRawResults.raw_video_candidates.length}):</div>
                                <div className="space-y-1.5">
                                  {aarRawResults.raw_video_candidates.slice(0, 20).map((v, idx) => {
                                    const vid = v.archive_item_id || `video_${idx}`;
                                    return (
                                      <div key={idx} className="p-2 bg-white rounded border border-blue-200 text-[10px]">
                                        <div className="flex items-start gap-2">
                                          <input
                                            type="checkbox"
                                            checked={aarManualSelection.videos[vid] || false}
                                            onChange={(e) => {
                                              setAarManualSelection(prev => ({
                                                ...prev,
                                                videos: { ...prev.videos, [vid]: e.target.checked }
                                              }));
                                            }}
                                            className="mt-0.5 cursor-pointer"
                                          />
                                          <div className="flex-1">
                                            <div className="font-medium text-gray-900">{v.title || 'Untitled'}</div>
                                            <div className="text-gray-600 mt-0.5">
                                              Source: <span className="font-mono">{v.source || 'unknown'}</span>
                                              {v._source_query && <> • Query: <span className="font-mono text-blue-700">{v._source_query}</span></>}
                                            </div>
                                            {v.thumbnail_url && (
                                              <img src={v.thumbnail_url} alt="" className="mt-1 w-32 h-20 object-cover rounded" />
                                            )}
                                          </div>
                                        </div>
                                      </div>
                                    );
                                  })}
                                  {aarRawResults.raw_video_candidates.length > 20 && (
                                    <div className="text-[10px] text-gray-500 italic">
                                      ... a dalších {aarRawResults.raw_video_candidates.length - 20} videí
                                    </div>
                                  )}
                                </div>
                              </div>
                            )}
                            
                            {/* Raw Images */}
                            {aarRawResults.raw_image_candidates && aarRawResults.raw_image_candidates.length > 0 && (
                              <div>
                                <div className="text-[10px] font-medium text-blue-800 mb-2">🖼️ Images ({aarRawResults.raw_image_candidates.length}):</div>
                                <div className="grid grid-cols-4 gap-2">
                                  {aarRawResults.raw_image_candidates.slice(0, 24).map((img, idx) => {
                                    const imgId = img.archive_item_id || `image_${idx}`;
                                    return (
                                      <div key={idx} className="p-1.5 bg-white rounded border border-blue-200 relative">
                                        <input
                                          type="checkbox"
                                          checked={aarManualSelection.images[imgId] || false}
                                          onChange={(e) => {
                                            setAarManualSelection(prev => ({
                                              ...prev,
                                              images: { ...prev.images, [imgId]: e.target.checked }
                                            }));
                                          }}
                                          className="absolute top-1 left-1 cursor-pointer z-10"
                                        />
                                        {img.thumbnail_url && (
                                          <img src={img.thumbnail_url} alt={img.title || ''} className="w-full h-24 object-cover rounded mb-1" />
                                        )}
                                        <div className="text-[9px] text-gray-700 truncate">{img.title || 'Untitled'}</div>
                                        <div className="text-[8px] text-gray-500 truncate">
                                          {img._source_query && <span className="font-mono">{img._source_query}</span>}
                                        </div>
                                      </div>
                                    );
                                  })}
                                  {aarRawResults.raw_image_candidates.length > 24 && (
                                    <div className="col-span-4 text-[10px] text-gray-500 italic text-center">
                                      ... a dalších {aarRawResults.raw_image_candidates.length - 24} obrázků
                                    </div>
                                  )}
                                </div>
                              </div>
                            )}
                          </div>
                        </details>
                      </div>
                    )}
                  </div>
                )}
                
                {/* STEP 3: LLM Quality Check */}
                {(aarStep === 'search_completed' || aarStep === 'llm_completed') && (
                  <div className="mb-3 p-3 bg-white border border-purple-200 rounded">
                    <div className="flex items-center justify-between mb-2">
                      <div className="text-xs font-medium text-gray-800">
                        {aarStep === 'search_completed' ? '🎨 Step 3: LLM Quality Check' : '✅ Step 3: LLM Check Complete'}
                      </div>
                      {aarStep === 'search_completed' && (
                        <button
                          onClick={aarStep3LLMCheck}
                          disabled={aarLoading}
                          className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                            aarLoading
                              ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                              : 'bg-green-600 text-white hover:bg-green-700'
                          }`}
                        >
                          {aarLoading ? '⏳ Analyzing...' : '🎨 LLM Quality Check'}
                        </button>
                      )}
                    </div>
                    
                    {aarStep === 'llm_completed' && (
                      <div className="mt-2 p-2 bg-green-50 border border-green-200 rounded">
                        <div className="text-[11px] text-green-700 font-medium">
                          ✅ Pipeline Complete! Scroll down to "Episode Pool" to see final results.
                        </div>
                      </div>
                    )}
                  </div>
                )}
                
                {/* Error display */}
                {aarError && (
                  <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700">
                    ❌ {aarError}
                  </div>
                )}
                
                {/* Reset button */}
                {aarStep !== 'idle' && (
                  <div className="mt-2 flex justify-end">
                    <button
                      onClick={() => {
                        setAarStep('idle');
                        setAarQueries([]);
                        setAarQueryChecked({});
                        setAarRawResults(null);
                        setAarError('');
                      }}
                      className="px-3 py-1 rounded text-xs bg-gray-400 text-white hover:bg-gray-500"
                    >
                      🔄 Reset Workflow
                    </button>
                  </div>
                )}
              </div>
              
              {/* DIVIDER */}
              <div className="my-4 border-t border-gray-300"></div>
              
              {/* DEPRECATED SECTION - HIDDEN (use Step-by-Step above instead) */}
              {false && (
                <>
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="text-sm font-medium text-gray-900">Ready to compile</div>
                      <div className="text-xs text-gray-600 mt-1">
                        🔍 Preview: najde videa/obrázky (AAR) • 🎬 Kompilovat: stáhne + vytvoří video (CB)
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={previewArchiveVideos}
                        disabled={!canCompile}
                        className={`px-4 py-2 rounded-lg transition-colors font-medium ${
                          !canCompile
                            ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                            : 'bg-purple-600 text-white hover:bg-purple-700'
                        }`}
                        title="Najde videa/obrázky na archive.org bez stahování (AUTOMATICKÝ režim - DEPRECATED, použij Step-by-Step výše)"
                      >
                        🔍 Preview Videa (Auto)
                      </button>
                      <button
                        onClick={generateVideoCompilation}
                        disabled={!canCompile}
                        className={`px-4 py-2 rounded-lg transition-colors font-medium ${
                          !canCompile
                            ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                            : 'bg-blue-600 text-white hover:bg-blue-700'
                        }`}
                        title="Spustí full pipeline: AAR + CB (stahování + kompilace)"
                      >
                        🎬 Kompilovat
                      </button>
                    </div>
                  </div>
                </>
              )}
              
              {/* FINAL COMPILATION BUTTON (ACTIVE) */}
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <div className="text-sm font-medium text-gray-900">🎬 Finální kompilace</div>
                  <div className="text-xs text-gray-600 mt-1">
                    Po dokončení Step 3 (LLM Check) můžeš zkompilovat finální video
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={generateVideoCompilation}
                    disabled={!canCompile || aarStep !== 'llm_completed'}
                    className={`px-4 py-2 rounded-lg transition-colors font-medium ${
                      !canCompile || aarStep !== 'llm_completed'
                        ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                        : 'bg-blue-600 text-white hover:bg-blue-700'
                    }`}
                    title="Stáhne assets + vytvoří finální video (AAR + CB pipeline)"
                  >
                    🎬 Kompilovat Video
                  </button>
                </div>
              </div>

              {/* Archive Stats Dashboard */}
              {archiveStats && archiveStats.manifest_exists && (
                <div className="mt-4 pt-4 border-t border-gray-200">
                  <div className="text-xs font-medium text-gray-800 mb-3">
                    📊 Archive.org Výsledky Preview
                  </div>
                  {archiveStats?.by_source && (
                    <div className="mb-3 text-[11px] text-gray-600">
                      Zdroje:{" "}
                      <span className="font-mono">
                        archive {archiveStats.by_source.archive_org ?? 0}
                      </span>
                      {" • "}
                      <span className="font-mono">
                        wikimedia {archiveStats.by_source.wikimedia ?? 0}
                      </span>
                      {" • "}
                      <span className="font-mono">
                        europeana {archiveStats.by_source.europeana ?? 0}
                      </span>
                      {typeof archiveStats.by_source.other === "number" && archiveStats.by_source.other > 0 && (
                        <>
                          {" • "}
                          <span className="font-mono">other {archiveStats.by_source.other}</span>
                        </>
                      )}
                    </div>
                  )}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="bg-gradient-to-br from-blue-50 to-blue-100 p-3 rounded-lg border border-blue-200">
                      <div className="text-2xl font-bold text-blue-700">{archiveStats.video_candidates}</div>
                      <div className="text-xs text-blue-600 mt-1">🎬 Videa</div>
                    </div>
                    <div className="bg-gradient-to-br from-green-50 to-green-100 p-3 rounded-lg border border-green-200">
                      <div className="text-2xl font-bold text-green-700">{archiveStats.image_candidates}</div>
                      <div className="text-xs text-green-600 mt-1">🖼️ Obrázky</div>
                    </div>
                    <div className="bg-gradient-to-br from-purple-50 to-purple-100 p-3 rounded-lg border border-purple-200">
                      <div className="text-2xl font-bold text-purple-700">{archiveStats.total_candidates}</div>
                      <div className="text-xs text-purple-600 mt-1">📦 Celkem</div>
                    </div>
                    <div className="bg-gradient-to-br from-orange-50 to-orange-100 p-3 rounded-lg border border-orange-200">
                      <div className="text-2xl font-bold text-orange-700">
                        {archiveStats.scenes_with_candidates}/{archiveStats.total_scenes}
                      </div>
                      <div className="text-xs text-orange-600 mt-1">✅ Scény OK</div>
                    </div>
                  </div>
                  {archiveStats.scenes_without_candidates > 0 && (
                    <div className="mt-2 text-xs text-orange-700 bg-orange-50 p-2 rounded border border-orange-200">
                      ⚠️ {archiveStats.scenes_without_candidates} scén nemá kandidáty - upravte vyhledávací dotazy výše
                    </div>
                  )}
                  {archiveStats.total_candidates === 0 && (
                    <div className="mt-2 text-xs text-red-700 bg-red-50 p-2 rounded border border-red-200">
                      ❌ Nenašly se žádné kandidáty - zkontrolujte vyhledávací dotazy nebo shot plan
                      {archiveStats?.query_probe?.mode === 'preview_fast_probe' && (
                        <div className="mt-2 text-[11px] text-red-800">
                          <div className="font-medium">
                            Rychlý test dotazů (preview):
                            {' '}0 výsledků po otestování {archiveStats.query_probe.probed_queries}/{archiveStats.query_probe.unique_queries_total} dotazů.
                          </div>
                          {Array.isArray(archiveStats.query_probe.probe_results) && archiveStats.query_probe.probe_results.length > 0 && (
                            <div className="mt-1 text-[10px] text-red-700">
                              Testované dotazy:{' '}
                              <span className="font-mono">
                                {archiveStats.query_probe.probe_results
                                  .slice(0, 5)
                                  .map((x) => x.query)
                                  .join(' • ')}
                                {archiveStats.query_probe.probe_results.length > 5 ? ' • …' : ''}
                              </span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                  {archiveStats.total_candidates > 0 && (
                    <div className="mt-2 text-xs text-green-700 bg-green-50 p-2 rounded border border-green-200">
                      ✅ Preview OK - můžete pokračovat kompilací nebo upravit vyhledávací dotazy
                    </div>
                  )}

                  {/* Visual previews (thumbnails) + LLM Assistant */}
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <button
                      onClick={async () => {
                        const next = !showEpisodePool;
                        setShowEpisodePool(next);
                        if (next && !episodePool && !episodePoolLoading) {
                          await loadEpisodePool();
                        }
                      }}
                      className="px-3 py-1.5 rounded text-xs bg-gradient-to-r from-green-600 to-green-700 text-white hover:from-green-700 hover:to-green-800 font-medium shadow-sm"
                      title="Zobraz VŠECHNY nalezené assets (celý episode pool)"
                    >
                      📦 {showEpisodePool ? 'Skrýt Episode Pool' : 'Zobrazit Episode Pool (VŠECHNY assets)'}
                    </button>
                    
                    <button
                      onClick={async () => {
                        const next = !showVisualCandidates;
                        setShowVisualCandidates(next);
                        if (next && !visualCandidates && !visualCandidatesLoading) {
                          await loadVisualCandidates();
                        }
                      }}
                      className="px-3 py-1.5 rounded text-xs bg-white border border-gray-300 text-gray-800 hover:bg-gray-50"
                    >
                      🖼️ {showVisualCandidates ? 'Skrýt náhledy' : 'Zobrazit náhledy kandidátů (per-beat)'}
                    </button>
                    
                    <button
                      onClick={runVisualAssistant}
                      disabled={visualAssistantRunning || !archiveStats?.manifest_exists}
                      className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                        visualAssistantRunning || !archiveStats?.manifest_exists
                          ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                          : 'bg-gradient-to-r from-purple-600 to-purple-700 text-white hover:from-purple-700 hover:to-purple-800 shadow-sm'
                      }`}
                      title={
                        !archiveStats?.manifest_exists
                          ? '⚠️ Nejdřív spusť "🔍 Preview Videa" aby se našli kandidáti'
                          : visualAssistantRunning
                          ? 'Probíhá analýza thumbnailů pomocí GPT-4o Vision...'
                          : 'LLM Vision analyzuje thumbnaily a vybere nejlepší pro každou scénu'
                      }
                    >
                      {visualAssistantRunning ? (
                        <>⏳ Analyzuji...</>
                      ) : !archiveStats?.manifest_exists ? (
                        <>✨ LLM vybrat nejlepší (nejdřív Preview)</>
                      ) : (
                        <>✨ LLM vybrat nejlepší vizuály</>
                      )}
                    </button>
                    
                    {visualAssistantResults && (
                      <div className="text-xs text-green-700 bg-green-50 px-2 py-1 rounded border border-green-200">
                        ✅ Analyzováno {visualAssistantResults.total_analyzed} kandidátů
                      </div>
                    )}
                  </div>

                  {showEpisodePool && (
                    <div className="mt-3 p-4 bg-gradient-to-br from-green-50 to-green-100 border-2 border-green-400 rounded-lg shadow-md">
                      {episodePoolLoading && (
                        <div className="text-sm text-gray-600">⏳ Načítám episode pool...</div>
                      )}
                      {!episodePoolLoading && !episodePool?.success && (
                        <div className="text-sm text-red-700">❌ Nepodařilo se načíst episode pool.</div>
                      )}
                      {!episodePoolLoading && episodePool?.success && (
                        <div>
                          <div className="mb-3 pb-3 border-b-2 border-green-400">
                            <div className="flex items-center justify-between mb-2">
                              <h4 className="text-lg font-bold text-green-900">📦 Episode Pool - VŠECHNY nalezené assets</h4>
                              {selectedPoolAssets.size > 0 && (
                                <div className="bg-green-600 text-white px-3 py-1 rounded-full text-sm font-bold">
                                  ✓ Vybráno: {selectedPoolAssets.size}
                                </div>
                              )}
                            </div>
                            <div className="mt-2 text-xs text-green-800">
                              <strong>Queries použité:</strong> {(episodePool.queries_used || []).length} queries
                            </div>
                            <div className="mt-1 flex flex-wrap gap-1">
                              {(episodePool.queries_used || []).slice(0, 12).map((q, idx) => (
                                <span key={idx} className="px-2 py-0.5 bg-green-200 text-green-900 rounded text-[10px] font-mono">
                                  {q}
                                </span>
                              ))}
                            </div>
                            <div className="mt-3 grid grid-cols-3 gap-3 text-center">
                              <div className="bg-white rounded-lg p-2 border border-green-300">
                                <div className="text-2xl font-bold text-blue-600">{episodePool.pool?.total_videos || 0}</div>
                                <div className="text-xs text-gray-600">📹 Videa</div>
                              </div>
                              <div className="bg-white rounded-lg p-2 border border-green-300">
                                <div className="text-2xl font-bold text-purple-600">{episodePool.pool?.total_images || 0}</div>
                                <div className="text-xs text-gray-600">🖼️ Obrázky</div>
                              </div>
                              <div className="bg-white rounded-lg p-2 border border-green-300">
                                <div className="text-2xl font-bold text-green-600">{episodePool.pool?.total_assets || 0}</div>
                                <div className="text-xs text-gray-600">📦 Celkem</div>
                              </div>
                            </div>

                            {/* Transparency view toggle */}
                            <div className="mt-4 flex flex-wrap items-center gap-2">
                              <div className="text-xs font-semibold text-green-900 mr-2">Zobrazení:</div>
                              <button
                                type="button"
                                onClick={() => setEpisodePoolView('selected')}
                                className={`text-xs px-3 py-1 rounded border ${episodePoolView === 'selected' ? 'bg-green-700 text-white border-green-800' : 'bg-white text-gray-800 border-gray-300 hover:bg-gray-50'}`}
                              >
                                ✅ Vybraný pool (pro kompilaci)
                              </button>
                              <button
                                type="button"
                                onClick={() => setEpisodePoolView('unique')}
                                className={`text-xs px-3 py-1 rounded border ${episodePoolView === 'unique' ? 'bg-green-700 text-white border-green-800' : 'bg-white text-gray-800 border-gray-300 hover:bg-gray-50'}`}
                                title="UNIQUE ranked = deduplikované výsledky (včetně LLM score, pokud běželo)"
                              >
                                🧬 Unique ranked ({episodePool.pool?.unique_ranked?.total_videos || 0}v / {episodePool.pool?.unique_ranked?.total_images || 0}i)
                              </button>
                              <button
                                type="button"
                                onClick={() => setEpisodePoolView('raw')}
                                className={`text-xs px-3 py-1 rounded border ${episodePoolView === 'raw' ? 'bg-green-700 text-white border-green-800' : 'bg-white text-gray-800 border-gray-300 hover:bg-gray-50'}`}
                                title="RAW candidates = úplně vše, co bylo nalezeno (před deduplikací)"
                              >
                                🔎 RAW ({episodePool.pool?.raw_candidates?.total_videos || 0}v / {episodePool.pool?.raw_candidates?.total_images || 0}i)
                              </button>
                            </div>
                          </div>

                          {(() => {
                            const view = episodePoolView || 'selected';
                            const bucket =
                              view === 'raw'
                                ? episodePool.pool?.raw_candidates
                                : view === 'unique'
                                ? episodePool.pool?.unique_ranked
                                : episodePool.pool;
                            const videos = bucket?.videos || [];
                            const images = bucket?.images || [];

                            const renderScore = (x) => {
                              const s = x?.llm_quality_score;
                              if (s === undefined || s === null) return null;
                              return (
                                <div className="mt-1 text-[10px] text-green-800 bg-green-50 border border-green-200 px-1 py-0.5 rounded">
                                  LLM score: <span className="font-mono">{s}</span>
                                </div>
                              );
                            };

                            return (
                              <>
                          {/* Videos */}
                          {videos && videos.length > 0 && (
                            <div className="mb-4">
                              <div className="flex items-center justify-between mb-2">
                                <h5 className="text-sm font-bold text-blue-900">📹 Videa ({videos.length})</h5>
                                <div className="flex gap-2">
                                  <button
                                    onClick={() => selectAllPoolAssets('videos')}
                                    className="text-xs px-2 py-1 bg-blue-500 text-white rounded hover:bg-blue-600"
                                  >
                                    Vybrat všechna videa
                                  </button>
                                  <button
                                    onClick={deselectAllPoolAssets}
                                    className="text-xs px-2 py-1 bg-gray-400 text-white rounded hover:bg-gray-500"
                                  >
                                    Zrušit výběr
                                  </button>
                                </div>
                              </div>
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                                {videos.map((video, idx) => {
                                  const isSelected = selectedPoolAssets.has(video.archive_item_id);
                                  return (
                                    <div 
                                      key={video.archive_item_id || idx} 
                                      className={`bg-white rounded-lg border-2 overflow-hidden shadow-sm cursor-pointer transition-all ${
                                        isSelected ? 'border-green-500 ring-2 ring-green-300' : 'border-blue-300 hover:border-blue-400'
                                      }`}
                                      onClick={() => togglePoolAssetSelection(video.archive_item_id)}
                                    >
                                      {/* Checkbox overlay */}
                                      <div className="relative">
                                        <div className="aspect-video bg-gray-100">
                                          {video.thumbnail_url ? (
                                            <img src={video.thumbnail_url} alt={video.title} className="w-full h-full object-cover" />
                                          ) : (
                                            <div className="w-full h-full flex items-center justify-center text-xs text-gray-500">No preview</div>
                                          )}
                                        </div>
                                        {isSelected && (
                                          <div className="absolute top-1 right-1 bg-green-500 text-white rounded-full p-1">
                                            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                                              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                            </svg>
                                          </div>
                                        )}
                                      </div>
                                      <div className="p-2">
                                        <div className="text-[11px] font-medium text-gray-900 line-clamp-2">{video.title || video.archive_item_id}</div>
                                        <div className="mt-1 text-[9px] text-gray-500 font-mono">{video.source || 'archive_org'}</div>
                                        {video._source_query && (
                                          <div className="mt-1 text-[8px] text-blue-700 bg-blue-50 px-1 py-0.5 rounded">
                                            Query: {video._source_query}
                                          </div>
                                        )}
                                        {renderScore(video)}
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}

                          {/* Images */}
                          {images && images.length > 0 && (
                            <div>
                              <div className="flex items-center justify-between mb-2">
                                <h5 className="text-sm font-bold text-purple-900">🖼️ Obrázky ({images.length})</h5>
                                <div className="flex gap-2">
                                  <button
                                    onClick={() => selectAllPoolAssets('images')}
                                    className="text-xs px-2 py-1 bg-purple-500 text-white rounded hover:bg-purple-600"
                                  >
                                    Vybrat všechny obrázky
                                  </button>
                                  <button
                                    onClick={deselectAllPoolAssets}
                                    className="text-xs px-2 py-1 bg-gray-400 text-white rounded hover:bg-gray-500"
                                  >
                                    Zrušit výběr
                                  </button>
                                </div>
                              </div>
                              <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
                                {images.map((image, idx) => {
                                  const isSelected = selectedPoolAssets.has(image.archive_item_id);
                                  return (
                                    <div 
                                      key={image.archive_item_id || idx} 
                                      className={`bg-white rounded overflow-hidden shadow-sm cursor-pointer transition-all ${
                                        isSelected ? 'border-2 border-green-500 ring-2 ring-green-300' : 'border border-purple-200 hover:border-purple-400'
                                      }`}
                                      onClick={() => togglePoolAssetSelection(image.archive_item_id)}
                                    >
                                      <div className="relative">
                                        <div className="aspect-square bg-gray-100">
                                          {image.thumbnail_url ? (
                                            <img src={image.thumbnail_url} alt={image.title} className="w-full h-full object-cover" />
                                          ) : (
                                            <div className="w-full h-full flex items-center justify-center text-[10px] text-gray-500">No preview</div>
                                          )}
                                        </div>
                                        {isSelected && (
                                          <div className="absolute top-1 right-1 bg-green-500 text-white rounded-full p-0.5">
                                            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                                              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                            </svg>
                                          </div>
                                        )}
                                      </div>
                                      <div className="p-1.5">
                                        <div className="text-[9px] text-gray-700 line-clamp-2">{image.title || image.archive_item_id}</div>
                                        <div className="mt-0.5 text-[8px] text-gray-500">{image.source || 'archive_org'}</div>
                                        {image._source_query && (
                                          <div className="mt-0.5 text-[7px] text-purple-700 bg-purple-50 px-1 py-0.5 rounded">
                                            Query: {image._source_query}
                                          </div>
                                        )}
                                        {renderScore(image)}
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}
                              </>
                            );
                          })()}
                        </div>
                      )}
                    </div>
                  )}

                  {showVisualCandidates && (
                    <div className="mt-3 p-3 bg-white border border-gray-200 rounded">
                      {visualCandidatesLoading && (
                        <div className="text-xs text-gray-500">Načítám náhledy…</div>
                      )}
                      {!visualCandidatesLoading && !visualCandidates?.success && (
                        <div className="text-xs text-red-700">Nepodařilo se načíst náhledy kandidátů.</div>
                      )}
                      {!visualCandidatesLoading && visualCandidates?.success && (
                        <div className="space-y-4">
                          {(visualCandidates.scenes || []).map((sc) => (
                            <div key={sc.scene_id} className="border border-gray-200 rounded p-3">
                              <div className="flex items-center justify-between mb-2">
                                <div className="text-xs font-medium text-gray-900">
                                  Scéna <span className="font-mono">{sc.scene_id}</span>
                                </div>
                                <div className="text-[11px] text-gray-500">
                                  {(sc.beats || []).length} beatů
                                </div>
                              </div>
                              <div className="space-y-3">
                                {(sc.beats || []).map((b) => {
                                  const beatKey = `${sc.scene_id}:${b.block_id}`;

                                  // Deduplicate candidates by archive_item_id (preserve order)
                                  const uniqueMap = new Map();
                                  (b.candidates || []).forEach((c) => {
                                    const key = c.archive_item_id || c.title;
                                    if (uniqueMap.has(key)) {
                                      uniqueMap.get(key).count += 1;
                                    } else {
                                      uniqueMap.set(key, { ...c, count: 1 });
                                    }
                                  });
                                  const uniqueCandidates = Array.from(uniqueMap.values()).slice(0, 8);

                                  // Manual override (persisted to manifest). If empty, we show an "Auto pick"
                                  // so user doesn't have to click everything just to see what will be used.
                                  const manualSelectedId = String(selectedBeatAssets?.[beatKey] || '').trim();
                                  const autoSelectedId = (() => {
                                    if (!uniqueCandidates.length) return '';
                                    // IMPORTANT: Keep UI aligned with actual pipeline behavior.
                                    // "Auto" uses the top candidate (index 0) unless user overrides selection.
                                    return String(uniqueCandidates[0]?.archive_item_id || '').trim();
                                  })();
                                  const effectiveSelectedId = manualSelectedId || autoSelectedId;
                                  const selectionMode = manualSelectedId ? 'manual' : autoSelectedId ? 'auto' : 'none';

                                  return (
                                    <div key={`${sc.scene_id}:${b.block_id}`} className="border-t border-gray-100 pt-2">
                                      <div className="flex items-start justify-between gap-3">
                                        <div className="text-[11px] text-gray-700">
                                          <span className="font-mono">{b.block_id}</span>
                                          {b.text ? (
                                            <span className="text-gray-500">
                                              {' '}
                                              — {String(b.text).slice(0, 140)}
                                              {String(b.text).length > 140 ? '…' : ''}
                                            </span>
                                          ) : null}

                                          {effectiveSelectedId ? (
                                            <div
                                              className={`mt-1 text-[10px] ${
                                                selectionMode === 'manual' ? 'text-blue-700' : 'text-indigo-700'
                                              }`}
                                            >
                                              {selectionMode === 'manual' ? '✅ Vybráno (MANUÁL): ' : '⭐ Auto vybráno: '}
                                              <span className="font-mono">{effectiveSelectedId}</span>
                                            </div>
                                          ) : (
                                            <div className="mt-1 text-[10px] text-gray-500">
                                              (Auto) žádný kandidát pro výběr
                                            </div>
                                          )}
                                        </div>

                                        <div className="shrink-0">
                                          <button
                                            onClick={() =>
                                              selectManifestAsset({
                                                sceneId: sc.scene_id,
                                                blockId: b.block_id,
                                                archiveItemId: null,
                                              })
                                            }
                                            disabled={!manualSelectedId}
                                            className={`px-2 py-1 rounded text-[10px] border transition-colors ${
                                              manualSelectedId
                                                ? 'bg-white border-gray-300 text-gray-800 hover:bg-gray-50'
                                                : 'bg-gray-100 border-gray-200 text-gray-400 cursor-not-allowed'
                                            }`}
                                            title="Zrušit ruční výběr (vrátit Auto pick)"
                                          >
                                            ↩︎ Auto
                                          </button>
                                        </div>
                                      </div>

                                      <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2">
                                        {uniqueCandidates.map((c, idx) => {
                                          const candidateId = String(c.archive_item_id || '').trim();
                                          const analysis = c._visual_analysis;
                                          const hasAnalysis = Boolean(analysis);
                                          const relevanceScore = hasAnalysis ? Number(analysis.relevance_score) : NaN;
                                          const hasScore = Number.isFinite(relevanceScore);
                                          const isRecommended = hasAnalysis && analysis.recommendation === 'use';
                                          const hasTextOverlay = hasAnalysis && Boolean(analysis.has_text_overlay);

                                          const isManualSelected =
                                            manualSelectedId && candidateId && candidateId === manualSelectedId;
                                          const isEffectiveSelected =
                                            effectiveSelectedId && candidateId && candidateId === String(effectiveSelectedId);
                                          const isAutoSelected = !manualSelectedId && isEffectiveSelected;

                                          return (
                                            <div
                                              key={c.archive_item_id || `${beatKey}:${idx}`}
                                              className={`border-2 rounded overflow-hidden relative ${
                                                hasAnalysis
                                                  ? isRecommended
                                                    ? 'border-green-400 bg-green-50'
                                                    : 'border-gray-300 bg-gray-50'
                                                  : 'border-gray-200 bg-gray-50'
                                              } ${
                                                isEffectiveSelected ? 'ring-4 ring-blue-500 border-blue-500 shadow-md' : ''
                                              }`}
                                            >
                                              <div className="aspect-video bg-gray-100 relative">
                                                {c.thumbnail_url ? (
                                                  <img
                                                    src={c.thumbnail_url}
                                                    alt={c.title || c.archive_item_id}
                                                    className="w-full h-full object-cover"
                                                    loading="lazy"
                                                  />
                                                ) : (
                                                  <div className="w-full h-full flex items-center justify-center text-[10px] text-gray-500">
                                                    no preview
                                                  </div>
                                                )}

                                                {/* Selected badge (AUTO / MANUAL) */}
                                                {isEffectiveSelected && (
                                                  <div
                                                    className={`absolute top-1 left-1 text-white text-[10px] font-bold px-2 py-0.5 rounded-full shadow ${
                                                      isManualSelected ? 'bg-blue-700' : 'bg-blue-600'
                                                    }`}
                                                  >
                                                    {isManualSelected ? '✓ VYBRÁNO' : '✓ AUTO'}
                                                  </div>
                                                )}

                                                {/* Badges */}
                                                <div className="absolute top-1 right-1 flex gap-1">
                                                  {c.count > 1 && (
                                                    <div className="bg-blue-600 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full">
                                                      {c.count}×
                                                    </div>
                                                  )}
                                                  {hasAnalysis && hasScore && (
                                                    <div
                                                      className={`text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
                                                        isRecommended ? 'bg-green-600' : 'bg-orange-600'
                                                      }`}
                                                      title={`LLM Score: ${(relevanceScore * 100).toFixed(0)}%`}
                                                    >
                                                      {isRecommended ? '✓' : '⚠️'} {(relevanceScore * 100).toFixed(0)}%
                                                    </div>
                                                  )}
                                                </div>

                                                {/* Text overlay warning */}
                                                {hasTextOverlay && (
                                                  <div className="absolute bottom-1 left-1 bg-red-600 text-white text-[9px] font-bold px-1.5 py-0.5 rounded">
                                                    📝 TEXT
                                                  </div>
                                                )}

                                                {/* First position badge */}
                                                {hasAnalysis && idx === 0 && (
                                                  <div
                                                    className={`absolute left-1 ${
                                                      isEffectiveSelected ? 'top-7' : 'top-1'
                                                    } bg-purple-600 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full`}
                                                  >
                                                    #1
                                                  </div>
                                                )}

                                                {/* Manual select */}
                                                <div className="absolute bottom-1 right-1">
                                                  <button
                                                    onClick={() =>
                                                      selectManifestAsset({
                                                        sceneId: sc.scene_id,
                                                        blockId: b.block_id,
                                                        archiveItemId: c.archive_item_id,
                                                      })
                                                    }
                                                    disabled={isEffectiveSelected}
                                                    className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                                                      isEffectiveSelected
                                                        ? 'bg-blue-600 text-white cursor-not-allowed'
                                                        : 'bg-white/90 text-gray-900 hover:bg-white border border-gray-200'
                                                    }`}
                                                    title={
                                                      isManualSelected
                                                        ? 'Vybráno (MANUÁL) pro tento beat'
                                                        : isAutoSelected
                                                        ? 'Aktuálně použito (AUTO)'
                                                        : 'Vybrat tento asset pro kompilaci (ruční override)'
                                                    }
                                                  >
                                                    {isManualSelected ? '✓ Vybráno' : isAutoSelected ? '✓ Auto' : 'Vybrat'}
                                                  </button>
                                                </div>
                                              </div>

                                              <div className="p-2">
                                                <div className="text-[11px] font-medium text-gray-900 line-clamp-2">
                                                  {c.title || c.archive_item_id}
                                                </div>
                                                <div className="mt-1 text-[10px] text-gray-500 font-mono">{c.source}</div>
                                                
                                                {/* Source Query (AAR episode pool query used) */}
                                                {c.source_query && (
                                                  <div className="mt-1 text-[9px] text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded border border-blue-200">
                                                    <span className="font-semibold">Query:</span> <span className="font-mono">{c.source_query}</span>
                                                  </div>
                                                )}

                                                {/* LLM Analysis */}
                                                {hasAnalysis && analysis.reasoning && (
                                                  <div className="mt-1 pt-1 border-t border-gray-200">
                                                    <div
                                                      className="text-[10px] text-gray-700 line-clamp-2"
                                                      title={analysis.reasoning}
                                                    >
                                                      💡 {analysis.reasoning}
                                                    </div>
                                                    {analysis.quality_issues && analysis.quality_issues.length > 0 && (
                                                      <div className="mt-0.5 text-[9px] text-orange-700">
                                                        ⚠️ {analysis.quality_issues.slice(0, 2).join(', ')}
                                                      </div>
                                                    )}
                                                  </div>
                                                )}
                                              </div>
                                            </div>
                                          );
                                        })}
                                      </div>

                                      <div className="mt-1 text-[10px] text-gray-500">
                                        {visualAssistantResults ? (
                                          <span className="text-green-700">
                                            ✅ Kandidáti seřazeni podle LLM Vision analýzy. #1 = nejlepší shoda.
                                          </span>
                                        ) : (
                                          <span>Pozn.: Klikni "✨ LLM vybrat nejlepší" pro automatickou analýzu thumbnailů.</span>
                                        )}
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {archiveStatsLoading && (
                <div className="mt-4 pt-4 border-t border-gray-200 text-xs text-gray-500 text-center">
                  Načítám statistiky...
                </div>
              )}
            </div>
          )}

          {/* Running Progress */}
          {videoCompilationState.status === 'running' && (
            <div className={`mb-4 p-4 bg-white border rounded ${
              archivePreviewMode ? 'border-purple-200' : 'border-blue-200'
            }`}>
              <div className="flex items-center justify-between mb-3">
                <div className="text-sm font-medium text-gray-900">
                  {archivePreviewMode ? '🔍' : '🎬'} {videoCompilationState.currentStep}
                </div>
                <div className="text-xs text-gray-600">
                  {Math.round(videoCompilationState.progress)}%
                </div>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2.5 mb-2">
                <div 
                  className={`h-2.5 rounded-full transition-all duration-300 ${
                    archivePreviewMode ? 'bg-purple-600' : 'bg-blue-600'
                  }`}
                  style={{ width: `${videoCompilationState.progress}%` }}
                ></div>
              </div>
              
              {/* Detailed progress info */}
              {videoCompilationState.cbDetails && !archivePreviewMode && (
                <div className="mt-3 p-3 bg-gray-50 rounded text-xs font-mono space-y-1">
                  <div className="flex justify-between text-gray-600">
                    <span>Fáze:</span>
                    <span className="font-semibold">
                      {videoCompilationState.cbDetails.phase === 'downloading' && '📥 Stahování'}
                      {videoCompilationState.cbDetails.phase === 'cutting' && '✂️ Střih'}
                      {videoCompilationState.cbDetails.phase === 'assembly' && '🎬 Finalizace'}
                      {videoCompilationState.cbDetails.phase === 'done' && '✅ Hotovo'}
                    </span>
                  </div>
                  
                  {videoCompilationState.cbDetails.phase === 'downloading' && (
                    <>
                      <div className="flex justify-between text-gray-600">
                        <span>Stahování:</span>
                        <span>{videoCompilationState.cbDetails.completed_downloads || 0} / {videoCompilationState.cbDetails.total_downloads || '?'}</span>
                      </div>
                      {videoCompilationState.cbDetails.current_file && (
                        <div className="text-gray-500 truncate">
                          📄 {videoCompilationState.cbDetails.current_file?.substring(0, 40)}...
                        </div>
                      )}
                      {videoCompilationState.cbDetails.speed_mbps > 0 && (
                        <div className="flex justify-between text-gray-600">
                          <span>Rychlost:</span>
                          <span>{videoCompilationState.cbDetails.speed_mbps?.toFixed(1)} MB/s</span>
                        </div>
                      )}
                    </>
                  )}
                  
                  {videoCompilationState.cbDetails.phase === 'cutting' && (
                    <div className="flex justify-between text-gray-600">
                      <span>Beaty:</span>
                      <span>{videoCompilationState.cbDetails.completed_clips || 0} / {videoCompilationState.cbDetails.total_clips || videoCompilationState.cbDetails.total_beats || '?'}</span>
                    </div>
                  )}
                  
                  {videoCompilationState.cbDetails.phase === 'assembly' && (
                    <div className="flex justify-between text-gray-600">
                      <span>Spojuji:</span>
                      <span>{videoCompilationState.cbDetails.total_clips || '?'} klipů</span>
                    </div>
                  )}
                </div>
              )}
              
              <div className="text-xs text-gray-600 text-center mt-2">
                {archivePreviewMode 
                  ? 'Rychlé hledání na archive.org - obvykle 30-60 sekund...'
                  : 'Prosím počkejte, generování může trvat 5-15 minut...'
                }
              </div>
            </div>
          )}

          {/* Error State */}
          {videoCompilationState.status === 'error' && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded">
              <div className="flex items-start gap-3">
                <div className="text-red-600 text-xl">❌</div>
                <div className="flex-1">
                  <div className="text-sm font-medium text-red-900 mb-1">Chyba při generování videa</div>
                  <div className="text-xs text-red-700">{toDisplayString(videoCompilationState.error)}</div>
                  <button
                    onClick={generateVideoCompilation}
                    className="mt-3 px-4 py-1.5 bg-red-600 text-white text-sm rounded hover:bg-red-700 transition-colors"
                  >
                    🔄 Zkusit znovu
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Success State */}
          {videoCompilationState.status === 'done' && videoCompilationState.outputPath && (
            <div className="mb-4 p-4 bg-green-50 border border-green-200 rounded">
              <div className="flex items-center gap-2 text-green-800 mb-3">
                <span className="text-xl">✅</span>
                <div className="text-sm font-medium">Video úspěšně vygenerováno!</div>
              </div>
              <div className="bg-white border border-gray-200 rounded p-3">
                <video
                  controls
                  className="w-full max-h-96 rounded"
                  src={videoCompilationState.outputPath}
                >
                  Váš prohlížeč nepodporuje přehrávání videa.
                </video>
                <div className="mt-3 flex gap-2">
                  {(() => {
                    const base = videoCompilationState.outputPath || '';
                    const filename = base.split('/').pop()?.split('?')[0];
                    const downloadUrl = filename ? `http://localhost:50000/api/video/download/${filename}` : base;
                    return (
                      <a
                        href={downloadUrl}
                        className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors text-sm"
                      >
                        📥 Stáhnout video
                      </a>
                    );
                  })()}
                  <button
                    onClick={() => {
                      // allow rerun compilation even if video already exists
                      setVideoCompilationState({
                        status: 'idle',
                        progress: 0,
                        currentStep: '',
                        error: null,
                        outputPath: null,
                      });
                      // start again immediately
                      setTimeout(() => generateVideoCompilation(), 0);
                    }}
                    className="px-4 py-2 bg-gray-900 text-white rounded hover:bg-black transition-colors text-sm"
                  >
                    🔁 Přegenerovat video
                  </button>
                  {selectedMusicFilename && (
                    <button
                      onClick={() => {
                        setVideoCompilationState({
                          status: 'idle',
                          progress: 0,
                          currentStep: '',
                          error: null,
                          outputPath: null,
                        });
                        setTimeout(() => generateVideoCompilation({ mode: 'cb_only' }), 0);
                      }}
                      className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors text-sm"
                      title="Rychlý remix hudby bez znovu-resolving assetů (CB only)"
                    >
                      🎵 Remix hudby
                    </button>
                  )}
                </div>
              </div>
              
              {/* Compilation Statistics */}
              {scriptState && (scriptState.asset_resolver_output || scriptState.compilation_builder_output) && (
                <div className="mt-4 p-3 bg-white border border-gray-200 rounded">
                  <div className="text-sm font-semibold text-gray-900 mb-2">📊 Statistiky kompilace:</div>
                  <div className="grid grid-cols-2 gap-4 text-xs">
                    {scriptState.asset_resolver_output && (
                      <>
                        <div>
                          <div className="text-gray-600">Celkem scén:</div>
                          <div className="font-mono font-semibold">{scriptState.asset_resolver_output.total_scenes || 0}</div>
                        </div>
                        <div>
                          <div className="text-gray-600">Přiřazení do scén (assets):</div>
                          <div className="font-mono font-semibold text-green-700">{scriptState.asset_resolver_output.total_assets_resolved || 0}</div>
                          {(scriptState.asset_resolver_output.pool_unique_total_assets != null ||
                            scriptState.asset_resolver_output.pool_selected_total_assets != null ||
                            scriptState.asset_resolver_output.pool_raw_total_assets != null) && (
                            <div className="mt-1 text-[11px] text-gray-700">
                              {scriptState.asset_resolver_output.pool_unique_total_assets != null && (
                                <>Unique: <span className="font-mono">{scriptState.asset_resolver_output.pool_unique_total_assets}</span></>
                              )}
                              {scriptState.asset_resolver_output.pool_selected_total_assets != null && (
                                <> · Pool: <span className="font-mono">{scriptState.asset_resolver_output.pool_selected_total_assets}</span></>
                              )}
                              {scriptState.asset_resolver_output.pool_raw_total_assets != null && (
                                <> · Raw: <span className="font-mono">{scriptState.asset_resolver_output.pool_raw_total_assets}</span></>
                              )}
                            </div>
                          )}
                        </div>
                        <div>
                          <div className="text-gray-600">Scény s assety:</div>
                          <div className="font-mono font-semibold">{scriptState.asset_resolver_output.scenes_with_assets || 0}</div>
                        </div>
                        <div>
                          <div className="text-gray-600">Scény bez assetů:</div>
                          <div className="font-mono font-semibold text-amber-600">{scriptState.asset_resolver_output.scenes_without_assets || 0}</div>
                        </div>
                      </>
                    )}
                    {scriptState.compilation_builder_output && (
                      <>
                        <div>
                          <div className="text-gray-600">Použitých klipů:</div>
                          <div className="font-mono font-semibold">{scriptState.compilation_builder_output.clips_used || 0}</div>
                        </div>
                        <div>
                          <div className="text-gray-600">Unikátních zdrojů:</div>
                          <div className="font-mono font-semibold">{scriptState.compilation_builder_output.compilation_report?.unique_assets_used || 0}</div>
                        </div>
                        {scriptState.compilation_builder_output.compilation_report?.total_subclips && (
                          <div>
                            <div className="text-gray-600">Celkem subklipů:</div>
                            <div className="font-mono font-semibold">{scriptState.compilation_builder_output.compilation_report.total_subclips}</div>
                          </div>
                        )}
                        {scriptState.compilation_builder_output.compilation_report?.reuse_ratio !== undefined && (
                          <div>
                            <div className="text-gray-600">Reuse ratio:</div>
                            <div className="font-mono font-semibold">{scriptState.compilation_builder_output.compilation_report.reuse_ratio}</div>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                  
                  {/* Asset sources breakdown (if available) */}
                  {scriptState.asset_resolver_output?.unresolved_scenes && scriptState.asset_resolver_output.unresolved_scenes.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-gray-200">
                      <div className="text-xs text-amber-700 mb-1">⚠️ Některé scény neměly dostatek videí</div>
                      <div className="text-xs text-gray-600">
                        Scény bez assetů: {scriptState.asset_resolver_output.unresolved_scenes.map(s => s.scene_id).join(', ').substring(0, 100)}
                        {scriptState.asset_resolver_output.unresolved_scenes.map(s => s.scene_id).join(', ').length > 100 && '...'}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Info box */}
          <div className="p-3 bg-blue-50 border border-blue-200 rounded">
            <div className="text-sm text-blue-900 mb-2 font-medium">📋 Jak to funguje:</div>
            <div className="text-xs text-blue-800 space-y-1">
              <div>1. ✅ Audio soubory jsou připraveny</div>
              <div>2. 🔍 AAR najde archive.org videa podle shot planu</div>
              <div>3. 🎬 CB spojí audio + videa do finální kompilace</div>
              <div>4. ⏱️ Generování trvá 5-15 minut (stahování + FFmpeg)</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default VideoProductionPipeline; 