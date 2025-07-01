import React, { useState } from 'react';
import axios from 'axios';
import FileUploader from './components/FileUploader';
import VoiceGenerator from './components/VoiceGenerator';
import BackgroundUploader from './components/BackgroundUploader';
import VideoBackgroundUploader from './components/VideoBackgroundUploader';

function App() {
  // Stavy aplikace
  const [audioFiles, setAudioFiles] = useState([]);
  const [introFile, setIntroFile] = useState(null);
  const [outroFile, setOutroFile] = useState(null);
  const [pauseDuration, setPauseDuration] = useState(0.6);
  const [generateSubtitles, setGenerateSubtitles] = useState(false);
  const [generateVideo, setGenerateVideo] = useState(false);
  const [subtitleJson, setSubtitleJson] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [generatedVoiceFiles, setGeneratedVoiceFiles] = useState([]);
  const [existingFiles, setExistingFiles] = useState([]);
  const [selectedBackground, setSelectedBackground] = useState(null);
  const [selectedVideoBackground, setSelectedVideoBackground] = useState(null);
  const [useVideoBackground, setUseVideoBackground] = useState(false);
  // Nový stav pro hlasitosti podle voice_id (v dB, 0 = bez změny) - načte z localStorage
  const [voiceVolumes, setVoiceVolumes] = useState(() => {
    try {
      const saved = localStorage.getItem('voice_volumes');
      const parsed = saved ? JSON.parse(saved) : {};
      console.log('💾 Načítám uložená nastavení hlasitosti:', parsed);
      return parsed;
    } catch (error) {
      console.error('❌ Chyba při načítání nastavení hlasitosti:', error);
      return {};
    }
  });

  // Načte existující soubory při startu aplikace a vymaže staré nahrávky
  React.useEffect(() => {
    // Vymaže staré nahrávky při refreshi
    setAudioFiles([]);
    setGeneratedVoiceFiles([]);
    setResult(null);
    setError('');
    // NERESETUJE selectedBackground - zůstane vybrané pozadí
    
    loadExistingFiles();
  }, []);

  // Funkce pro načtení existujících souborů z backendu
  const loadExistingFiles = async () => {
    try {
      const response = await axios.get('/api/files');
      setExistingFiles(response.data.files || []);
    } catch (err) {
      console.error('Chyba při načítání existujících souborů:', err);
      // Nezobrazzujeme chybu uživateli, jen logujeme
    }
  };

  // Funkce pro zpracování nahraných audio souborů
  const handleAudioFilesSelected = (files) => {
    setAudioFiles(files);
    setError('');
  };

  // Funkce pro zpracování intro souboru
  const handleIntroFileSelected = (file) => {
    setIntroFile(file);
  };

  // Funkce pro zpracování outro souboru
  const handleOutroFileSelected = (file) => {
    setOutroFile(file);
  };

  // Funkce pro přidání existujícího souboru do seznamu
  const addExistingFile = (existingFile) => {
    // Vytvoří virtuální File objekt s názvem existujícího souboru
    const virtualFile = new File([''], existingFile.filename, {
      type: 'audio/mpeg',
      lastModified: existingFile.modified * 1000
    });
    
    // Označí soubor jako existující na serveru
    virtualFile.isExistingFile = true;
    virtualFile.serverPath = existingFile.filename;
    
    // Přidá do seznamu audio souborů
    setAudioFiles(prev => [...prev, virtualFile]);
  };

  // Funkce pro zpracování vygenerovaných hlasů
  const handleVoicesGenerated = (generatedFiles) => {
    console.log('✅ Vygenerované hlasy:', generatedFiles);
    setGeneratedVoiceFiles(generatedFiles);
    
    // Automaticky zaškrtni titulky a video
    setGenerateSubtitles(true);
    setGenerateVideo(true);
    
    // Předvyplň JSON pro titulky na základě vygenerovaných souborů
    const subtitleMapping = {};
    generatedFiles.forEach(file => {
      // Použije původní text nebo fallback
      const text = file.original_text || `Text pro ${file.block_name}`;
      subtitleMapping[file.filename] = text;
    });
    
    setSubtitleJson(JSON.stringify(subtitleMapping, null, 2));
    
    // AUTOMATICKY PŘIDÁ vygenerované soubory do seznamu ke zpracování
    const virtualFiles = generatedFiles.map(file => {
      const virtualFile = new File([''], file.filename, {
        type: 'audio/mpeg',
        lastModified: Date.now()
      });
      
      // Označí soubor jako existující na serveru
      virtualFile.isExistingFile = true;
      virtualFile.serverPath = file.filename;
      
      return virtualFile;
    });
    
    // DŮLEŽITÉ: Seřadí soubory pro správný dialog (Tesla_01, Socrates_01, Tesla_02, Socrates_02...)
    const sortedFiles = sortFilesForDialog(virtualFiles);
    
    // Vymaže předchozí soubory a přidá pouze nově vygenerované v SPRÁVNÉM POŘADÍ
    setAudioFiles(sortedFiles);
    
    // Zobrazí informační zprávu
    setError('');
    setResult({
      success: true,
      message: `✅ Vygenerováno ${generatedFiles.length} hlasových souborů! Automaticky přidány ke zpracování.`,
      generated_count: generatedFiles.length
    });
    
    // Aktualizuje seznam existujících souborů
    loadExistingFiles();
  };

  // Funkce pro identifikaci voice_id ze jména souboru
  const getVoiceIdFromFilename = (filename) => {
    const name = filename.toLowerCase();
    if (name.startsWith('tesla')) {
      return 'TZJ3e6gtORAbkUEkE87b'; // Tesla voice ID
    } else if (name.startsWith('socrates')) {
      return '2oYYnH4PPhofszUhWldb'; // Socrates voice ID
    }
    return 'unknown'; // Neznámý hlas
  };

  // Funkce pro získání názvu hlasu z voice_id
  const getVoiceNameFromId = (voiceId) => {
    switch (voiceId) {
      case 'TZJ3e6gtORAbkUEkE87b':
        return 'Tesla (Nikola Tesla)';
      case '2oYYnH4PPhofszUhWldb':
        return 'Socrates';
      default:
        return 'Neznámý hlas';
    }
  };

  // Funkce pro extrakci čísla ze jména souboru (Tesla_01 -> 1, Socrates_02 -> 2)
  const getNumberFromFilename = (filename) => {
    const match = filename.match(/_(\d+)/);
    return match ? parseInt(match[1], 10) : 0;
  };

  // Funkce pro správné seřazení souborů pro dialog (Tesla_01, Socrates_01, Tesla_02, Socrates_02...)
  const sortFilesForDialog = (files) => {
    return [...files].sort((a, b) => {
      const filenameA = a.name || a.serverPath;
      const filenameB = b.name || b.serverPath;
      
      const numberA = getNumberFromFilename(filenameA);
      const numberB = getNumberFromFilename(filenameB);
      
      if (numberA !== numberB) {
        return numberA - numberB; // Řadí podle čísla (01, 02, 03...)
      }
      
      // Pokud mají stejné číslo, Tesla jde před Socrates
      const isATesla = filenameA.toLowerCase().startsWith('tesla');
      const isBTesla = filenameB.toLowerCase().startsWith('tesla');
      
      if (isATesla && !isBTesla) return -1; // Tesla před Socrates
      if (!isATesla && isBTesla) return 1;  // Socrates po Tesla
      
      return 0; // Stejné
    });
  };

  // Funkce pro seskupení souborů podle voice_id
  const groupFilesByVoice = () => {
    const groups = {};
    audioFiles.forEach((file, index) => {
      const filename = file.name || file.serverPath;
      const voiceId = getVoiceIdFromFilename(filename);
      
      if (!groups[voiceId]) {
        groups[voiceId] = [];
      }
      groups[voiceId].push({ file, index, filename });
    });
    return groups;
  };

  // Funkce pro odstranění souboru ze seznamu
  const removeFile = (index) => {
    const newFiles = audioFiles.filter((_, i) => i !== index);
    setAudioFiles(newFiles);
  };

  // Funkce pro nastavení hlasitosti celého hlasu (voice_id) - ukládá do localStorage
  const setVoiceVolume = (voiceId, volume) => {
    const numericVolume = parseFloat(volume);
    console.log(`🔊 Nastavuji hlasitost ${voiceId}: ${numericVolume}dB`);
    
    const newVolumes = {
      ...voiceVolumes,
      [voiceId]: numericVolume
    };
    
    // Uloží do localStorage pro budoucí použití
    try {
      localStorage.setItem('voice_volumes', JSON.stringify(newVolumes));
      console.log('💾 Uloženo nastavení hlasitosti do localStorage:', newVolumes);
    } catch (error) {
      console.error('❌ Chyba při ukládání nastavení hlasitosti:', error);
    }
    
    setVoiceVolumes(newVolumes);
  };

  // Funkce pro získání hlasitosti hlasu (výchozí 0 dB)
  const getVoiceVolume = (voiceId) => {
    return voiceVolumes[voiceId] || 0;
  };

  // Funkce pro vymazání všech uložených nastavení hlasitosti
  const resetAllVoiceVolumes = () => {
    try {
      localStorage.removeItem('voice_volumes');
      setVoiceVolumes({});
      console.log('🗑️ Vymazána všechna uložená nastavení hlasitosti');
    } catch (error) {
      console.error('❌ Chyba při mazání nastavení hlasitosti:', error);
    }
  };

  // Funkce pro zpracování vybraného pozadí
  const handleBackgroundSelected = (background) => {
    console.log('📥 App.js přijal pozadí:', background);
    setSelectedBackground(background);
    console.log('✅ Vybrané pozadí nastaveno:', background);
  };

  // Funkce pro zpracování vybraného video pozadí
  const handleVideoBackgroundSelected = (videoBackground) => {
    console.log('📥 App.js přijal video pozadí:', videoBackground);
    setSelectedVideoBackground(videoBackground);
    console.log('✅ Vybrané video pozadí nastaveno:', videoBackground);
  };

  // Funkce pro zpracování a spojení audio souborů
  const handleCombineAudio = async () => {
    console.log('🚀 handleCombineAudio ZAČÍNÁ');
    console.log('📋 Audio soubory:', audioFiles);
    console.log('📋 Počet souborů:', audioFiles.length);

    if (audioFiles.length === 0) {
      setError('Nahrajte alespoň jeden audio soubor!');
      return;
    }

    // Validace JSON pro titulky
    if (generateSubtitles && subtitleJson.trim()) {
      try {
        JSON.parse(subtitleJson);
      } catch (e) {
        setError('Neplatný JSON formát pro titulky!');
        return;
      }
    }

    console.log('✅ Validace prošla, spouštím zpracování...');
    setIsProcessing(true);
    setError('');
    setResult(null);

    try {
      // Připraví FormData pro odeslání
      const formData = new FormData();
      
      // Přidá audio soubory
      console.log('📦 Přidávám audio soubory do FormData:');
      audioFiles.forEach((file, index) => {
        console.log(`  ${index + 1}. ${file.name || file.serverPath}`, {
          size: file.size,
          type: file.type,
          isExistingFile: file.isExistingFile,
          serverPath: file.serverPath,
          lastModified: file.lastModified
        });
        formData.append('audio_files', file);
      });

      // Přidá intro/outro pokud existují
      if (introFile) {
        formData.append('intro_file', introFile);
      }
      if (outroFile) {
        formData.append('outro_file', outroFile);
      }

      // Přidá ostatní parametry
      formData.append('pause_duration', pauseDuration);
      formData.append('generate_subtitles', generateSubtitles);
      formData.append('generate_video', generateVideo);
      
      if (generateSubtitles && subtitleJson.trim()) {
        formData.append('subtitle_json', subtitleJson);
      }

      // Přidá hlasitosti souborů podle voice_id
      const volumeData = {};
      audioFiles.forEach(file => {
        const filename = file.name || file.serverPath;
        const voiceId = getVoiceIdFromFilename(filename);
        const volume = getVoiceVolume(voiceId);
        if (volume !== 0) { // Posílá pouze změněné hlasitosti
          volumeData[filename] = volume;
        }
      });
      console.log('🔊 Posílám data hlasitostí na backend:', volumeData);
      if (Object.keys(volumeData).length > 0) {
        formData.append('file_volumes', JSON.stringify(volumeData));
      }

      // Přidá vybrané pozadí (priorita: video > obrázek)
      if (useVideoBackground && selectedVideoBackground) {
        console.log('🎥 Posílám video pozadí na backend:', selectedVideoBackground.filename);
        formData.append('video_background_filename', selectedVideoBackground.filename);
      } else if (selectedBackground) {
        console.log('🖼️ Posílám obrázek pozadí na backend:', selectedBackground.filename);
        formData.append('background_filename', selectedBackground.filename);
      } else {
        console.log('❌ Žádné pozadí není vybráno!');
      }

      // Odešle požadavek na backend
      console.log('📤 ODESÍLÁM REQUEST na /api/upload...');
      console.log('📦 FormData připravená, odesílám...');
      
      const response = await axios.post('/api/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: 1200000 // 20 minut timeout pro dlouhé zpracování (vhodné pro 100+ souborů)
      });

      console.log('✅ RESPONSE PŘIJATA:', response.data);
      setResult(response.data);
    } catch (err) {
      console.error('❌ CHYBA při zpracování:', err);
      console.error('❌ Error response:', err.response);
      console.error('❌ Error message:', err.message);
      setError(err.response?.data?.error || err.message || 'Došlo k chybě při zpracování!');
    } finally {
      console.log('🏁 Zpracování dokončeno, isProcessing = false');
      setIsProcessing(false);
    }
  };

  // Funkce pro stažení souboru
  const downloadFile = async (filename) => {
    try {
      // Zkusí fetch pro lepší error handling
      const response = await fetch(`/api/download/${filename}`);
      
      if (!response.ok) {
        throw new Error(`Stahování selhalo: ${response.status} ${response.statusText}`);
      }
      
      // Vytvoří blob z odpovědi
      const blob = await response.blob();
      
      // Vytvoří odkaz pro stažení
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      
      // Vyčistí
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      
    } catch (error) {
      console.error('Chyba při stahování:', error);
      setError(`Chyba při stahování souboru: ${error.message}`);
    }
  };

  // Formátování velikosti souboru
  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  // Formátování délky trvání
  const formatDuration = (seconds) => {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Hlavička */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            🎵 AI Voice Block Combiner
          </h1>
          <p className="text-gray-600">
            Spojte více MP3 souborů do jednoho s možností generování titulků
          </p>
        </div>

        {/* Generování hlasů přes ElevenLabs API */}
        <VoiceGenerator 
          onVoicesGenerated={handleVoicesGenerated}
        />

        {/* Hlavní formulář */}
        <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
          {/* Vygenerované hlasové soubory */}
          {generatedVoiceFiles.length > 0 && (
            <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg">
              <h3 className="text-lg font-semibold text-green-800 mb-3">
                🎤 Vygenerované hlasové soubory ({generatedVoiceFiles.length})
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {generatedVoiceFiles.map((file, index) => (
                  <div key={index} className="flex items-center p-3 bg-white rounded border border-green-200">
                    <div className="flex-shrink-0 mr-3">
                      <div className="w-8 h-8 bg-green-100 rounded-full flex items-center justify-center">
                        <span className="text-green-600 text-sm font-semibold">
                          ✓
                        </span>
                      </div>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">
                        {file.filename}
                      </p>
                      <p className="text-xs text-gray-500 truncate">
                        {file.block_name}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-3 p-2 bg-blue-50 border border-blue-200 rounded">
                <p className="text-sm text-blue-800">
                  🚀 <strong>Soubory jsou automaticky přidány ke zpracování!</strong> Můžete rovnou kliknout "Spojit & Exportovat" níže.
                </p>
              </div>
            </div>
          )}

          {/* Upload hlavních audio souborů */}
          <div className="mb-6">
            <FileUploader
              onFilesSelected={handleAudioFilesSelected}
              acceptedFiles={['mp3', 'wav', 'audio']}
              multiple={true}
              label="📁 Hlavní audio soubory (Tesla_1.mp3, Socrates_1.mp3, atd.)"
              placeholder="Nahrajte MP3 soubory, které chcete spojit"
            />
            
            {/* Seznam nahraných souborů seskupených podle hlasu */}
            {audioFiles.length > 0 && (
              <div className="mt-4 space-y-4">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-medium text-gray-700">
                    🎧 Nahrané soubory seskupené podle hlasu ({audioFiles.length}):
                  </h4>
                  <button
                    onClick={() => setAudioFiles(sortFilesForDialog(audioFiles))}
                    className="px-3 py-1 text-xs bg-blue-100 text-blue-700 rounded hover:bg-blue-200 transition duration-200"
                  >
                    🔄 Seřadit pro dialog
                  </button>
                </div>
                
                {Object.entries(groupFilesByVoice()).map(([voiceId, voiceFiles]) => {
                  const currentVolume = getVoiceVolume(voiceId);
                  const voiceName = getVoiceNameFromId(voiceId);
                  
                  return (
                    <div key={voiceId} className="bg-gray-50 p-4 rounded-lg border">
                      {/* Hlavička hlasu */}
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex-1">
                          <h5 className="text-sm font-semibold text-gray-900">{voiceName}</h5>
                          <p className="text-xs text-gray-500">{voiceFiles.length} souborů</p>
                        </div>
                        <div className="text-right flex items-center space-x-2">
                          <span className={`text-sm font-medium ${
                            currentVolume > 0 ? 'text-green-600' : 
                            currentVolume < 0 ? 'text-orange-600' : 
                            'text-gray-600'
                          }`}>
                            {currentVolume > 0 ? '+' : ''}{currentVolume}dB
                          </span>
                          {voiceVolumes[voiceId] !== undefined && (
                            <span className="text-xs bg-green-100 text-green-700 px-1 rounded" title="Uložené nastavení">
                              💾
                            </span>
                          )}
                        </div>
                      </div>
                      
                      {/* Ovládání hlasitosti pro celý hlas */}
                      <div className="flex items-center space-x-3 mb-3">
                        <label className="text-xs text-gray-600 font-medium">
                          🔊 Hlasitost celého hlasu:
                        </label>
                        <div className="flex-1 flex items-center space-x-2">
                          <span className="text-xs text-gray-500 w-8">-20dB</span>
                          <input
                            type="range"
                            min="-20"
                            max="20"
                            step="1"
                            value={currentVolume}
                            onChange={(e) => setVoiceVolume(voiceId, parseFloat(e.target.value))}
                            className="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer slider"
                          />
                          <span className="text-xs text-gray-500 w-8">+20dB</span>
                        </div>
                      </div>
                      
                      {/* Rychlé předvolby */}
                      <div className="flex space-x-1 mb-3">
                        <button
                          onClick={() => setVoiceVolume(voiceId, -6)}
                          className="px-2 py-1 text-xs bg-orange-100 text-orange-700 rounded hover:bg-orange-200"
                        >
                          Tišší (-6dB)
                        </button>
                        <button
                          onClick={() => setVoiceVolume(voiceId, 0)}
                          className="px-2 py-1 text-xs bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
                        >
                          Reset (0dB)
                        </button>
                        <button
                          onClick={() => setVoiceVolume(voiceId, 6)}
                          className="px-2 py-1 text-xs bg-green-100 text-green-700 rounded hover:bg-green-200"
                        >
                          Hlasitější (+6dB)
                        </button>
                      </div>
                      
                      {/* Seznam souborů v této skupině */}
                      <div className="border-t pt-2">
                        <p className="text-xs text-gray-600 mb-2">Soubory v této skupině:</p>
                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                          {voiceFiles.map((item) => (
                            <div key={item.index} className="flex items-center justify-between bg-white p-2 rounded border">
                              <span className="text-xs text-gray-700 truncate">{item.filename}</span>
                              <button
                                onClick={() => removeFile(item.index)}
                                className="text-red-500 hover:text-red-700 text-xs ml-1"
                              >
                                ×
                              </button>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  );
                })}
                
                <div className="p-3 bg-blue-50 border border-blue-200 rounded">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <p className="text-xs text-blue-800">
                        💡 <strong>Skupinové nastavení hlasitosti:</strong> Změna hlasitosti se aplikuje na všechny soubory stejného hlasu najednou. Tesla a Socrates mají nezávislé nastavení.
                      </p>
                      <p className="text-xs text-blue-700 mt-1">
                        🔄 <strong>Pořadí pro dialog:</strong> Soubory se automaticky řadí Tesla_01 → Socrates_01 → Tesla_02 → Socrates_02... Pokud potřebujete, použijte tlačítko "Seřadit pro dialog".
                      </p>
                      <p className="text-xs text-green-700 mt-1">
                        💾 <strong>Paměť nastavení:</strong> Hlasitost se automaticky ukládá a pamatuje při dalším použití aplikace.
                      </p>
                    </div>
                    <button
                      onClick={resetAllVoiceVolumes}
                      className="ml-3 px-2 py-1 text-xs bg-red-100 text-red-700 rounded hover:bg-red-200 transition duration-200"
                      title="Vymaže všechna uložená nastavení hlasitosti"
                    >
                      🗑️ Reset paměti
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Existující soubory ve složce */}
            {existingFiles.length > 0 && (
              <div className="mt-4 space-y-2">
                <h4 className="text-sm font-medium text-gray-700">
                  📁 Dostupné soubory na serveru ({existingFiles.length}):
                </h4>
                <div className="max-h-32 overflow-y-auto custom-scrollbar space-y-1">
                  {existingFiles.map((file, index) => {
                    const isAlreadyAdded = audioFiles.some(af => af.name === file.filename);
                    return (
                      <div key={index} className="flex items-center justify-between bg-blue-50 p-2 rounded">
                        <div className="flex-1">
                          <span className="text-sm text-gray-700">{file.filename}</span>
                          <span className="text-xs text-gray-500 ml-2">
                            ({formatFileSize(file.size)})
                          </span>
                          {isAlreadyAdded && (
                            <span className="text-xs text-green-600 ml-2 font-medium">
                              ✓ Přidáno
                            </span>
                          )}
                        </div>
                        <button
                          onClick={() => addExistingFile(file)}
                          disabled={isAlreadyAdded}
                          className={`text-sm px-2 py-1 rounded ${
                            isAlreadyAdded 
                              ? 'text-gray-400 cursor-not-allowed' 
                              : 'text-blue-600 hover:text-blue-800 hover:bg-blue-100'
                          }`}
                        >
                          {isAlreadyAdded ? '✓' : '+ Přidat'}
                        </button>
                      </div>
                    );
                  })}
                </div>
                <p className="text-xs text-gray-500">
                  💡 Klikněte "+ Přidat" pro použití existujících souborů ve spojování
                </p>
              </div>
            )}
          </div>

          {/* Intro a Outro soubory */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div>
              <FileUploader
                onFilesSelected={handleIntroFileSelected}
                acceptedFiles={['mp3', 'wav', 'audio']}
                multiple={false}
                label="🎤 Intro soubor (volitelné)"
                placeholder="Přetáhněte intro MP3"
              />
              {introFile && (
                <p className="text-xs text-gray-600 mt-1">
                  ✓ {introFile.name} ({formatFileSize(introFile.size)})
                </p>
              )}
            </div>
            
            <div>
              <FileUploader
                onFilesSelected={handleOutroFileSelected}
                acceptedFiles={['mp3', 'wav', 'audio']}
                multiple={false}
                label="🎙️ Outro soubor (volitelné)"
                placeholder="Přetáhněte outro MP3"
              />
              {outroFile && (
                <p className="text-xs text-gray-600 mt-1">
                  ✓ {outroFile.name} ({formatFileSize(outroFile.size)})
                </p>
              )}
            </div>
          </div>

          {/* Nastavení pauzy */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              ⏸️ Délka pauzy mezi bloky: {pauseDuration}s
            </label>
            <input
              type="range"
              min="0.5"
              max="2"
              step="0.1"
              value={pauseDuration}
              onChange={(e) => setPauseDuration(parseFloat(e.target.value))}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer slider"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>0.5s</span>
              <span>2.0s</span>
            </div>
          </div>

          {/* Generování titulků */}
          <div className="mb-6">
            <div className="flex items-center mb-3">
              <input
                type="checkbox"
                id="generateSubtitles"
                checked={generateSubtitles}
                onChange={(e) => setGenerateSubtitles(e.target.checked)}
                className={`h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded ${
                  generatedVoiceFiles.length > 0 && generateSubtitles ? 'ring-2 ring-green-400' : ''
                }`}
              />
              <label htmlFor="generateSubtitles" className="ml-2 text-sm font-medium text-gray-700 flex items-center">
                📝 Generovat titulky (.srt)
                {generatedVoiceFiles.length > 0 && generateSubtitles && (
                  <span className="ml-2 px-2 py-1 text-xs bg-green-100 text-green-700 rounded-full">
                    Auto ✓
                  </span>
                )}
              </label>
            </div>

            {generateSubtitles && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  JSON mapování (název souboru → text):
                </label>
                <textarea
                  value={subtitleJson}
                  onChange={(e) => setSubtitleJson(e.target.value)}
                  placeholder='{"Tesla_1.mp3": "Dobrý den, zde Tesla...", "Socrates_1.mp3": "A já jsem Socrates..."}'
                  className="w-full h-24 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-primary-500 focus:border-primary-500 text-sm"
                />
                <p className="text-xs text-gray-500 mt-1">
                  {generatedVoiceFiles.length > 0 ? (
                    <>
                      💡 <strong>Automaticky předvyplněno</strong> texty z vygenerovaných hlasů - můžete upravit podle potřeby
                    </>
                  ) : (
                    'Zadejte JSON s mapováním názvů souborů na text pro titulky'
                  )}
                </p>
              </div>
            )}
          </div>

          {/* Pozadí pro video */}
          {generateVideo && (
            <div className="mb-6">
              {/* Checkbox pro výběr typu pozadí */}
              <div className="mb-4 p-4 bg-gray-50 border border-gray-200 rounded-lg">
                <h3 className="text-sm font-medium text-gray-900 mb-3">🎨 Typ pozadí pro video:</h3>
                <div className="space-y-2">
                  <div className="flex items-center">
                    <input
                      type="radio"
                      id="image-background"
                      name="background-type"
                      checked={!useVideoBackground}
                      onChange={() => setUseVideoBackground(false)}
                      className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"
                    />
                    <label htmlFor="image-background" className="ml-2 text-sm text-gray-700">
                      🖼️ Obrázek pozadí (statický)
                    </label>
                  </div>
                  <div className="flex items-center">
                    <input
                      type="radio"
                      id="video-background"
                      name="background-type"
                      checked={useVideoBackground}
                      onChange={() => setUseVideoBackground(true)}
                      className="h-4 w-4 text-purple-600 focus:ring-purple-500 border-gray-300"
                    />
                    <label htmlFor="video-background" className="ml-2 text-sm text-gray-700">
                      🎥 Video pozadí (animované)
                    </label>
                  </div>
                </div>
              </div>

              {/* Zobrazí příslušný uploader podle výběru */}
              {useVideoBackground ? (
                <VideoBackgroundUploader onVideoBackgroundSelected={handleVideoBackgroundSelected} />
              ) : (
                <BackgroundUploader onBackgroundSelected={handleBackgroundSelected} />
              )}
            </div>
          )}

          {/* Generování videa */}
          <div className="mb-6">
            <div className="flex items-center mb-3">
              <input
                type="checkbox"
                id="generateVideo"
                checked={generateVideo}
                onChange={(e) => setGenerateVideo(e.target.checked)}
                className={`h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded ${
                  generatedVoiceFiles.length > 0 && generateVideo ? 'ring-2 ring-green-400' : ''
                }`}
              />
              <label htmlFor="generateVideo" className="ml-2 text-sm font-medium text-gray-700 flex items-center">
                🎬 Generovat video (.mp4)
                {generatedVoiceFiles.length > 0 && generateVideo && (
                  <span className="ml-2 px-2 py-1 text-xs bg-green-100 text-green-700 rounded-full">
                    Auto ✓
                  </span>
                )}
              </label>
            </div>
            
            {generateVideo && (
              <div className="bg-blue-50 border border-blue-200 rounded-md p-3">
                <p className="text-sm text-blue-800 font-medium mb-1">
                  📹 Video bude obsahovat:
                </p>
                <ul className="text-xs text-blue-700 space-y-1 ml-4">
                  <li>• {
                    useVideoBackground && selectedVideoBackground 
                      ? `🎥 Video pozadí: ${selectedVideoBackground.filename}` 
                      : selectedBackground 
                        ? `🖼️ Obrázek pozadí: ${selectedBackground.filename}` 
                        : '🌊 Vizuální waveform zobrazení zvuku'
                  }</li>
                  <li>• Audio z vygenerovaného MP3 souboru</li>
                  {generateSubtitles && <li>• Titulky ze SRT souboru (pokud jsou zapnuté)</li>}
                  <li>• Výstupní rozlišení: 1920x1080 (Full HD)</li>
                </ul>
                <p className="text-xs text-blue-600 mt-2">
                  ⏱️ Generování videa může trvat několik minut v závislosti na délce audia.
                  {useVideoBackground && selectedVideoBackground && <span className="block mt-1">🔄 Video pozadí bude automaticky loopováno podle délky audia.</span>}
                </p>
              </div>
            )}
          </div>

          {/* Chybová zpráva */}
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md">
              <p className="text-sm text-red-600">❌ {error}</p>
            </div>
          )}

          {/* Tlačítko pro zpracování */}
          <button
            onClick={handleCombineAudio}
            disabled={isProcessing || audioFiles.length === 0}
            className={`
              w-full py-3 px-4 rounded-md font-medium text-white
              ${isProcessing || audioFiles.length === 0
                ? 'bg-gray-400 cursor-not-allowed' 
                : 'bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2'
              }
              transition duration-200
            `}
          >
            {isProcessing ? (
              <div className="flex flex-col items-center justify-center">
                <span className="flex items-center justify-center mb-2">
                  <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Zpracovávám {audioFiles.length} audio souborů...
                </span>
                {audioFiles.length > 50 && (
                  <span className="text-xs text-white/80">
                    ⏳ Velké množství souborů - může trvat až 20 minut
                  </span>
                )}
              </div>
            ) : (
              '🚀 Spojit & Exportovat'
            )}
          </button>
        </div>

        {/* Výsledky */}
        {result && (
          <div className="bg-white rounded-lg shadow-lg p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">
              ✅ Zpracování dokončeno!
            </h3>
            
            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 bg-green-50 rounded-md">
                <div>
                  <p className="text-sm font-medium text-green-800">
                    🎵 final_output.mp3
                  </p>
                  <p className="text-xs text-green-600">
                    Délka: {formatDuration(result.duration)} | 
                    Segmentů: {result.segments_count}
                  </p>
                </div>
                <button
                  onClick={() => downloadFile(result.audio_file)}
                  className="px-4 py-2 bg-green-600 text-white text-sm rounded-md hover:bg-green-700 transition duration-200"
                >
                  📥 Stáhnout
                </button>
              </div>

              {result.subtitle_file && (
                <div className="flex items-center justify-between p-3 bg-blue-50 rounded-md">
                  <div>
                    <p className="text-sm font-medium text-blue-800">
                      📝 final_output.srt
                    </p>
                    <p className="text-xs text-blue-600">
                      Soubor s titulky
                    </p>
                  </div>
                  <button
                    onClick={() => downloadFile(result.subtitle_file)}
                    className="px-4 py-2 bg-blue-600 text-white text-sm rounded-md hover:bg-blue-700 transition duration-200"
                  >
                    📥 Stáhnout
                  </button>
                </div>
              )}

              {result.video_file && (
                <div className="flex items-center justify-between p-3 bg-purple-50 rounded-md">
                  <div>
                    <p className="text-sm font-medium text-purple-800">
                      🎬 final_output.mp4
                    </p>
                    <p className="text-xs text-purple-600">
                      {result.video_background_used 
                        ? `🎥 Video s video pozadím${generateSubtitles ? ' a titulky' : ''}`
                        : result.background_used 
                          ? `🖼️ Video s obrázkem pozadí${generateSubtitles ? ' a titulky' : ''}`
                          : `🌊 Video s waveform${generateSubtitles ? ' a titulky' : ''}`
                      }
                    </p>
                    {result.video_message && (
                      <p className="text-xs text-purple-500 mt-1">
                        ✅ {result.video_message}
                      </p>
                    )}
                  </div>
                  <button
                    onClick={() => downloadFile(result.video_file)}
                    className="px-4 py-2 bg-purple-600 text-white text-sm rounded-md hover:bg-purple-700 transition duration-200"
                  >
                    📥 Stáhnout
                  </button>
                </div>
              )}

              {result.video_error && (
                <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-md">
                  <p className="text-sm font-medium text-yellow-800">
                    ⚠️ Video se nepodařilo vygenerovat
                  </p>
                  <p className="text-xs text-yellow-700 mt-1">
                    {result.video_error}
                  </p>
                  <p className="text-xs text-yellow-600 mt-1">
                    Audio a titulky jsou k dispozici, pouze video generování selhalo.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App; 