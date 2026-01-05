import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toDisplayString } from '../utils/display';

const UnifiedTaskQueue = ({ 
  openaiApiKey, 
  elevenlabsApiKey,
  availableAssistants, 
  onOpenApiManagement,
  onVideoProjectGenerated 
}) => {
  // Stavy pro fronta úkolů
  const [tasks, setTasks] = useState(() => {
    const saved = localStorage.getItem('unifiedTaskQueue');
    return saved ? JSON.parse(saved) : [];
  });
  
  // Stavy pro nový úkol
  const [newTaskPrompt, setNewTaskPrompt] = useState('');
  const [newTaskType, setNewTaskType] = useState('podcast'); // podcast, video
  const [targetDuration, setTargetDuration] = useState(1);
  const [targetWords, setTargetWords] = useState(150);
  const [selectedAssistant, setSelectedAssistant] = useState('');
  
  // Stavy pro zpracování
  const [isProcessing, setIsProcessing] = useState(false);
  const [currentTaskId, setCurrentTaskId] = useState(null);
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState('');
  const [currentDetails, setCurrentDetails] = useState('');
  const [error, setError] = useState('');
  
  // Stav pro kontrolu textu před generováním hlasů
  const [pendingTextReview, setPendingTextReview] = useState(null);
  const [showTextReview, setShowTextReview] = useState(false);
  
  // Stavy pro UI
  const [activeTab, setActiveTab] = useState('queue'); // queue, history, video-queue
  const [showAddModal, setShowAddModal] = useState(false);

  // Video fronta - úkoly připravené na video produkci
  const [videoQueue, setVideoQueue] = useState(() => {
    const saved = localStorage.getItem('videoQueue');
    return saved ? JSON.parse(saved) : [];
  });

  // Automaticky aktualizuj target_words podle délky
  useEffect(() => {
    setTargetWords(targetDuration * 150);
  }, [targetDuration]);

  // Uklání do localStorage
  useEffect(() => {
    localStorage.setItem('unifiedTaskQueue', JSON.stringify(tasks));
  }, [tasks]);

  useEffect(() => {
    localStorage.setItem('videoQueue', JSON.stringify(videoQueue));
  }, [videoQueue]);

  // Poznámka: Automatické zpracování je VYPNUTO kvůli problémům s timeouty
  // useEffect(() => {
  //   const processingTask = tasks.find(task => task.status === 'processing');
  //   const waitingTask = tasks.find(task => task.status === 'waiting');
  //   
  //   if (!processingTask && !isProcessing && waitingTask) {
  //     setTimeout(() => {
  //       processNextTask();
  //     }, 500);
  //   }
  // }, [tasks, isProcessing]);

  const addTask = () => {
    if (!newTaskPrompt.trim()) {
      setError('Zadejte téma úkolu');
      return;
    }
    if (!openaiApiKey) {
      setError('OpenAI API klíč není nastaven');
      return;
    }
    if (!selectedAssistant) {
      setError('Vyberte asistenta');
      return;
    }
    if (newTaskType === 'podcast' && !elevenlabsApiKey) {
      setError('ElevenLabs API klíč není nastaven pro podcast');
      return;
    }

    const assistantData = availableAssistants.find(a => a.id === selectedAssistant);
    
    const newTask = {
      id: Date.now(),
      type: newTaskType,
      prompt: newTaskPrompt.trim(),
      targetDuration,
      targetWords,
      selectedAssistant,
      assistantName: assistantData?.name || 'Neznámý',
      assistantCategory: assistantData?.category || 'podcast',
      status: 'waiting', // waiting, processing, completed, error
      result: null,
      error: null,
      createdAt: new Date(),
      voiceFiles: [],
      videoGenerated: false
    };

    setTasks(prev => [...prev, newTask]);
    
    // Reset formuláře
    setNewTaskPrompt('');
    setSelectedAssistant('');
    setShowAddModal(false);
    setError('');
  };

  const processNextTask = async () => {
    if (isProcessing) return;

    const waitingTask = tasks.find(task => task.status === 'waiting');
    if (!waitingTask) return;

    setCurrentTaskId(waitingTask.id);
    setIsProcessing(true);
    setError('');
    setProgress(0);
    setCurrentStep('');

    // Označit úkol jako zpracovává se
    setTasks(prev => prev.map(task => 
      task.id === waitingTask.id ? { ...task, status: 'processing' } : task
    ));

    try {
      if (waitingTask.type === 'podcast') {
        await processPodcastTask(waitingTask);
      } else if (waitingTask.type === 'video') {
        await processVideoTask(waitingTask);
      }
      
      setTasks(prev => prev.map(task => 
        task.id === waitingTask.id ? { 
          ...task, 
          status: 'completed',
          completedAt: new Date()
        } : task
      ));

    } catch (err) {
      console.error('Chyba při zpracování úkolu:', err);
      
      setTasks(prev => prev.map(task => 
        task.id === waitingTask.id ? { 
          ...task, 
          status: 'error', 
          error: err.message,
          completedAt: new Date()
        } : task
      ));
      setError(err.message);
    }

    setIsProcessing(false);
    setCurrentTaskId(null);
    setProgress(0);
    setCurrentStep('');
  };

  const processPodcastTask = async (task) => {
    const updateProgress = (step, percent, details = '') => {
      setCurrentStep(step);
      setProgress(percent);
      setCurrentDetails(details);
    };

    updateProgress('Příprava struktury', 10, 'Generuji strukturu podcastu...');
    
    // Generování struktury podcastu
    const structureResponse = await axios.post('/api/generate-video-structure', {
      topic: task.prompt,
      target_minutes: task.targetDuration,
      target_words: task.targetWords,
      detail_assistant_id: task.selectedAssistant,
      assistant_category: task.assistantCategory, // PŘIDÁNO: používám kategorii z tasku
      api_key: openaiApiKey
    }, { timeout: 60000 });

    if (!structureResponse.data.success) {
      throw new Error(structureResponse.data.error);
    }

    const { segments, video_context } = structureResponse.data.data;
    updateProgress('Generování obsahu', 30, `Generuji ${segments.length} segmentů...`);

    // Generování obsahu segmentů
    const segmentPromises = segments.map(async (segment, index) => {
      const segmentResponse = await axios.post('/api/generate-segment-content', {
        detail_assistant_id: task.selectedAssistant,
        segment_info: segment,
        video_context,
        api_key: openaiApiKey,
        assistant_category: task.assistantCategory
        // ODSTRANĚNO: narrator_voice_id - nechám backend zachovat původní z assistant response
      }, { timeout: 300000 }); // 5 minut timeout pro dlouhé operace

      const progressIncrement = 40 / segments.length;
      const newProgress = 30 + (progressIncrement * (index + 1));
      updateProgress('Generování obsahu', newProgress, `Segment "${segment.id}" dokončen`);

      return {
        segmentId: segment.id,
        content: segmentResponse.data.data.segment_content
      };
    });

    const segmentResults = await Promise.all(segmentPromises);
    
    updateProgress('Text vygenerován', 70, 'Čekám na kontrolu textu...');

    // Uložit text a zastavit pro kontrolu
    setTasks(prev => prev.map(taskItem => 
      taskItem.id === task.id ? { 
        ...taskItem, 
        result: {
          segments: segmentResults,
          video_context,
          structure: segments
        },
        status: 'text_ready', // Nový stav pro připravený text
        completedAt: new Date()
      } : taskItem
    ));

    // Zobrazit náhled textu pro kontrolu
    setPendingTextReview({
      taskId: task.id,
      segments: segmentResults,
      title: task.prompt,
      narratorVoiceId: 'fb6f5b20hmCY0fO9Gr8v',
      segmentStructure: segments,
      video_context
    });
    setShowTextReview(true);
    
    // Zastavit zpracování - pokračování bude po potvrzení
    setIsProcessing(false);
    setCurrentTaskId(null);
  };

  // Funkce pro pokračování s generováním hlasů po kontrole textu
  const generateVoicesForTask = async (taskData) => {
    setIsProcessing(true);
    setCurrentTaskId(taskData.taskId);
    setShowTextReview(false);
    setPendingTextReview(null);

    const updateProgress = (step, percent, details = '') => {
      setCurrentStep(step);
      setProgress(percent);
      setCurrentDetails(details);
    };

    try {
      updateProgress('Generování hlasů', 75, 'Vytvářím audio soubory...');

      // Generování hlasových souborů
      const voicePromises = taskData.segments.map(async (result, index) => {
        const voiceResponse = await axios.post('/api/generate-voice', {
          text: result.content,
          voice_id: taskData.narratorVoiceId,
          elevenlabs_api_key: elevenlabsApiKey,
          filename: `${taskData.taskId}_segment_${index + 1}`
        }, { timeout: 120000 });

        const progressIncrement = 20 / taskData.segments.length;
        const newProgress = 75 + (progressIncrement * (index + 1));
        updateProgress('Generování hlasů', newProgress, `Audio ${index + 1}/${taskData.segments.length}`);

        return voiceResponse.data.filename;
      });

      const voiceFiles = await Promise.all(voicePromises);

    updateProgress('Dokončování', 95, 'Ukládám výsledky...');

      // Finální uložení s hlasovými soubory
      setTasks(prev => prev.map(taskItem => 
        taskItem.id === taskData.taskId ? { 
          ...taskItem, 
          voiceFiles: voiceFiles,
          status: 'completed'
        } : taskItem
      ));

      updateProgress('Hotovo', 100, 'Podcast úspěšně vygenerován!');
      
      setTimeout(() => {
        setIsProcessing(false);
        setCurrentTaskId(null);
      }, 2000);

    } catch (error) {
      console.error('Chyba při generování hlasů:', error);
      setError(`Chyba při generování hlasů: ${error.message}`);
      
      setTasks(prev => prev.map(taskItem => 
        taskItem.id === taskData.taskId ? { 
          ...taskItem, 
          status: 'error'
        } : taskItem
      ));
      
      setIsProcessing(false);
      setCurrentTaskId(null);
    }
  };

  const processVideoTask = async (task) => {
    // Implementace video úkolu - zatím jednoduchá verze
    const updateProgress = (step, percent, details = '') => {
      setCurrentStep(step);
      setProgress(percent);
      setCurrentDetails(details);
    };

    updateProgress('Video generování', 50, 'Připravuji video projekt...');
    
    // Simulace video generování
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    updateProgress('Hotovo', 100, 'Video projekt připraven!');
  };

  const createVideoFromTask = (task) => {
    if (!task.voiceFiles || task.voiceFiles.length === 0) {
      setError('Úkol nemá vygenerované hlasové soubory');
       return;
     }

    // Přidat do video fronty
    const videoProject = {
      id: `video_${task.id}`,
      originalTaskId: task.id,
      title: task.prompt,
      type: 'podcast-to-video',
      voiceFiles: task.voiceFiles,
      segments: task.result?.segments || [],
      status: 'pending', // pending, processing, completed, error
      createdAt: new Date()
    };

    setVideoQueue(prev => [...prev, videoProject]);
    
    // Označit původní úkol jako připravený na video
     setTasks(prev => prev.map(t => 
      t.id === task.id ? { ...t, videoGenerated: true } : t
    ));

    // Přepnout na video frontu
    setActiveTab('video-queue');
  };

  const removeTask = (taskId) => {
    setTasks(prev => prev.filter(task => task.id !== taskId));
  };

  const clearAllTasks = () => {
    setTasks([]);
  };

  const clearCompletedTasks = () => {
    setTasks(prev => prev.filter(task => task.status !== 'completed'));
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'waiting': return '⏳';
      case 'processing': return '🔄';
      case 'text_ready': return '📝';
      case 'completed': return '✅';
      case 'error': return '❌';
      default: return '⏳';
    }
  };

  const getTypeIcon = (type) => {
    switch (type) {
      case 'podcast': return '🎙️';
      case 'video': return '📹';
      default: return '📝';
    }
  };

  const formatDate = (date) => {
    return new Date(date).toLocaleString('cs-CZ');
  };

  const formatDuration = (duration) => {
    return `${duration} min`;
  };

  const waitingTasks = tasks.filter(task => task.status === 'waiting');
  const processingTasks = tasks.filter(task => task.status === 'processing');
  const textReadyTasks = tasks.filter(task => task.status === 'text_ready');
  const completedTasks = tasks.filter(task => task.status === 'completed');
  const errorTasks = tasks.filter(task => task.status === 'error');

  return (
    <div className="unified-task-queue bg-white p-6 rounded-lg shadow-lg">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-800">
          📋 Fronta úkolů
        </h2>
        <div className="flex gap-2">
          <button
            onClick={() => setShowAddModal(true)}
            className="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600 transition-colors"
          >
            ➕ Přidat úkol
          </button>
          {tasks.length > 0 && (
            <button
              onClick={clearCompletedTasks}
              className="bg-gray-500 text-white px-4 py-2 rounded hover:bg-gray-600 transition-colors"
            >
              🗑️ Vymazat dokončené
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200 mb-6">
              <button
          onClick={() => setActiveTab('queue')}
          className={`px-4 py-2 font-medium ${
            activeTab === 'queue' 
              ? 'border-b-2 border-blue-500 text-blue-600' 
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          📋 Fronta ({waitingTasks.length + processingTasks.length + textReadyTasks.length})
              </button>
              <button
          onClick={() => setActiveTab('history')}
          className={`px-4 py-2 font-medium ${
            activeTab === 'history' 
              ? 'border-b-2 border-blue-500 text-blue-600' 
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          📊 Historie ({completedTasks.length + errorTasks.length})
              </button>
        <button
          onClick={() => setActiveTab('video-queue')}
          className={`px-4 py-2 font-medium ${
            activeTab === 'video-queue' 
              ? 'border-b-2 border-blue-500 text-blue-600' 
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          📹 Video ve frontě ({videoQueue.length})
        </button>
      </div>

      {/* Error Display */}
      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
          ❌ {toDisplayString(error)}
        </div>
      )}

      {/* Current Processing Task */}
      {isProcessing && currentTaskId && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
          <h3 className="font-semibold text-blue-800 mb-2">
            🔄 Zpracovává se: {tasks.find(t => t.id === currentTaskId)?.prompt}
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

      {/* Queue Tab */}
      {activeTab === 'queue' && (
        <div>
          {waitingTasks.length === 0 && processingTasks.length === 0 && textReadyTasks.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
              📭 Fronta je prázdná
                </div>
          ) : (
            <div className="space-y-4">
              {[...processingTasks, ...textReadyTasks, ...waitingTasks].map((task, index) => (
                <div 
                  key={task.id} 
                  className={`border rounded-lg p-4 ${
                    task.status === 'processing' 
                      ? 'border-blue-300 bg-blue-50' 
                      : task.status === 'text_ready'
                      ? 'border-yellow-300 bg-yellow-50'
                      : 'border-gray-200 bg-gray-50'
                  }`}
                >
                  <div className="flex justify-between items-start">
                      <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-lg">{getStatusIcon(task.status)}</span>
                        <span className="text-lg">{getTypeIcon(task.type)}</span>
                        <span className="font-semibold text-gray-800">
                          {task.prompt}
                        </span>
                        </div>
                      <div className="text-sm text-gray-600 space-y-1">
                        <div>📅 Vytvořeno: {formatDate(task.createdAt)}</div>
                        <div>🎭 Asistent: {task.assistantName}</div>
                        <div>⏱️ Délka: {formatDuration(task.targetDuration)}</div>
                        <div>📝 Slova: {task.targetWords}</div>
                            </div>
                            </div>
                    <div className="flex gap-2">
                      {task.status === 'text_ready' && (
                        <button
                          onClick={() => {
                            setPendingTextReview({
                              taskId: task.id,
                              segments: task.result.segments,
                              title: task.prompt,
                              narratorVoiceId: 'fb6f5b20hmCY0fO9Gr8v',
                              segmentStructure: task.result.structure,
                              video_context: task.result.video_context
                            });
                            setShowTextReview(true);
                          }}
                          className="bg-blue-500 text-white px-3 py-1 rounded text-sm hover:bg-blue-600 transition-colors"
                          title="Zkontrolovat text"
                        >
                          📝 Zkontrolovat text
                        </button>
                      )}
                      <button
                        onClick={() => removeTask(task.id)}
                        className="text-red-500 hover:text-red-700 p-1"
                        title="Smazat úkol"
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
                          
      {/* History Tab */}
      {activeTab === 'history' && (
                                <div>
          {completedTasks.length === 0 && errorTasks.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              📭 Historie je prázdná
                                </div>
          ) : (
            <div className="space-y-4">
              {[...completedTasks, ...errorTasks].map((task) => (
                <div 
                  key={task.id} 
                  className={`border rounded-lg p-4 ${
                    task.status === 'completed' 
                      ? 'border-green-200 bg-green-50' 
                      : 'border-red-200 bg-red-50'
                  }`}
                >
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-lg">{getStatusIcon(task.status)}</span>
                        <span className="text-lg">{getTypeIcon(task.type)}</span>
                        <span className="font-semibold text-gray-800">
                          {task.prompt}
                        </span>
                                </div>
                      <div className="text-sm text-gray-600 space-y-1">
                        <div>📅 Dokončeno: {formatDate(task.completedAt)}</div>
                        <div>🎭 Asistent: {task.assistantName}</div>
                        <div>⏱️ Délka: {formatDuration(task.targetDuration)}</div>
                        {task.status === 'completed' && task.voiceFiles && (
                          <div>🎵 Hlasové soubory: {task.voiceFiles.length}</div>
                        )}
                        {task.status === 'error' && (
                          <div className="text-red-600">❌ {task.error}</div>
                            )}
                          </div>
                        </div>
                    <div className="flex gap-2">
                      {task.status === 'completed' && task.type === 'podcast' && !task.videoGenerated && (
                            <button
                          onClick={() => createVideoFromTask(task)}
                          className="bg-purple-500 text-white px-3 py-1 rounded text-sm hover:bg-purple-600 transition-colors"
                          title="Vytvořit video"
                        >
                          📹 Vytvořit video
                            </button>
                          )}
                            <button
                        onClick={() => removeTask(task.id)}
                        className="text-red-500 hover:text-red-700 p-1"
                        title="Smazat úkol"
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

      {/* Video Queue Tab */}
      {activeTab === 'video-queue' && (
        <div>
          {videoQueue.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              📹 Video fronta je prázdná
            </div>
          ) : (
            <div className="space-y-4">
              {videoQueue.map((videoProject) => (
                <div 
                  key={videoProject.id} 
                  className="border border-purple-200 bg-purple-50 rounded-lg p-4"
                >
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-lg">📹</span>
                        <span className="font-semibold text-gray-800">
                          {videoProject.title}
                        </span>
                          </div>
                      <div className="text-sm text-gray-600 space-y-1">
                        <div>📅 Vytvořeno: {formatDate(videoProject.createdAt)}</div>
                        <div>🎵 Hlasové soubory: {videoProject.voiceFiles.length}</div>
                        <div>📝 Segmenty: {videoProject.segments.length}</div>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => {
                          // Implementace spuštění video produkce
                          console.log('Spouštím video produkci pro:', videoProject);
                        }}
                        className="bg-purple-500 text-white px-3 py-1 rounded text-sm hover:bg-purple-600 transition-colors"
                      >
                        🚀 Spustit produkci
                      </button>
                      <button
                        onClick={() => {
                          setVideoQueue(prev => prev.filter(vp => vp.id !== videoProject.id));
                        }}
                        className="text-red-500 hover:text-red-700 p-1"
                        title="Smazat z video fronty"
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

      {/* Text Review Modal */}
      {showTextReview && pendingTextReview && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-4xl max-h-[80vh] overflow-y-auto">
            <h3 className="text-lg font-bold mb-4">📝 Kontrola vygenerovaného textu</h3>
            
            <div className="mb-4">
              <h4 className="font-semibold text-gray-800">Projekt: {pendingTextReview.title}</h4>
              <p className="text-sm text-gray-600">
                {pendingTextReview.segments.length} segmentů
              </p>
            </div>

            <div className="space-y-4 mb-6">
              {pendingTextReview.segments.map((segment, index) => (
                <div key={index} className="border border-gray-200 rounded-lg p-4">
                  <h5 className="font-medium text-gray-800 mb-2">
                    Segment {index + 1}: {segment.segmentId}
                  </h5>
                  <div className="text-sm text-gray-700 whitespace-pre-wrap">
                    {segment.content}
                  </div>
                  <div className="text-xs text-gray-500 mt-2">
                    Počet slov: {segment.content.split(' ').length}
                    </div>
                  </div>
                ))}
            </div>

            <div className="flex justify-end gap-2">
              <button
                onClick={() => {
                  setShowTextReview(false);
                  setPendingTextReview(null);
                  // Označit úkol jako zrušený
                  setTasks(prev => prev.map(task => 
                    task.id === pendingTextReview.taskId ? { 
                      ...task, 
                      status: 'error',
                      error: 'Zrušeno uživatelem po kontrole textu'
                    } : task
                  ));
                }}
                className="px-4 py-2 text-gray-600 hover:text-gray-800 border border-gray-300 rounded"
              >
                ❌ Zrušit
              </button>
              <button
                onClick={() => {
                  // Editace textu - zatím jen jednoduchá implementace
                  alert('Funkce editace bude implementována v budoucí verzi');
                }}
                className="px-4 py-2 bg-yellow-500 text-white rounded hover:bg-yellow-600 transition-colors"
              >
                ✏️ Editovat
              </button>
              <button
                onClick={() => generateVoicesForTask(pendingTextReview)}
                className="bg-green-500 text-white px-4 py-2 rounded hover:bg-green-600 transition-colors"
              >
                ✅ Pokračovat s generováním hlasů
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Task Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-bold mb-4">➕ Přidat nový úkol</h3>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Typ úkolu
                </label>
                <select
                  value={newTaskType}
                  onChange={(e) => setNewTaskType(e.target.value)}
                  className="w-full border border-gray-300 rounded px-3 py-2"
                >
                  <option value="podcast">🎙️ Podcast</option>
                  <option value="video">📹 Video</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Téma / Prompt
                </label>
                <textarea
                  value={newTaskPrompt}
                  onChange={(e) => setNewTaskPrompt(e.target.value)}
                  placeholder="O čem má být úkol..."
                  className="w-full border border-gray-300 rounded px-3 py-2 h-24 resize-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Asistent
                </label>
                <select
                  value={selectedAssistant}
                  onChange={(e) => setSelectedAssistant(e.target.value)}
                  className="w-full border border-gray-300 rounded px-3 py-2"
                >
                  <option value="">Vyberte asistenta...</option>
                  {availableAssistants.map(assistant => (
                    <option key={assistant.id} value={assistant.id}>
                      {assistant.name} ({assistant.category})
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Délka (min)
                  </label>
                  <input
                    type="number"
                    value={targetDuration}
                    onChange={(e) => setTargetDuration(parseInt(e.target.value))}
                    min="1"
                    max="60"
                    className="w-full border border-gray-300 rounded px-3 py-2"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Slova
                  </label>
                  <input
                    type="number"
                    value={targetWords}
                    onChange={(e) => setTargetWords(parseInt(e.target.value))}
                    className="w-full border border-gray-300 rounded px-3 py-2"
                    disabled
                  />
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 text-gray-600 hover:text-gray-800"
              >
                Zrušit
              </button>
              <button
                onClick={addTask}
                className="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600 transition-colors"
              >
                Přidat úkol
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default UnifiedTaskQueue; 