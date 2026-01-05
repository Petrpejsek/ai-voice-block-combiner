import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toDisplayString } from '../utils/display';

const VisualAssistantManager = ({ openaiApiKey, onClose }) => {
  const [visualAssistantConfig, setVisualAssistantConfig] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  
  // Test generování stavy
  const [testPrompt, setTestPrompt] = useState({
    topic: 'cars',
    duration_minutes: 12,
    style: 'educational',
    target_audience: 'general'
  });
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatedPlan, setGeneratedPlan] = useState(null);
  
  // DALL-E cache stavy
  const [cacheStats, setCacheStats] = useState(null);
  const [isLoadingCache, setIsLoadingCache] = useState(false);

  useEffect(() => {
    loadVisualAssistantConfig();
    loadCacheStats();
  }, []);

  const loadVisualAssistantConfig = async () => {
    setIsLoading(true);
    setError('');
    
    try {
      const response = await axios.get('/api/visual-assistant-config');
      setVisualAssistantConfig(response.data);
    } catch (err) {
      console.error('Chyba při načítání Visual Assistant config:', err);
      setError('Nepodařilo se načíst konfiguraci Visual Assistant');
    } finally {
      setIsLoading(false);
    }
  };

  const loadCacheStats = async () => {
    setIsLoadingCache(true);
    
    try {
      const response = await axios.get('/api/dalle-cache-stats');
      setCacheStats(response.data);
    } catch (err) {
      console.error('Chyba při načítání DALL-E cache stats:', err);
      // Cache stats nejsou kritické, takže nezobrazujeme chybu
    } finally {
      setIsLoadingCache(false);
    }
  };

  const testVisualAssistant = async () => {
    if (!openaiApiKey) {
      setError('OpenAI API klíč není nastaven');
      return;
    }

    setIsGenerating(true);
    setError('');
    setGeneratedPlan(null);

    try {
      const response = await axios.post('/api/visual-assistant-generate', {
        topic: testPrompt.topic,
        duration_minutes: testPrompt.duration_minutes,
        style: testPrompt.style,
        target_audience: testPrompt.target_audience
      }, { 
        timeout: 120000,
        headers: {
          'Authorization': `Bearer ${openaiApiKey}`
        }
      });

      if (response.data.success) {
        setGeneratedPlan(response.data.data);
      } else {
        setError(response.data.error || 'Nepodařilo se vygenerovat plán');
      }
    } catch (err) {
      console.error('Chyba při testování Visual Assistant:', err);
      setError(err.response?.data?.error || 'Chyba při komunikaci s Visual Assistant');
    } finally {
      setIsGenerating(false);
    }
  };

  const clearCache = async () => {
    try {
      await axios.post('/api/dalle-cache-clear');
      await loadCacheStats();
      alert('DALL-E cache byla vymazána');
    } catch (err) {
      console.error('Chyba při mazání cache:', err);
      setError('Nepodařilo se vymazat cache');
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
      <div className="bg-white rounded-lg p-6 w-full max-w-4xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold text-gray-800">
            🎨 Visual Assistant Management
          </h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 text-2xl"
          >
            ✕
          </button>
        </div>

        {/* Error Display */}
        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
            ❌ {toDisplayString(error)}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left Column - Configuration */}
          <div>
            <h3 className="text-lg font-semibold text-gray-700 mb-4">
              ⚙️ Konfigurace
            </h3>
            
            {/* Visual Assistant Info */}
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
              <h4 className="font-semibold text-blue-800 mb-2">Visual Assistant</h4>
              {isLoading ? (
                <div className="text-blue-600">🔄 Načítám...</div>
              ) : visualAssistantConfig ? (
                <div className="space-y-2 text-sm">
                  <div>
                    <span className="font-medium">ID:</span> {visualAssistantConfig.assistant_id}
                  </div>
                  <div>
                    <span className="font-medium">Název:</span> {visualAssistantConfig.name}
                  </div>
                  <div>
                    <span className="font-medium">Model:</span> {visualAssistantConfig.model}
                  </div>
                  <div>
                    <span className="font-medium">Status:</span> 
                    <span className="text-green-600 ml-1">✅ Aktivní</span>
                  </div>
                </div>
              ) : (
                <div className="text-red-600">❌ Nepodařilo se načíst konfiguraci</div>
              )}
            </div>

            {/* DALL-E Cache Stats */}
            <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
              <h4 className="font-semibold text-green-800 mb-2">
                🖼️ DALL-E Cache Statistiky
              </h4>
              {isLoadingCache ? (
                <div className="text-green-600">🔄 Načítám...</div>
              ) : cacheStats ? (
                <div className="space-y-2 text-sm">
                  <div>
                    <span className="font-medium">Počet obrázků:</span> {cacheStats.total_images}
                  </div>
                  <div>
                    <span className="font-medium">Celková velikost:</span> {formatFileSize(cacheStats.total_size)}
                  </div>
                  <div>
                    <span className="font-medium">Nejstarší:</span> {cacheStats.oldest_image ? formatDate(cacheStats.oldest_image) : 'N/A'}
                  </div>
                  <div>
                    <span className="font-medium">Nejnovější:</span> {cacheStats.newest_image ? formatDate(cacheStats.newest_image) : 'N/A'}
                  </div>
                  <div className="pt-2">
                    <button
                      onClick={clearCache}
                      className="bg-red-500 text-white px-3 py-1 rounded text-sm hover:bg-red-600 transition-colors"
                    >
                      🗑️ Vymazat cache
                    </button>
                  </div>
                </div>
              ) : (
                <div className="text-gray-600">📊 Cache statistiky nejsou dostupné</div>
              )}
            </div>

            {/* Test Parameters */}
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
              <h4 className="font-semibold text-gray-800 mb-3">🧪 Test Parametry</h4>
              
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Téma
                  </label>
                  <input
                    type="text"
                    value={testPrompt.topic}
                    onChange={(e) => setTestPrompt(prev => ({ ...prev, topic: e.target.value }))}
                    className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
                    placeholder="Například: cars, space, history..."
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Délka (minuty)
                  </label>
                  <input
                    type="number"
                    value={testPrompt.duration_minutes}
                    onChange={(e) => setTestPrompt(prev => ({ ...prev, duration_minutes: parseInt(e.target.value) }))}
                    min="1"
                    max="60"
                    className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Styl
                  </label>
                  <select
                    value={testPrompt.style}
                    onChange={(e) => setTestPrompt(prev => ({ ...prev, style: e.target.value }))}
                    className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
                  >
                    <option value="educational">Vzdělávací</option>
                    <option value="entertaining">Zábavný</option>
                    <option value="documentary">Dokumentární</option>
                    <option value="casual">Neformální</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Cílová skupina
                  </label>
                  <select
                    value={testPrompt.target_audience}
                    onChange={(e) => setTestPrompt(prev => ({ ...prev, target_audience: e.target.value }))}
                    className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
                  >
                    <option value="general">Obecná</option>
                    <option value="kids">Děti</option>
                    <option value="teens">Teenageři</option>
                    <option value="adults">Dospělí</option>
                    <option value="experts">Experti</option>
                  </select>
                </div>

                <button
                  onClick={testVisualAssistant}
                  disabled={isGenerating || !openaiApiKey}
                  className="w-full bg-blue-500 text-white py-2 px-4 rounded hover:bg-blue-600 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
                >
                  {isGenerating ? '🔄 Generuji...' : '🚀 Test Visual Assistant'}
                </button>
              </div>
            </div>
          </div>

          {/* Right Column - Generated Plan */}
          <div>
            <h3 className="text-lg font-semibold text-gray-700 mb-4">
              📋 Vygenerovaný Plán
            </h3>
            
            {isGenerating ? (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-6 text-center">
                <div className="text-blue-600 text-lg mb-2">🔄 Generuji JSON plán...</div>
                <div className="text-blue-500 text-sm">Může to trvat až 2 minuty</div>
              </div>
            ) : generatedPlan ? (
              <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                <h4 className="font-semibold text-green-800 mb-3">
                  ✅ JSON Plán Úspěšně Vygenerován
                </h4>
                
                {/* Plan Summary */}
                <div className="bg-white rounded border p-3 mb-4">
                  <h5 className="font-medium text-gray-800 mb-2">📊 Přehled</h5>
                  <div className="text-sm space-y-1">
                    <div>
                      <span className="font-medium">Téma:</span> {generatedPlan.topic || testPrompt.topic}
                    </div>
                    <div>
                      <span className="font-medium">Délka:</span> {generatedPlan.duration || testPrompt.duration_minutes} min
                    </div>
                    <div>
                      <span className="font-medium">Bloky:</span> {generatedPlan.content_blocks?.length || 0}
                    </div>
                    <div>
                      <span className="font-medium">Obrázky:</span> {generatedPlan.total_images || 0}
                    </div>
                  </div>
                </div>

                {/* Content Blocks */}
                {generatedPlan.content_blocks && (
                  <div className="bg-white rounded border p-3 mb-4">
                    <h5 className="font-medium text-gray-800 mb-2">
                      🎬 Obsahové Bloky ({generatedPlan.content_blocks.length})
                    </h5>
                    <div className="space-y-2 max-h-48 overflow-y-auto">
                      {generatedPlan.content_blocks.map((block, index) => (
                        <div key={index} className="bg-gray-50 rounded p-2 text-sm">
                          <div className="font-medium text-gray-700">
                            Blok {index + 1}: {block.title || 'Bez názvu'}
                          </div>
                          <div className="text-gray-600">
                            ⏱️ {block.duration}s | 🖼️ {block.image_prompt ? 'Má obrázek' : 'Bez obrázku'}
                          </div>
                          {block.image_prompt && (
                            <div className="text-xs text-blue-600 mt-1">
                              📸 {block.image_prompt.substring(0, 80)}...
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Raw JSON */}
                <div className="bg-white rounded border p-3">
                  <h5 className="font-medium text-gray-800 mb-2">📄 Raw JSON</h5>
                  <pre className="text-xs bg-gray-100 rounded p-2 overflow-x-auto">
                    {JSON.stringify(generatedPlan, null, 2)}
                  </pre>
                </div>
              </div>
            ) : (
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-6 text-center text-gray-500">
                <div className="text-lg mb-2">📋</div>
                <div>Vygenerovaný plán se zobrazí zde</div>
                <div className="text-sm mt-2">Klikněte na "Test Visual Assistant" pro generování</div>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="mt-6 pt-4 border-t border-gray-200">
          <div className="text-sm text-gray-600">
            <strong>📖 Co dělá Visual Assistant:</strong>
            <ul className="list-disc list-inside mt-2 space-y-1">
              <li>Analyzuje téma a vytváří strukturovaný JSON plán videa</li>
              <li>Definuje obsahové bloky s časováním a DALL-E prompty</li>
              <li>Optimalizuje pro Ken Burns efekty a crossfade přechody</li>
              <li>Využívá cache systém pro reuse obrázků a snížení nákladů</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

export default VisualAssistantManager; 