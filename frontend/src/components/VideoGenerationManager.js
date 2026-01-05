import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toDisplayString } from '../utils/display';

const VideoGenerationManager = ({ openaiApiKey, onClose }) => {
  const [activeTab, setActiveTab] = useState('generate'); // generate, cache, settings
  const [error, setError] = useState('');
  
  // Generování video stavy
  const [videoRequest, setVideoRequest] = useState({
    topic: '',
    duration_minutes: 12,
    style: 'educational',
    target_audience: 'general',
    audio_files: []
  });
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationProgress, setGenerationProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState('');
  const [generatedVideo, setGeneratedVideo] = useState(null);
  
  // Cache stavy
  const [cacheStats, setCacheStats] = useState(null);
  const [isLoadingCache, setIsLoadingCache] = useState(false);
  const [cacheItems, setCacheItems] = useState([]);
  
  // Nastavení stavy
  const [settings, setSettings] = useState({
    kenBurnsEnabled: true,
    crossfadeEnabled: true,
    imageDuration: 8,
    crossfadeDuration: 1,
    videoQuality: 'medium'
  });

  useEffect(() => {
    loadCacheStats();
    loadCacheItems();
  }, []);

  const loadCacheStats = async () => {
    setIsLoadingCache(true);
    
    try {
      const response = await axios.get('/api/dalle-cache-stats');
      setCacheStats(response.data);
    } catch (err) {
      console.error('Chyba při načítání cache stats:', err);
    } finally {
      setIsLoadingCache(false);
    }
  };

  const loadCacheItems = async () => {
    try {
      const response = await axios.get('/api/dalle-cache-list');
      setCacheItems(response.data.items || []);
    } catch (err) {
      console.error('Chyba při načítání cache items:', err);
    }
  };

  const generateVideo = async () => {
    if (!videoRequest.topic.trim()) {
      setError('Zadejte téma videa');
      return;
    }
    if (!openaiApiKey) {
      setError('OpenAI API klíč není nastaven');
      return;
    }

    setIsGenerating(true);
    setError('');
    setGenerationProgress(0);
    setCurrentStep('');
    setGeneratedVideo(null);

    try {
      await processVideoGeneration();
    } catch (err) {
      console.error('Chyba při generování videa:', err);
      setError(err.message || 'Nepodařilo se vygenerovat video');
    } finally {
      setIsGenerating(false);
      setGenerationProgress(0);
      setCurrentStep('');
    }
  };

  const processVideoGeneration = async () => {
    const updateProgress = (step, percent) => {
      setCurrentStep(step);
      setGenerationProgress(percent);
    };

    // 1. Generování JSON plánu
    updateProgress('Generování JSON plánu videa...', 10);
    const planResponse = await axios.post('/api/visual-assistant-generate', {
      topic: videoRequest.topic,
      duration_minutes: videoRequest.duration_minutes,
      style: videoRequest.style,
      target_audience: videoRequest.target_audience
    }, { timeout: 120000 });

    if (!planResponse.data.success) {
      throw new Error(planResponse.data.error || 'Nepodařilo se vygenerovat plán');
    }

    const videoPlan = planResponse.data.data;
    updateProgress('JSON plán vygenerován', 25);

    // 2. Generování/načítání obrázků z cache
    updateProgress('Generování obrázků (DALL-E + cache)', 30);
    const imagePromises = videoPlan.content_blocks.map(async (block, index) => {
      if (!block.image_prompt) return null;

      const imageResponse = await axios.post('/api/dalle-generate-cached', {
        prompt: block.image_prompt,
        use_cache: true
      }, { timeout: 60000 });

      const progressIncrement = 40 / videoPlan.content_blocks.length;
      const newProgress = 30 + (progressIncrement * (index + 1));
      updateProgress(`Obrázek ${index + 1}/${videoPlan.content_blocks.length}`, newProgress);

      return {
        blockIndex: index,
        imageUrl: imageResponse.data.image_url,
        fromCache: imageResponse.data.from_cache
      };
    });

    const imageResults = await Promise.all(imagePromises);
    updateProgress('Všechny obrázky připraveny', 70);

    // 3. Ken Burns efekty a crossfade příprava
    updateProgress('Příprava Ken Burns efektů...', 75);
    await new Promise(resolve => setTimeout(resolve, 1000)); // Simulace

    // 4. FFmpeg video kompozice
    updateProgress('FFmpeg video kompozice...', 80);
    const videoResponse = await axios.post('/api/video-compose', {
      video_plan: videoPlan,
      images: imageResults.filter(img => img !== null),
      audio_files: videoRequest.audio_files,
      settings: settings
    }, { timeout: 300000 });

    if (!videoResponse.data.success) {
      throw new Error(videoResponse.data.error || 'Nepodařilo se sestavit video');
    }

    updateProgress('Video úspěšně vygenerováno!', 100);

    // Nastavení výsledků
    setGeneratedVideo({
      ...videoResponse.data.data,
      videoPlan,
      imageResults,
      cacheHits: imageResults.filter(img => img && img.fromCache).length,
      newImages: imageResults.filter(img => img && !img.fromCache).length
    });

    // Aktualizace cache stats
    await loadCacheStats();
  };

  const clearCache = async () => {
    if (!window.confirm('Opravdu chcete vymazat celou DALL-E cache?')) {
      return;
    }

    try {
      await axios.post('/api/dalle-cache-clear');
      await loadCacheStats();
      await loadCacheItems();
      alert('Cache byla úspěšně vymazána');
    } catch (err) {
      console.error('Chyba při mazání cache:', err);
      setError('Nepodařilo se vymazat cache');
    }
  };

  const deleteCacheItem = async (itemId) => {
    try {
      await axios.delete(`/api/dalle-cache-item/${itemId}`);
      await loadCacheStats();
      await loadCacheItems();
    } catch (err) {
      console.error('Chyba při mazání cache položky:', err);
      setError('Nepodařilo se smazat cache položku');
    }
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleString('cs-CZ');
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 w-full max-w-6xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold text-gray-800">
            🎬 Video Generation Manager
          </h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 text-2xl"
          >
            ✕
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 mb-6">
          <button
            onClick={() => setActiveTab('generate')}
            className={`px-4 py-2 font-medium ${
              activeTab === 'generate' 
                ? 'border-b-2 border-blue-500 text-blue-600' 
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            🎬 Generování
          </button>
          <button
            onClick={() => setActiveTab('cache')}
            className={`px-4 py-2 font-medium ${
              activeTab === 'cache' 
                ? 'border-b-2 border-blue-500 text-blue-600' 
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            🖼️ DALL-E Cache
          </button>
          <button
            onClick={() => setActiveTab('settings')}
            className={`px-4 py-2 font-medium ${
              activeTab === 'settings' 
                ? 'border-b-2 border-blue-500 text-blue-600' 
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            ⚙️ Nastavení
          </button>
        </div>

        {/* Error Display */}
        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
            ❌ {toDisplayString(error)}
          </div>
        )}

        {/* Generate Tab */}
        {activeTab === 'generate' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Left Column - Form */}
            <div>
              <h3 className="text-lg font-semibold text-gray-700 mb-4">
                📝 Parametry videa
              </h3>
              
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Téma videa
                  </label>
                  <input
                    type="text"
                    value={videoRequest.topic}
                    onChange={(e) => setVideoRequest(prev => ({ ...prev, topic: e.target.value }))}
                    placeholder="Například: Historie automobilů, Vesmírné technologie..."
                    className="w-full border border-gray-300 rounded px-3 py-2"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Délka (minuty)
                    </label>
                    <input
                      type="number"
                      value={videoRequest.duration_minutes}
                      onChange={(e) => setVideoRequest(prev => ({ ...prev, duration_minutes: parseInt(e.target.value) }))}
                      min="1"
                      max="60"
                      className="w-full border border-gray-300 rounded px-3 py-2"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Styl
                    </label>
                    <select
                      value={videoRequest.style}
                      onChange={(e) => setVideoRequest(prev => ({ ...prev, style: e.target.value }))}
                      className="w-full border border-gray-300 rounded px-3 py-2"
                    >
                      <option value="educational">Vzdělávací</option>
                      <option value="entertaining">Zábavný</option>
                      <option value="documentary">Dokumentární</option>
                      <option value="casual">Neformální</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Cílová skupina
                  </label>
                  <select
                    value={videoRequest.target_audience}
                    onChange={(e) => setVideoRequest(prev => ({ ...prev, target_audience: e.target.value }))}
                    className="w-full border border-gray-300 rounded px-3 py-2"
                  >
                    <option value="general">Obecná</option>
                    <option value="kids">Děti</option>
                    <option value="teens">Teenageři</option>
                    <option value="adults">Dospělí</option>
                    <option value="experts">Experti</option>
                  </select>
                </div>

                <button
                  onClick={generateVideo}
                  disabled={isGenerating || !openaiApiKey}
                  className="w-full bg-blue-500 text-white py-3 px-4 rounded hover:bg-blue-600 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
                >
                  {isGenerating ? '🔄 Generuji video...' : '🚀 Vygenerovat video'}
                </button>
              </div>

              {/* Progress */}
              {isGenerating && (
                <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
                  <h4 className="font-semibold text-blue-800 mb-2">
                    🔄 Probíhá generování...
                  </h4>
                  <div className="w-full bg-blue-200 rounded-full h-2 mb-2">
                    <div 
                      className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${generationProgress}%` }}
                    ></div>
                  </div>
                  <div className="text-sm text-blue-700">
                    {currentStep} ({Math.round(generationProgress)}%)
                  </div>
                </div>
              )}
            </div>

            {/* Right Column - Results */}
            <div>
              <h3 className="text-lg font-semibold text-gray-700 mb-4">
                📹 Výsledek
              </h3>
              
              {generatedVideo ? (
                <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                  <h4 className="font-semibold text-green-800 mb-3">
                    ✅ Video úspěšně vygenerováno
                  </h4>
                  
                  <div className="space-y-3">
                    <div className="bg-white rounded border p-3">
                      <h5 className="font-medium text-gray-800 mb-2">📊 Statistiky</h5>
                      <div className="text-sm space-y-1">
                        <div>
                          <span className="font-medium">Výstupní soubor:</span> {generatedVideo.output_file}
                        </div>
                        <div>
                          <span className="font-medium">Obsahové bloky:</span> {generatedVideo.videoPlan?.content_blocks?.length || 0}
                        </div>
                        <div>
                          <span className="font-medium">Cache hits:</span> 
                          <span className="text-green-600 ml-1">{generatedVideo.cacheHits}</span>
                        </div>
                        <div>
                          <span className="font-medium">Nové obrázky:</span> 
                          <span className="text-blue-600 ml-1">{generatedVideo.newImages}</span>
                        </div>
                      </div>
                    </div>

                    <div className="bg-white rounded border p-3">
                      <h5 className="font-medium text-gray-800 mb-2">🎬 Technické detaily</h5>
                      <div className="text-sm space-y-1">
                        <div>Ken Burns efekty: {settings.kenBurnsEnabled ? '✅ Zapnuto' : '❌ Vypnuto'}</div>
                        <div>Crossfade přechody: {settings.crossfadeEnabled ? '✅ Zapnuto' : '❌ Vypnuto'}</div>
                        <div>Délka obrázku: {settings.imageDuration}s</div>
                        <div>Délka přechodu: {settings.crossfadeDuration}s</div>
                      </div>
                    </div>

                    <button
                      onClick={() => {
                        // Implementace stažení videa
                        window.open(`/api/download-video/${generatedVideo.output_file}`, '_blank');
                      }}
                      className="w-full bg-green-500 text-white py-2 px-4 rounded hover:bg-green-600 transition-colors"
                    >
                      📥 Stáhnout video
                    </button>
                  </div>
                </div>
              ) : (
                <div className="bg-gray-50 border border-gray-200 rounded-lg p-6 text-center text-gray-500">
                  <div className="text-lg mb-2">📹</div>
                  <div>Vygenerované video se zobrazí zde</div>
                  <div className="text-sm mt-2">Vyplňte parametry a klikněte na "Vygenerovat video"</div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Cache Tab */}
        {activeTab === 'cache' && (
          <div>
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-lg font-semibold text-gray-700">
                🖼️ DALL-E Cache Management
              </h3>
              <button
                onClick={clearCache}
                className="bg-red-500 text-white px-4 py-2 rounded hover:bg-red-600 transition-colors"
              >
                🗑️ Vymazat celou cache
              </button>
            </div>

            {/* Cache Stats */}
            {isLoadingCache ? (
              <div className="text-center py-4">🔄 Načítám cache statistiky...</div>
            ) : cacheStats ? (
              <div className="grid grid-cols-4 gap-4 mb-6">
                <div className="bg-blue-100 rounded-lg p-4 text-center">
                  <div className="text-2xl font-bold text-blue-800">{cacheStats.total_images}</div>
                  <div className="text-sm text-blue-600">Obrázků</div>
                </div>
                <div className="bg-green-100 rounded-lg p-4 text-center">
                  <div className="text-2xl font-bold text-green-800">{formatFileSize(cacheStats.total_size)}</div>
                  <div className="text-sm text-green-600">Celková velikost</div>
                </div>
                <div className="bg-purple-100 rounded-lg p-4 text-center">
                  <div className="text-2xl font-bold text-purple-800">{cacheStats.cache_hits || 0}</div>
                  <div className="text-sm text-purple-600">Cache hits</div>
                </div>
                <div className="bg-orange-100 rounded-lg p-4 text-center">
                  <div className="text-2xl font-bold text-orange-800">{Math.round((cacheStats.cache_hits || 0) / Math.max(cacheStats.total_requests || 1, 1) * 100)}%</div>
                  <div className="text-sm text-orange-600">Úspěšnost</div>
                </div>
              </div>
            ) : null}

            {/* Cache Items */}
            <div className="space-y-4">
              {cacheItems.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  📭 Cache je prázdná
                </div>
              ) : (
                cacheItems.map((item, index) => (
                  <div key={index} className="border border-gray-200 rounded-lg p-4 flex items-start gap-4">
                    {/* Image Preview */}
                    <div className="flex-shrink-0">
                      <img 
                        src={item.image_url} 
                        alt="Cache preview"
                        className="w-20 h-20 object-cover rounded border"
                      />
                    </div>

                    {/* Item Details */}
                    <div className="flex-1">
                      <div className="text-sm space-y-1">
                        <div>
                          <span className="font-medium">Prompt:</span> {item.prompt}
                        </div>
                        <div>
                          <span className="font-medium">Hash:</span> {item.hash}
                        </div>
                        <div>
                          <span className="font-medium">Velikost:</span> {formatFileSize(item.size)}
                        </div>
                        <div>
                          <span className="font-medium">Vytvořeno:</span> {formatDate(item.created_at)}
                        </div>
                        <div>
                          <span className="font-medium">Použití:</span> {item.usage_count || 0}x
                        </div>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex-shrink-0">
                      <button
                        onClick={() => deleteCacheItem(item.id)}
                        className="text-red-500 hover:text-red-700 p-1"
                        title="Smazat z cache"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* Settings Tab */}
        {activeTab === 'settings' && (
          <div>
            <h3 className="text-lg font-semibold text-gray-700 mb-6">
              ⚙️ Nastavení video generování
            </h3>

            <div className="space-y-6">
              {/* Video Effects */}
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                <h4 className="font-semibold text-gray-800 mb-3">🎬 Video efekty</h4>
                
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium text-gray-700">Ken Burns efekty</div>
                      <div className="text-sm text-gray-500">Zoom a pan efekty pro dynamičtější obraz</div>
                    </div>
                    <label className="switch">
                      <input
                        type="checkbox"
                        checked={settings.kenBurnsEnabled}
                        onChange={(e) => setSettings(prev => ({ ...prev, kenBurnsEnabled: e.target.checked }))}
                      />
                      <span className="slider"></span>
                    </label>
                  </div>

                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium text-gray-700">Crossfade přechody</div>
                      <div className="text-sm text-gray-500">Plynulé přechody mezi obrázky</div>
                    </div>
                    <label className="switch">
                      <input
                        type="checkbox"
                        checked={settings.crossfadeEnabled}
                        onChange={(e) => setSettings(prev => ({ ...prev, crossfadeEnabled: e.target.checked }))}
                      />
                      <span className="slider"></span>
                    </label>
                  </div>
                </div>
              </div>

              {/* Timing Settings */}
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                <h4 className="font-semibold text-gray-800 mb-3">⏱️ Časování</h4>
                
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Délka zobrazení obrázku (sekundy)
                    </label>
                    <input
                      type="number"
                      value={settings.imageDuration}
                      onChange={(e) => setSettings(prev => ({ ...prev, imageDuration: parseInt(e.target.value) }))}
                      min="3"
                      max="20"
                      className="w-full border border-gray-300 rounded px-3 py-2"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Délka crossfade (sekundy)
                    </label>
                    <input
                      type="number"
                      value={settings.crossfadeDuration}
                      onChange={(e) => setSettings(prev => ({ ...prev, crossfadeDuration: parseFloat(e.target.value) }))}
                      min="0.5"
                      max="3"
                      step="0.1"
                      className="w-full border border-gray-300 rounded px-3 py-2"
                    />
                  </div>
                </div>
              </div>

              {/* Quality Settings */}
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                <h4 className="font-semibold text-gray-800 mb-3">🎥 Kvalita a výkon</h4>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Kvalita videa
                  </label>
                  <select
                    value={settings.videoQuality}
                    onChange={(e) => setSettings(prev => ({ ...prev, videoQuality: e.target.value }))}
                    className="w-full border border-gray-300 rounded px-3 py-2"
                  >
                    <option value="low">Nízká (rychlé renderování)</option>
                    <option value="medium">Střední (vyvážená)</option>
                    <option value="high">Vysoká (pomalé renderování)</option>
                  </select>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* CSS pro switch */}
      <style jsx>{`
        .switch {
          position: relative;
          display: inline-block;
          width: 48px;
          height: 24px;
        }

        .switch input {
          opacity: 0;
          width: 0;
          height: 0;
        }

        .slider {
          position: absolute;
          cursor: pointer;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background-color: #ccc;
          transition: .4s;
          border-radius: 24px;
        }

        .slider:before {
          position: absolute;
          content: "";
          height: 18px;
          width: 18px;
          left: 3px;
          bottom: 3px;
          background-color: white;
          transition: .4s;
          border-radius: 50%;
        }

        input:checked + .slider {
          background-color: #2196F3;
        }

        input:checked + .slider:before {
          transform: translateX(24px);
        }
      `}</style>
    </div>
  );
};

export default VideoGenerationManager; 