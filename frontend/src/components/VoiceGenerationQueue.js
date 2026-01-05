import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toDisplayString } from '../utils/display';

const VoiceGenerationQueue = React.forwardRef(({ 
  elevenlabsApiKey, 
  onVoicesGenerated,
  onApiKeyRequired 
}, ref) => {
  const [voiceTasks, setVoiceTasks] = useState([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentStep, setCurrentStep] = useState('');
  const [progress, setProgress] = useState(0);
  const [currentDetails, setCurrentDetails] = useState('');
  const [error, setError] = useState('');
  const [cancelRequested, setCancelRequested] = useState(false);
  
  // Detail modal stavy
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [selectedTask, setSelectedTask] = useState(null);

  // Načte úkoly z localStorage při spuštění
  useEffect(() => {
    try {
      const saved = localStorage.getItem('voiceTasks');
      if (saved) {
        const tasks = JSON.parse(saved);
        setVoiceTasks(tasks);
        console.log('📋 Načteno z localStorage:', tasks.length, 'hlasových úkolů');
      }
    } catch (error) {
      console.error('Chyba při načítání hlasových úkolů:', error);
    }
  }, []);

  // Uloží úkoly do localStorage při změně
  useEffect(() => {
    if (voiceTasks.length > 0) {
      try {
        localStorage.setItem('voiceTasks', JSON.stringify(voiceTasks));
        console.log('💾 Uloženo do localStorage:', voiceTasks.length, 'hlasových úkolů');
      } catch (error) {
        console.error('Chyba při ukládání hlasových úkolů:', error);
      }
    }
  }, [voiceTasks]);

  // Automaticky spustí zpracování když je úkol přidán
  useEffect(() => {
    const waitingTask = voiceTasks.find(task => task.status === 'waiting');
    if (waitingTask && !isGenerating && elevenlabsApiKey) {
      console.log('🚀 Automaticky spouštím zpracování úkolu:', waitingTask.projectName);
      processNextTask();
    }
  }, [voiceTasks, isGenerating, elevenlabsApiKey]);

  // Přidá nový úkol do fronty
  const addVoiceTask = (finalProject) => {
    console.log('🎤 Přidávám nový hlasový úkol:', finalProject.title);

    // Převede video projekt na ElevenLabs JSON formát
    const elevenlabsJson = {};
    let totalBlocks = 0;

    if (finalProject?.segments) {
      finalProject.segments.forEach((segment) => {
        const segmentContent = segment.content || {};
        Object.entries(segmentContent).forEach(([blockName, blockData]) => {
          if (blockData && blockData.text && blockData.voice_id) {
            elevenlabsJson[blockName] = {
              text: blockData.text,
              voice_id: blockData.voice_id
            };
            totalBlocks++;
          }
        });
      });
    }

    if (totalBlocks === 0) {
      setError('Projekt nemá žádné platné hlasové bloky!');
      return;
    }

    const newTask = {
      id: `voice_${Date.now()}`,
      projectName: finalProject.title || 'Neznámý projekt',
      projectId: finalProject.id,
      elevenlabsJson,
      totalBlocks,
      status: 'waiting',
      createdAt: new Date().toISOString(),
      result: null,
      error: null
    };

    setVoiceTasks(prev => [...prev, newTask]);
    setError('');
    console.log('✅ Hlasový úkol přidán:', newTask.projectName, '-', totalBlocks, 'bloků');
  };

  // Zpracuje další čekající úkol
  const processNextTask = async () => {
    const waitingTask = voiceTasks.find(task => task.status === 'waiting');
    if (!waitingTask || isGenerating) {
      console.log('🔍 Žádné čekající úkoly nebo právě běží generování');
      return;
    }

    if (!elevenlabsApiKey) {
      setError('ElevenLabs API klíč není nastaven!');
      if (onApiKeyRequired) onApiKeyRequired();
      return;
    }

    console.log('🎙️ Spouštím generování hlasů pro:', waitingTask.projectName);

    // Označí úkol jako zpracovává se
    setVoiceTasks(prev => prev.map(task =>
      task.id === waitingTask.id
        ? { ...task, status: 'processing' }
        : task
    ));

    setIsGenerating(true);
    setError('');

    try {
      await generateVoicesForTask(waitingTask);
    } catch (err) {
      console.error('❌ Chyba při generování hlasů:', err);
      
      // Označí úkol jako chybný
      setVoiceTasks(prev => prev.map(task =>
        task.id === waitingTask.id
          ? { ...task, status: 'error', error: err.message }
          : task
      ));

      setError(`Chyba při generování "${waitingTask.projectName}": ${err.message}`);
    } finally {
      setIsGenerating(false);
      setCurrentStep('');
      setProgress(0);
      setCurrentDetails('');
    }
  };

  // Generuje hlasy pro konkrétní úkol
  const generateVoicesForTask = async (task) => {
    const updateProgress = (step, percent, details = '') => {
      setCurrentStep(step);
      setProgress(percent);
      setCurrentDetails(details);
    };

    updateProgress('Příprava', 10, `Připravuji ${task.totalBlocks} hlasových bloků...`);

    console.log('📤 Odesílám do ElevenLabs:', {
      voice_blocks: task.elevenlabsJson,
      api_key: elevenlabsApiKey ? '***nastaven***' : 'CHYBÍ'
    });

    // Upozornění na dlouhé generování
    if (task.totalBlocks > 20) {
      updateProgress('Generování', 30, `⚠️ Generuji ${task.totalBlocks} hlasů - může trvat 10-20 minut!`);
    } else {
      updateProgress('Generování', 30, `Generuji ${task.totalBlocks} hlasů...`);
    }

    const response = await axios.post('/api/generate-voices', {
      voice_blocks: task.elevenlabsJson,
      api_key: elevenlabsApiKey
    }, { timeout: 1200000 }); // 20 minut timeout (4x více času)

    updateProgress('Zpracování', 80, 'Zpracovávám odpověď...');

    if (!response.data.success) {
      throw new Error(response.data.error || 'Neočekávaná chyba z API');
    }

    updateProgress('Dokončování', 95, 'Ukládám výsledky...');

    const generatedFiles = response.data.generated_files || [];
    
    // Označí úkol jako dokončený
    setVoiceTasks(prev => prev.map(t =>
      t.id === task.id
        ? { 
            ...t, 
            status: 'completed',
            result: {
              generated_files: generatedFiles,
              generated_count: generatedFiles.length,
              success: true
            }
          }
        : t
    ));

    updateProgress('Dokončeno', 100, `Vygenerováno ${generatedFiles.length} hlasových souborů!`);

    // Informuje parent komponentu o nových souborech
    if (onVoicesGenerated && generatedFiles.length > 0) {
      const filesWithTexts = generatedFiles.map(file => ({
        ...file,
        original_text: task.elevenlabsJson[file.block_name]?.text || ''
      }));
      onVoicesGenerated(filesWithTexts);
    }

    console.log('✅ Generování dokončeno:', generatedFiles.length, 'souborů');
  };

  // Odstraní úkol z fronty
  const removeTask = (taskId) => {
    setVoiceTasks(prev => prev.filter(task => task.id !== taskId));
    console.log('🗑️ Úkol odstraněn:', taskId);
  };

  // Vyčistí všechny úkoly
  const clearAllTasks = () => {
    setVoiceTasks([]);
    setIsGenerating(false);
    setError('');
    localStorage.removeItem('voiceTasks');
    console.log('🧹 Všechny hlasové úkoly vyčištěny');
  };

  // Vynutí spuštění dalšího úkolu
  const forceStartNext = () => {
    const waitingTask = voiceTasks.find(task => task.status === 'waiting');
    if (waitingTask && !isGenerating) {
      processNextTask();
    } else {
      alert('Žádné čekající úkoly nebo právě běží generování');
    }
  };

  // Zkusí znovu neúspěšný úkol
  const retryTask = (taskId) => {
    setVoiceTasks(prev => prev.map(task =>
      task.id === taskId
        ? { ...task, status: 'waiting', error: null }
        : task
    ));
    console.log('🔄 Úkol označen k opakování:', taskId);
  };

  // Pokračuje dalším úkolem (přeskočí chybný)
  const skipToNext = () => {
    const waitingTask = voiceTasks.find(task => task.status === 'waiting');
    if (waitingTask && !isGenerating) {
      processNextTask();
    } else {
      alert('Žádné další čekající úkoly');
    }
  };

  // Zruší aktuální generování
  const cancelGeneration = () => {
    setCancelRequested(true);
    setCurrentStep('Ruším generování...');
    setCurrentDetails('Čekám na dokončení aktuálního hlasu...');
    
    // Označí běžící úkol jako zrušený
    setVoiceTasks(prev => prev.map(task =>
      task.status === 'processing'
        ? { ...task, status: 'cancelled', error: 'Zrušeno uživatelem' }
        : task
    ));
    
    setTimeout(() => {
      setIsGenerating(false);
      setCancelRequested(false);
      setCurrentStep('');
      setProgress(0);
      setCurrentDetails('');
    }, 2000);
  };

  // Detail modal funkce
  const openDetailModal = (task) => {
    setSelectedTask(task);
    setShowDetailModal(true);
  };

  const closeDetailModal = () => {
    setShowDetailModal(false);
    setSelectedTask(null);
  };

  // Expozice metod pro parent komponentu přes ref
  React.useImperativeHandle(ref, () => ({
    addVoiceTask: addVoiceTask
  }));

  return (
    <div className="bg-white rounded-lg shadow-sm p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-xl font-semibold text-gray-900 flex items-center">
            <span className="w-8 h-8 bg-purple-100 rounded-lg flex items-center justify-center mr-3">
              <span className="text-purple-600 text-lg">🎤</span>
            </span>
            Generování hlasů
          </h3>
          <p className="text-sm text-gray-600">Automatická fronta pro ElevenLabs TTS</p>
        </div>
        <div className="flex space-x-3">
          {voiceTasks.length > 0 && (
            <>
              <button
                onClick={forceStartNext}
                className="px-4 py-2 bg-orange-600 text-white rounded-md hover:bg-orange-700 transition-colors text-sm"
              >
                ⚡ Spustit další
              </button>
              {voiceTasks.some(task => task.status === 'error') && (
                <button
                  onClick={skipToNext}
                  className="px-4 py-2 bg-yellow-600 text-white rounded-md hover:bg-yellow-700 transition-colors text-sm"
                >
                  ⏭️ Přeskočit chyby
                </button>
              )}
              <button
                onClick={clearAllTasks}
                className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 transition-colors text-sm"
              >
                🧹 Vyčistit vše
              </button>
            </>
          )}
        </div>
      </div>

      {/* Status Bar */}
      <div className="mb-6 p-3 bg-gray-50 border border-gray-200 rounded-lg">
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center space-x-4">
            <div className={`flex items-center ${elevenlabsApiKey ? 'text-green-600' : 'text-red-600'}`}>
              <div className={`w-2 h-2 rounded-full mr-2 ${elevenlabsApiKey ? 'bg-green-500' : 'bg-red-500'}`}></div>
              ElevenLabs API {elevenlabsApiKey ? 'Připojeno' : 'Není nastaveno'}
            </div>
            <div className="flex items-center text-gray-600">
              <div className="w-2 h-2 rounded-full mr-2 bg-purple-500"></div>
              {voiceTasks.length} úkolů ve frontě
            </div>
          </div>
          <div className="text-xs text-gray-500">
            {voiceTasks.filter(t => t.status === 'waiting').length} čeká • 
            {voiceTasks.filter(t => t.status === 'completed').length} hotovo • 
            {voiceTasks.filter(t => t.status === 'error').length} chyb
          </div>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-red-700 text-sm">❌ {toDisplayString(error)}</p>
        </div>
      )}

      {/* Progress */}
      {isGenerating && (
        <div className="mb-6 p-4 bg-purple-50 border border-purple-200 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-purple-800">🎤 {currentStep}</h4>
            <div className="flex items-center space-x-3">
              <span className="text-sm text-purple-600">{progress}%</span>
              <button
                onClick={cancelGeneration}
                className="px-3 py-1 bg-red-500 text-white rounded-md hover:bg-red-600 transition-colors text-xs"
                disabled={cancelRequested}
              >
                {cancelRequested ? '🛑 Ruším...' : '❌ Zrušit'}
              </button>
            </div>
          </div>
          <div className="w-full bg-purple-200 rounded-full h-2 mb-3">
            <div 
              className="bg-purple-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            ></div>
          </div>
          {currentDetails && (
            <div className="text-xs text-purple-700">
              {currentDetails}
            </div>
          )}
        </div>
      )}

      {/* Voice Tasks List */}
      {voiceTasks.length > 0 && (
        <div className="mt-6">
          <h4 className="text-lg font-semibold text-gray-800 mb-4">
            🎤 Hlasové úkoly ({voiceTasks.length})
          </h4>
          
          {voiceTasks.map((task, index) => (
            <div key={task.id} className={`mb-4 p-4 rounded-lg border ${
              task.status === 'waiting' ? 'bg-gray-50 border-gray-300' :
              task.status === 'processing' ? 'bg-purple-50 border-purple-300' :
              task.status === 'completed' ? 'bg-green-50 border-green-300' :
              'bg-red-50 border-red-300'
            }`}>
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <div className="flex items-center">
                    <span className={`w-3 h-3 rounded-full mr-3 ${
                      task.status === 'waiting' ? 'bg-gray-400' :
                      task.status === 'processing' ? 'bg-purple-500 animate-pulse' :
                      task.status === 'completed' ? 'bg-green-500' :
                      'bg-red-500'
                    }`}></span>
                    <h5 className="font-medium">{task.projectName}</h5>
                  </div>
                  
                  {/* Základní informace */}
                  <p className="text-sm text-gray-600 mt-1">
                    {task.totalBlocks} hlasových bloků
                  </p>

                  {/* Detailní metriky */}
                  <div className="mt-2 p-3 bg-white/50 rounded-md border border-gray-200">
                    <div className="grid grid-cols-2 gap-4 text-xs">
                      <div>
                        <div className="font-medium text-gray-700 mb-1">🎯 Připraveno:</div>
                        <div className="text-gray-600">
                          🎤 {task.totalBlocks} hlasových bloků<br/>
                          📝 {Object.keys(task.elevenlabsJson).length} textů
                        </div>
                      </div>
                      <div>
                        <div className="font-medium text-gray-700 mb-1">
                          {task.status === 'completed' ? '✅ Vygenerováno:' : 
                           task.status === 'processing' ? '🔄 Generuje se...' :
                           task.status === 'error' ? '❌ Chyba:' :
                           '⏳ Čeká na zpracování'}
                        </div>
                        <div className="text-gray-600">
                          {task.status === 'completed' && task.result ? (
                            <>
                              📊 {task.result.generated_count} MP3 souborů<br/>
                              ✅ Úspěšně dokončeno
                            </>
                          ) : task.status === 'processing' ? (
                            <>
                              🔄 Zpracovává se...<br/>
                              ⚡ Komunikuje s API
                            </>
                          ) : task.status === 'error' ? (
                            <>
                              ❌ Chyba generování<br/>
                              🔧 Vyžaduje zásah
                            </>
                          ) : (
                            <>
                              ⏸️ Ve frontě<br/>
                              📋 Čeká na zpracování
                            </>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Čas vytvoření */}
                    <div className="mt-2 pt-2 border-t border-gray-200 text-xs text-gray-500">
                      Vytvořeno: {new Date(task.createdAt).toLocaleString('cs-CZ')}
                    </div>
                  </div>

                  {/* Akční tlačítka */}
                  <div className="mt-3 flex space-x-2">
                    {task.status === 'completed' && task.result && (
                      <button
                        onClick={() => openDetailModal(task)}
                        className="text-sm bg-gray-600 text-white px-3 py-1 rounded hover:bg-gray-700"
                      >
                        🎧 Detail & Přehrát
                      </button>
                    )}
                    
                    {task.status === 'error' && (
                      <>
                        <button
                          onClick={() => retryTask(task.id)}
                          className="text-sm bg-orange-600 text-white px-3 py-1 rounded hover:bg-orange-700"
                        >
                          🔄 Zkusit znovu
                        </button>
                        <button
                          onClick={() => {
                            alert('Chyba: ' + (task.error || 'Neznámá chyba'));
                          }}
                          className="text-sm bg-red-600 text-white px-3 py-1 rounded hover:bg-red-700"
                        >
                          ❌ Zobrazit chybu
                        </button>
                      </>
                    )}
                  </div>

                  {task.status === 'error' && (
                    <div className="mt-2 text-sm text-red-700">
                      ❌ {task.error}
                    </div>
                  )}
                </div>
                <button
                  onClick={() => removeTask(task.id)}
                  className="text-red-600 hover:text-red-800 text-sm px-2 py-1 border border-red-300 rounded hover:bg-red-50"
                >
                  Odstranit
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {voiceTasks.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          <span className="text-4xl mb-2 block">🎤</span>
          <p className="text-lg font-medium">Žádné hlasové úkoly</p>
          <p className="text-sm">Klikněte na "Generovat hlasy" v textech výše pro přidání úkolu</p>
        </div>
      )}

      {/* Detail Modal */}
      {showDetailModal && selectedTask && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-auto">
            {/* Modal Header */}
            <div className="p-6 border-b border-gray-200 sticky top-0 bg-white">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xl font-semibold text-gray-900">
                    🎧 Detail hlasového projektu
                  </h3>
                  <p className="text-gray-600 mt-1">{selectedTask.projectName}</p>
                </div>
                <button
                  onClick={closeDetailModal}
                  className="text-gray-400 hover:text-gray-600 text-2xl"
                >
                  ×
                </button>
              </div>
            </div>

            {/* Modal Content */}
            <div className="p-6">
              {/* Základní informace */}
              <div className="mb-6 p-4 bg-gray-50 rounded-lg">
                <h4 className="font-medium text-gray-900 mb-2">📊 Informace o úkolu</h4>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="font-medium">Stav:</span>
                    <span className={`ml-2 px-2 py-1 rounded text-xs ${
                      selectedTask.status === 'completed' ? 'bg-green-100 text-green-800' :
                      selectedTask.status === 'error' ? 'bg-red-100 text-red-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {selectedTask.status === 'completed' ? '✅ Dokončeno' :
                       selectedTask.status === 'error' ? '❌ Chyba' : selectedTask.status}
                    </span>
                  </div>
                  <div>
                    <span className="font-medium">Vytvořeno:</span>
                    <span className="ml-2">{new Date(selectedTask.createdAt).toLocaleString('cs-CZ')}</span>
                  </div>
                  <div>
                    <span className="font-medium">Celkem bloků:</span>
                    <span className="ml-2">{selectedTask.totalBlocks}</span>
                  </div>
                  <div>
                    <span className="font-medium">Vygenerováno:</span>
                    <span className="ml-2">
                      {selectedTask.result?.generated_count || 0} MP3 souborů
                    </span>
                  </div>
                </div>
              </div>

              {/* MP3 Soubory a přehrávače */}
              {selectedTask.result?.generated_files && selectedTask.result.generated_files.length > 0 && (
                <div className="mb-6">
                  <h4 className="font-medium text-gray-900 mb-4">🎵 Vygenerované hlasové soubory</h4>
                  <div className="space-y-4">
                    {selectedTask.result.generated_files.map((file, index) => (
                      <div key={index} className="p-4 border border-gray-200 rounded-lg">
                        <div className="flex items-start justify-between mb-3">
                          <div className="flex-1">
                            <h5 className="font-medium text-gray-900">{file.filename}</h5>
                            <p className="text-sm text-gray-600 mt-1">
                              Blok: {file.block_name} | Voice ID: {file.voice_id}
                            </p>
                          </div>
                          <div className="flex space-x-2">
                            <a
                              href={`/api/download/${file.filename}`}
                              download={file.filename}
                              className="text-sm bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700"
                            >
                              💾 Stáhnout
                            </a>
                          </div>
                        </div>

                        {/* Přehrávač */}
                        <div className="mb-3">
                          <audio 
                            controls 
                            className="w-full"
                            preload="metadata"
                          >
                            <source src={`/api/download/${file.filename}`} type="audio/mpeg" />
                            Váš prohlížeč nepodporuje přehrávání audia.
                          </audio>
                        </div>

                        {/* Originální text */}
                        {selectedTask.elevenlabsJson[file.block_name] && (
                          <div className="p-3 bg-gray-50 rounded border">
                            <h6 className="text-xs font-medium text-gray-700 mb-2">📝 Originální text:</h6>
                            <p className="text-sm text-gray-800">
                              {selectedTask.elevenlabsJson[file.block_name].text}
                            </p>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Chybné soubory (pokud existují) */}
              {selectedTask.elevenlabsJson && selectedTask.result?.generated_files && (
                (() => {
                  const generatedFileNames = selectedTask.result.generated_files.map(f => f.block_name);
                  const allBlockNames = Object.keys(selectedTask.elevenlabsJson);
                  const failedBlocks = allBlockNames.filter(name => !generatedFileNames.includes(name));
                  
                  if (failedBlocks.length > 0) {
                    return (
                      <div className="mb-6">
                        <h4 className="font-medium text-red-900 mb-4">❌ Neúspěšné bloky ({failedBlocks.length})</h4>
                        <div className="space-y-3">
                          {failedBlocks.map((blockName, index) => (
                            <div key={index} className="p-3 border border-red-200 rounded-lg bg-red-50">
                              <h5 className="font-medium text-red-900">{blockName}</h5>
                              <p className="text-sm text-red-700 mt-1">
                                Voice ID: {selectedTask.elevenlabsJson[blockName].voice_id}
                              </p>
                              <div className="mt-2 p-2 bg-white rounded border border-red-200">
                                <p className="text-sm text-gray-800">
                                  {selectedTask.elevenlabsJson[blockName].text}
                                </p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  }
                  return null;
                })()
              )}

              {/* Technické detaily */}
              <div className="border-t border-gray-200 pt-4">
                <details className="cursor-pointer">
                  <summary className="font-medium text-gray-900 hover:text-gray-700">
                    🔧 Technické detaily
                  </summary>
                  <div className="mt-3 space-y-3">
                    <div>
                      <h6 className="text-sm font-medium text-gray-700 mb-2">Výsledek API:</h6>
                      <pre className="text-xs bg-gray-100 p-3 rounded overflow-auto max-h-40">
                        {JSON.stringify(selectedTask.result, null, 2)}
                      </pre>
                    </div>
                    <div>
                      <h6 className="text-sm font-medium text-gray-700 mb-2">Originální JSON požadavek:</h6>
                      <pre className="text-xs bg-gray-100 p-3 rounded overflow-auto max-h-40">
                        {JSON.stringify(selectedTask.elevenlabsJson, null, 2)}
                      </pre>
                    </div>
                  </div>
                </details>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-6 border-t border-gray-200 bg-gray-50">
              <div className="flex justify-end space-x-3">
                {selectedTask.result?.generated_files && selectedTask.result.generated_files.length > 0 && (
                  <button
                    onClick={() => {
                      // Stažení všech souborů
                      selectedTask.result.generated_files.forEach(file => {
                        const link = document.createElement('a');
                        link.href = `/api/download/${file.filename}`;
                        link.download = file.filename;
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                      });
                    }}
                    className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                  >
                    💾 Stáhnout vše
                  </button>
                )}
                <button
                  onClick={closeDetailModal}
                  className="px-4 py-2 bg-gray-300 text-gray-700 rounded-md hover:bg-gray-400 transition-colors"
                >
                  Zavřít
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
});

export default VoiceGenerationQueue; 