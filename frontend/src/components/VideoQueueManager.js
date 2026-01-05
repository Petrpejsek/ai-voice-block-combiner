import React, { useState, useEffect } from 'react';
import { toDisplayString } from '../utils/display';

const VideoQueueManager = ({ openaiApiKey }) => {
  const [videoQueue, setVideoQueue] = useState(() => {
    const saved = localStorage.getItem('videoProductionQueue');
    return saved ? JSON.parse(saved) : [];
  });
  
  const [isProcessing, setIsProcessing] = useState(false);
  const [currentItem, setCurrentItem] = useState(null);
  
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState('');
  const [error, setError] = useState('');

  // Automatické ukládání do localStorage (ZACHOVÁNO)
  useEffect(() => {
    localStorage.setItem('videoProductionQueue', JSON.stringify(videoQueue));
  }, [videoQueue]);

  // Automatické zpracování - upraveno s dependencemi
  useEffect(() => {
    if (!isProcessing) {
      const pendingItem = videoQueue.find(item => item.status === 'pending');
      if (pendingItem) {
        processNextItem();
      }
    }
  }, [videoQueue, isProcessing]); // Přidány dependencies

  const processNextItem = async () => {
    if (isProcessing) return;

    const pendingItem = videoQueue.find(item => item.status === 'pending');
    if (!pendingItem) return;

    setCurrentItem(pendingItem);
    setIsProcessing(true);
    setError('');
    setProgress(0);
    setCurrentStep('');

    // Označit jako zpracovává se
    setVideoQueue(prev => prev.map(item => 
      item.id === pendingItem.id ? { 
        ...item, 
        status: 'processing',
        progress: 0,
        currentStep: 'Inicializace...'
      } : item
    ));

    try {
      await processVideoProduction(pendingItem);
      
      // Úspěch
      setVideoQueue(prev => prev.map(item => 
        item.id === pendingItem.id ? { 
          ...item, 
          status: 'completed',
          progress: 100,
          currentStep: 'Dokončeno',
          completedAt: new Date()
        } : item
      ));

    } catch (err) {
      console.error('Chyba při video produkci:', err);
      
      setVideoQueue(prev => prev.map(item => 
        item.id === pendingItem.id ? { 
          ...item, 
          status: 'error',
          error: err.message,
          currentStep: 'Chyba',
          completedAt: new Date()
        } : item
      ));
      
      setError(err.message);
    }

    setIsProcessing(false);
    setCurrentItem(null);
    setProgress(0);
    setCurrentStep('');
  };

  const processVideoProduction = async (item) => {
    const updateProgress = (step, percent, details = '') => {
      setCurrentStep(step);
      setProgress(percent);
      
      // Aktualizovat i v queue
      setVideoQueue(prev => prev.map(queueItem => 
        queueItem.id === item.id ? { 
          ...queueItem, 
          progress: percent,
          currentStep: step
        } : queueItem
      ));
    };

    updateProgress('Příprava video produkce', 10, 'Načítám data...');
    
    // Simulace video produkce
    if (!item.voiceFiles || item.voiceFiles.length === 0) {
      throw new Error('Chybí hlasové soubory pro video produkci');
    }

    updateProgress('Analýza audio souborů', 20, `Zpracovávám ${item.voiceFiles.length} souborů...`);
    await new Promise(resolve => setTimeout(resolve, 1000));

    updateProgress('Generování JSON plánu', 40, 'Vytvářím plán videa...');
    await new Promise(resolve => setTimeout(resolve, 1500));

    updateProgress('DALL-E generování obrázků', 60, 'Vytvářím vizuální obsah...');
    await new Promise(resolve => setTimeout(resolve, 2000));

    updateProgress('FFmpeg video kompozice', 80, 'Skládám finální video...');
    await new Promise(resolve => setTimeout(resolve, 2500));

    updateProgress('Finalizace', 95, 'Ukládám výsledek...');
    await new Promise(resolve => setTimeout(resolve, 500));

    // Simulace výstupního souboru
    const outputFile = `video_${item.id}_${Date.now()}.mp4`;
    
    setVideoQueue(prev => prev.map(queueItem => 
      queueItem.id === item.id ? { 
        ...queueItem, 
        outputFile: outputFile
      } : queueItem
    ));

    updateProgress('Dokončeno', 100, 'Video úspěšně vytvořeno!');
  };

  const removeFromQueue = (itemId) => {
    setVideoQueue(prev => prev.filter(item => item.id !== itemId));
  };

  const clearCompleted = () => {
    setVideoQueue(prev => prev.filter(item => item.status !== 'completed'));
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'pending': return '⏳';
      case 'processing': return '🔄';
      case 'completed': return '✅';
      case 'error': return '❌';
      default: return '⏳';
    }
  };

  const formatDate = (date) => {
    return new Date(date).toLocaleString('cs-CZ');
  };

  const pendingItems = videoQueue.filter(item => item.status === 'pending');
  const processingItems = videoQueue.filter(item => item.status === 'processing');
  const completedItems = videoQueue.filter(item => item.status === 'completed');
  const errorItems = videoQueue.filter(item => item.status === 'error');

  return (
    <div className="video-queue-manager bg-white p-6 rounded-lg shadow-lg">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-800">
          📹 Video Produkce Fronta
        </h2>
        <div className="flex gap-2">
          <span className="bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-sm">
            Ve frontě: {pendingItems.length + processingItems.length}
          </span>
          <span className="bg-green-100 text-green-800 px-3 py-1 rounded-full text-sm">
            Dokončeno: {completedItems.length}
          </span>
          {videoQueue.length > 0 && (
            <button
              onClick={clearCompleted}
              className="bg-gray-500 text-white px-3 py-1 rounded text-sm hover:bg-gray-600 transition-colors"
            >
              🗑️ Vymazat dokončené
            </button>
          )}
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
          ❌ {toDisplayString(error)}
        </div>
      )}

      {/* Current Processing Item */}
      {isProcessing && currentItem && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
          <h3 className="font-semibold text-blue-800 mb-2">
            🔄 Zpracovává se: {currentItem.title}
          </h3>
          <div className="w-full bg-blue-200 rounded-full h-2 mb-2">
            <div 
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            ></div>
          </div>
          <div className="text-sm text-blue-700">
            {currentStep} ({Math.round(progress)}%)
          </div>
        </div>
      )}

      {/* Queue Content */}
      {videoQueue.length === 0 ? (
        <div className="text-center py-8 text-gray-500">
          📹 Video fronta je prázdná
          <div className="text-sm mt-2">
            Dokončené podcast úkoly s tlačítkem "Vytvořit video" se zde automaticky objeví
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Pending Items */}
          {pendingItems.length > 0 && (
            <div>
              <h3 className="text-lg font-semibold text-gray-700 mb-3">
                ⏳ Ve frontě ({pendingItems.length})
              </h3>
              {pendingItems.map((item) => (
                <div key={item.id} className="border border-yellow-200 bg-yellow-50 rounded-lg p-4 mb-3">
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-lg">{getStatusIcon(item.status)}</span>
                        <span className="font-semibold text-gray-800">
                          {item.title}
                        </span>
                      </div>
                      <div className="text-sm text-gray-600 space-y-1">
                        <div>📅 Přidáno: {formatDate(item.createdAt)}</div>
                        <div>🎵 Audio soubory: {item.voiceFiles.length}</div>
                        <div>📝 Segmenty: {item.segments.length}</div>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => removeFromQueue(item.id)}
                        className="text-red-500 hover:text-red-700 p-1"
                        title="Odstranit z fronty"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Processing Items */}
          {processingItems.length > 0 && (
            <div>
              <h3 className="text-lg font-semibold text-gray-700 mb-3">
                🔄 Zpracovává se ({processingItems.length})
              </h3>
              {processingItems.map((item) => (
                <div key={item.id} className="border border-blue-200 bg-blue-50 rounded-lg p-4 mb-3">
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-lg">{getStatusIcon(item.status)}</span>
                        <span className="font-semibold text-gray-800">
                          {item.title}
                        </span>
                      </div>
                      <div className="w-full bg-blue-200 rounded-full h-2 mb-2">
                        <div 
                          className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                          style={{ width: `${item.progress}%` }}
                        ></div>
                      </div>
                      <div className="text-sm text-blue-700">
                        {item.currentStep} ({Math.round(item.progress)}%)
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Completed Items */}
          {completedItems.length > 0 && (
            <div>
              <h3 className="text-lg font-semibold text-gray-700 mb-3">
                ✅ Dokončeno ({completedItems.length})
              </h3>
              {completedItems.map((item) => (
                <div key={item.id} className="border border-green-200 bg-green-50 rounded-lg p-4 mb-3">
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-lg">{getStatusIcon(item.status)}</span>
                        <span className="font-semibold text-gray-800">
                          {item.title}
                        </span>
                      </div>
                      <div className="text-sm text-gray-600 space-y-1">
                        <div>📅 Dokončeno: {formatDate(item.completedAt)}</div>
                        <div>🎵 Audio soubory: {item.voiceFiles.length}</div>
                        <div>📝 Segmenty: {item.segments.length}</div>
                        {item.outputFile && (
                          <div>📹 Video soubor: {item.outputFile}</div>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      {item.outputFile && (
                        <button
                          onClick={() => {
                            // Implementace stažení video souboru
                            console.log('Stahování:', item.outputFile);
                          }}
                          className="bg-green-500 text-white px-3 py-1 rounded text-sm hover:bg-green-600 transition-colors"
                        >
                          📥 Stáhnout
                        </button>
                      )}
                      <button
                        onClick={() => removeFromQueue(item.id)}
                        className="text-red-500 hover:text-red-700 p-1"
                        title="Odstranit z fronty"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Error Items */}
          {errorItems.length > 0 && (
            <div>
              <h3 className="text-lg font-semibold text-gray-700 mb-3">
                ❌ Chyby ({errorItems.length})
              </h3>
              {errorItems.map((item) => (
                <div key={item.id} className="border border-red-200 bg-red-50 rounded-lg p-4 mb-3">
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-lg">{getStatusIcon(item.status)}</span>
                        <span className="font-semibold text-gray-800">
                          {item.title}
                        </span>
                      </div>
                      <div className="text-sm text-gray-600 space-y-1">
                        <div>📅 Selhalo: {formatDate(item.completedAt)}</div>
                        <div className="text-red-600">❌ {item.error}</div>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => {
                          // Restart úkolu
                          setVideoQueue(prev => prev.map(queueItem => 
                            queueItem.id === item.id ? { 
                              ...queueItem, 
                              status: 'pending',
                              error: null,
                              progress: 0,
                              currentStep: ''
                            } : queueItem
                          ));
                        }}
                        className="bg-yellow-500 text-white px-3 py-1 rounded text-sm hover:bg-yellow-600 transition-colors"
                      >
                        🔄 Opakovat
                      </button>
                      <button
                        onClick={() => removeFromQueue(item.id)}
                        className="text-red-500 hover:text-red-700 p-1"
                        title="Odstranit z fronty"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Statistics */}
      {videoQueue.length > 0 && (
        <div className="mt-6 pt-4 border-t border-gray-200">
          <div className="grid grid-cols-4 gap-4 text-center">
            <div className="bg-yellow-100 rounded-lg p-3">
              <div className="text-2xl font-bold text-yellow-800">{pendingItems.length}</div>
              <div className="text-sm text-yellow-600">Ve frontě</div>
            </div>
            <div className="bg-blue-100 rounded-lg p-3">
              <div className="text-2xl font-bold text-blue-800">{processingItems.length}</div>
              <div className="text-sm text-blue-600">Zpracovává se</div>
            </div>
            <div className="bg-green-100 rounded-lg p-3">
              <div className="text-2xl font-bold text-green-800">{completedItems.length}</div>
              <div className="text-sm text-green-600">Dokončeno</div>
            </div>
            <div className="bg-red-100 rounded-lg p-3">
              <div className="text-2xl font-bold text-red-800">{errorItems.length}</div>
              <div className="text-sm text-red-600">Chyby</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default VideoQueueManager; 