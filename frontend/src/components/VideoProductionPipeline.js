import React, { useState } from 'react';
import axios from 'axios';

const VideoProductionPipeline = ({ 
  openaiApiKey, 
  availableAssistants, 
  onOpenApiManagement,
  onOpenAddAssistant,
  onVideoProjectGenerated
}) => {
  // Základní formulář stavy
  const [prompt, setPrompt] = useState('');
  const [targetDuration, setTargetDuration] = useState(12);
  const [targetWords, setTargetWords] = useState(1800);
  const [selectedDetailAssistant, setSelectedDetailAssistant] = useState('');
  
  // Jediný úkol stavy
  const [isGenerating, setIsGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState('');
  const [currentDetails, setCurrentDetails] = useState('');
  const [error, setError] = useState('');
  
  // Jednoduché seznamy úkolů s localStorage
  const [tasks, setTasks] = useState(() => {
    const saved = localStorage.getItem('simpleTasks');
    return saved ? JSON.parse(saved) : [];
  });
  const [currentTaskIndex, setCurrentTaskIndex] = useState(-1);

  // Automaticky aktualizuj target_words
  React.useEffect(() => {
    setTargetWords(targetDuration * 150);
  }, [targetDuration]);

  // Uklání do localStorage
  React.useEffect(() => {
    localStorage.setItem('simpleTasks', JSON.stringify(tasks));
  }, [tasks]);

  // Automatické spouštění dalších úkolů ve frontě
  React.useEffect(() => {
    const processingTask = tasks.find(task => task.status === 'processing');
    const waitingTask = tasks.find(task => task.status === 'waiting');
    
    // Pokud není žádný úkol v procesu a existuje čekající úkol, spusť ho
    if (!processingTask && !isGenerating && waitingTask) {
      console.log('🚀 Automaticky spouštím další úkol:', waitingTask.prompt);
      // Malé zpoždění aby se UI stihlo aktualizovat
      setTimeout(() => {
        processNextTask();
      }, 100);
    }
  }, [tasks, isGenerating]);

  const addTask = () => {
    if (!prompt.trim()) {
      setError('Zadejte téma');
      return;
    }
    if (!openaiApiKey) {
      setError('OpenAI API klíč není nastaven');
      return;
    }
    if (!selectedDetailAssistant) {
      setError('Vyberte Detail Assistant');
      return;
    }

    const newTask = {
      id: Date.now(),
      prompt: prompt.trim(),
      targetDuration,
      targetWords,
      selectedDetailAssistant,
      assistantName: availableAssistants.find(a => a.id === selectedDetailAssistant)?.name || 'Neznámý',
      status: 'waiting', // waiting, processing, completed, error
      result: null,
      error: null,
      createdAt: new Date()
    };

    setTasks(prev => [...prev, newTask]);
    setPrompt('');
    setSelectedDetailAssistant('');
    setError('');
    
    // useEffect automaticky spustí zpracování
  };

  const processNextTask = async () => {
    if (isGenerating) return;

    const waitingTask = tasks.find(task => task.status === 'waiting');
    if (!waitingTask) return;

    const taskIndex = tasks.findIndex(task => task.id === waitingTask.id);
    setCurrentTaskIndex(taskIndex);
    setIsGenerating(true);
    setError('');
    setProgress(0);
    setCurrentStep('');

    // Označit úkol jako zpracovává se
    setTasks(prev => prev.map(task => 
      task.id === waitingTask.id ? { ...task, status: 'processing' } : task
    ));

    try {
      await generateVideoProject(waitingTask);
      
      // Úspěch - result se nastaví v generateVideoProject
      setTasks(prev => prev.map(task => 
        task.id === waitingTask.id ? { 
          ...task, 
          status: 'completed',
          completedAt: new Date()
        } : task
      ));

    } catch (err) {
      console.error('Chyba:', err);
      
      // Chyba
      setTasks(prev => prev.map(task => 
        task.id === waitingTask.id ? { 
          ...task, 
          status: 'error', 
          error: err.message,
          completedAt: new Date()
        } : task
      ));
    }

    setIsGenerating(false);
    setCurrentTaskIndex(-1);
    setProgress(0);
    setCurrentStep('');

    // useEffect automaticky spustí další úkol
  };

  const generateVideoProject = async (task) => {
    const updateProgress = (step, percent, details = '') => {
      setCurrentStep(step);
      setProgress(percent);
      setCurrentDetails(details);
    };

    updateProgress('Příprava', 10, 'Připravuji strukturu...');
    
    const structureResponse = await axios.post('/api/generate-video-structure', {
      topic: task.prompt,
      target_minutes: task.targetDuration,
      target_words: task.targetWords,
      detail_assistant_id: task.selectedDetailAssistant,
      api_key: openaiApiKey
    }, { timeout: 60000 });

    if (!structureResponse.data.success) {
      throw new Error(structureResponse.data.error);
    }

    const { detail_assistant_id, segments, video_context } = structureResponse.data.data;
    updateProgress('Příprava', 25, `Struktura: ${segments.length} segmentů`);

    const selectedAssistant = availableAssistants.find(a => a.id === task.selectedDetailAssistant);
    const assistantCategory = selectedAssistant?.category || 'podcast';
    const narratorVoiceId = 'fb6f5b20hmCY0fO9Gr8v';

    updateProgress('Generování', 30, `Generuji ${segments.length} segmentů...`);

    const segmentPromises = segments.map(async (segment, index) => {
      const segmentResponse = await axios.post('/api/generate-segment-content', {
        detail_assistant_id,
        segment_info: segment,
        video_context,
        api_key: openaiApiKey,
        assistant_category: assistantCategory,
        narrator_voice_id: narratorVoiceId
      }, { timeout: 200000 });

      const progressIncrement = 60 / segments.length;
      const newProgress = 30 + (progressIncrement * (index + 1));
      updateProgress('Generování', newProgress, `Segment "${segment.id}" dokončen`);

      return {
        segmentId: segment.id,
        content: segmentResponse.data.data.segment_content
      };
    });

    const segmentResults = await Promise.all(segmentPromises);
    
    const segmentContentsMap = {};
    segmentResults.forEach(result => {
      segmentContentsMap[result.segmentId] = result.content;
    });
    
    updateProgress('Dokončování', 95, 'Skládám finální projekt...');

    const finalVideoProject = {
      id: Date.now(),
      title: task.prompt.substring(0, 50) + '...',
      created_at: new Date().toISOString(),
      video_info: {
        title: task.prompt,
        total_duration_minutes: task.targetDuration,
        total_words_estimate: task.targetWords,
        target_audience: "Obecná veřejnost",
        tone: "Vzdělávací"
      },
      youtube_metadata: {
        title: task.prompt.substring(0, 100),
        description: `Vzdělávací video o tématu: ${task.prompt}`,
        tags: task.prompt.split(' ').slice(0, 10),
        category: "Education"
      },
      segments: segments.map(segment => ({
        ...segment,
        content: segmentContentsMap[segment.id]
      })),
      metadata: {
        total_segments: segments.length,
        total_words: Object.values(segmentContentsMap).reduce((total, content) => {
          let segmentWords = 0;
          Object.values(content).forEach(block => {
            if (block && block.text) {
              segmentWords += block.text.split(' ').length;
            }
          });
          return total + segmentWords;
        }, 0),
        estimated_cost: segments.length * 0.15,
        generation_time: new Date().toISOString()
      }
    };

    updateProgress('Dokončeno', 100, 'Video projekt úspěšně vygenerován!');

    // Uložit výsledek do úkolu
    setTasks(prev => prev.map(t => 
      t.id === task.id ? { ...t, result: finalVideoProject } : t
    ));

    // Poslat do voice generatoru
    if (onVideoProjectGenerated) {
      onVideoProjectGenerated(finalVideoProject);
    }
  };

  const removeTask = (taskId) => {
    setTasks(prev => prev.filter(task => task.id !== taskId));
  };

  const clearAllTasks = () => {
    setTasks([]);
    setCurrentTaskIndex(-1);
    setIsGenerating(false);
    localStorage.removeItem('simpleTasks');
  };

  const forceStartNext = () => {
    console.log('🔧 Ruční spuštění dalšího úkolu');
    const waitingTask = tasks.find(task => task.status === 'waiting');
    if (waitingTask && !isGenerating) {
      processNextTask();
    } else {
      alert('Žádné čekající úkoly nebo právě běží generování');
    }
  };

  const openaiAssistants = availableAssistants.filter(a => a.type === 'openai_assistant');

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
          <p className="text-sm text-gray-600">Zadejte téma + vyberte Detail Assistant</p>
        </div>
        <div className="flex space-x-3">
          <button
            onClick={onOpenAddAssistant}
            className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors text-sm"
          >
            ➕ Přidat asistenta
          </button>
          <button
            onClick={onOpenApiManagement}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors text-sm"
          >
            🔧 API Management
          </button>
          {tasks.length > 0 && (
            <>
              <button
                onClick={forceStartNext}
                className="px-4 py-2 bg-orange-600 text-white rounded-md hover:bg-orange-700 transition-colors text-sm"
              >
                ⚡ Spustit další
              </button>
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
            <div className={`flex items-center ${openaiApiKey ? 'text-green-600' : 'text-red-600'}`}>
              <div className={`w-2 h-2 rounded-full mr-2 ${openaiApiKey ? 'bg-green-500' : 'bg-red-500'}`}></div>
              OpenAI API {openaiApiKey ? 'Připojeno' : 'Není nastaveno'}
            </div>
            <div className={`flex items-center ${openaiAssistants.length > 0 ? 'text-green-600' : 'text-amber-600'}`}>
              <div className={`w-2 h-2 rounded-full mr-2 ${openaiAssistants.length > 0 ? 'bg-green-500' : 'bg-amber-500'}`}></div>
              {openaiAssistants.length} Detail Assistants
            </div>
          </div>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-red-700 text-sm">❌ {error}</p>
        </div>
      )}

      {/* Form */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div className="md:col-span-2">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Video téma *
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="electricity and innovation"
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Cílová délka (minuty)
          </label>
          <input
            type="number"
            value={targetDuration}
            onChange={(e) => setTargetDuration(parseInt(e.target.value))}
            min="5"
            max="60"
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Cílový počet slov (automaticky)
          </label>
          <input
            type="number"
            value={targetWords}
            readOnly
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm bg-gray-50 text-gray-600"
          />
        </div>

        <div className="md:col-span-2">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Detail Assistant *
          </label>
          <select
            value={selectedDetailAssistant}
            onChange={(e) => setSelectedDetailAssistant(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
          >
            <option value="">-- Vyberte Detail Assistant --</option>
            {openaiAssistants.map(assistant => (
              <option key={assistant.id} value={assistant.id}>
                {assistant.name} {assistant.category === 'document' ? '(📄 Dokument)' : '(🎙️ Podcast)'}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Add Button */}
      <div className="flex justify-center mb-6">
        <button
          onClick={addTask}
          disabled={!prompt.trim() || !openaiApiKey || !selectedDetailAssistant}
          className={`px-8 py-3 rounded-lg font-medium text-white transition-colors ${
            !prompt.trim() || !openaiApiKey || !selectedDetailAssistant
              ? 'bg-gray-400 cursor-not-allowed'
              : 'bg-purple-600 hover:bg-purple-700'
          }`}
        >
          ➕ Přidat úkol
        </button>
      </div>

      {/* Progress */}
      {isGenerating && (
        <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-blue-800">🔄 {currentStep}</h4>
            <span className="text-sm text-blue-600">{progress}%</span>
          </div>
          <div className="w-full bg-blue-200 rounded-full h-2 mb-3">
            <div 
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            ></div>
          </div>
          {currentDetails && (
            <div className="text-xs text-blue-700">
              {currentDetails}
            </div>
          )}
        </div>
      )}

      {/* Tasks List */}
      {tasks.length > 0 && (
        <div className="mt-6">
          <h4 className="text-lg font-semibold text-gray-800 mb-4">
            📋 Úkoly ({tasks.length})
          </h4>
          
          {tasks.map((task, index) => (
            <div key={task.id} className={`mb-4 p-4 rounded-lg border ${
              task.status === 'waiting' ? 'bg-gray-50 border-gray-300' :
              task.status === 'processing' ? 'bg-blue-50 border-blue-300' :
              task.status === 'completed' ? 'bg-green-50 border-green-300' :
              'bg-red-50 border-red-300'
            }`}>
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <div className="flex items-center">
                    <span className={`w-3 h-3 rounded-full mr-3 ${
                      task.status === 'waiting' ? 'bg-gray-400' :
                      task.status === 'processing' ? 'bg-blue-500 animate-pulse' :
                      task.status === 'completed' ? 'bg-green-500' :
                      'bg-red-500'
                    }`}></span>
                    <h5 className="font-medium">{task.prompt}</h5>
                  </div>
                  <p className="text-sm text-gray-600 mt-1">
                    {task.assistantName} • {task.targetDuration} min
                  </p>
                                     {task.status === 'completed' && task.result && (
                     <div className="mt-2 flex space-x-2">
                       <button
                         onClick={() => {
                           const detailWindow = window.open('', '_blank');
                           detailWindow.document.write(`
                             <html>
                               <head><title>Detail úkolu: ${task.prompt}</title></head>
                               <body style="font-family: Arial;">
                                 <h2>Detail úkolu: ${task.prompt}</h2>
                                 <pre style="background: #f5f5f5; padding: 10px; overflow: auto;">${JSON.stringify(task.result, null, 2)}</pre>
                               </body>
                             </html>
                           `);
                           detailWindow.document.close();
                         }}
                         className="text-sm bg-gray-600 text-white px-3 py-1 rounded hover:bg-gray-700"
                       >
                         📄 Detail
                       </button>
                       <button
                         onClick={() => onVideoProjectGenerated && onVideoProjectGenerated(task.result)}
                         className="text-sm bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700"
                       >
                         🎵 Generovat hlasy
                       </button>
                     </div>
                   )}
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
    </div>
  );
};

export default VideoProductionPipeline; 