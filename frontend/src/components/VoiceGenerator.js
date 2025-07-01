import React, { useState } from 'react';
import axios from 'axios';

const VoiceGenerator = ({ onVoicesGenerated }) => {
  const [voiceBlocksJson, setVoiceBlocksJson] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  
  // Nové stavy pro automatické generování z tématu
  const [documentaryTopic, setDocumentaryTopic] = useState('');
  const [documentaryStyle, setDocumentaryStyle] = useState('Cinematic, BBC-style, serious tone');
  const [isGeneratingFromTopic, setIsGeneratingFromTopic] = useState(false);

  // Načte API klíč z localStorage při spuštění
  React.useEffect(() => {
    const savedApiKey = localStorage.getItem('elevenlabs_api_key');
    if (savedApiKey) {
      setApiKey(savedApiKey);
    }
  }, []);

  // Uloží API klíč do localStorage při změně
  const handleApiKeyChange = (newApiKey) => {
    setApiKey(newApiKey);
    if (newApiKey.trim()) {
      localStorage.setItem('elevenlabs_api_key', newApiKey);
    } else {
      localStorage.removeItem('elevenlabs_api_key');
    }
  };

  // Ukázkový JSON pro uživatele
  const exampleJson = {
    "Tesla_1": {
      "text": "Dobrý den, já jsem Nikola Tesla. Dnes budu mluvit o elektřině a budoucnosti energetiky.",
      "voice_id": "21m00Tcm4TlvDq8ikWAM"
    },
    "Socrates_1": {
      "text": "Zdravím vás, já jsem Socrates. Pojďme společně filosofovat o podstatě poznání.",
      "voice_id": "AZnzlk1XvdvUeBnXmlld"
    },
    "Tesla_2": {
      "text": "Bezdrátový přenos energie je klíčem k osvobození lidstva od závislosti na drátěné infrastruktuře.",
      "voice_id": "21m00Tcm4TlvDq8ikWAM"
    }
  };

  const handleGenerateVoices = async () => {
    console.log('🚀 handleGenerateVoices ZAČÍNÁ');
    console.log('📝 JSON input:', voiceBlocksJson);
    console.log('🔑 API key:', apiKey ? '***nastaven***' : 'CHYBÍ');

    if (!voiceBlocksJson.trim()) {
      setError('Zadejte JSON definici hlasových bloků!');
      return;
    }

    if (!apiKey.trim()) {
      setError('Zadejte ElevenLabs API klíč!');
      return;
    }

    // Validace JSON
    let voiceBlocks;
    try {
      voiceBlocks = JSON.parse(voiceBlocksJson);
      console.log('✅ JSON parsován úspěšně:', voiceBlocks);
    } catch (e) {
      console.error('❌ JSON parse error:', e);
      setError('Neplatný JSON formát!');
      return;
    }

    console.log('📤 Odesílám request na backend...');
    setIsGenerating(true);
    setError('');
    setResult(null);

    try {
      const requestData = {
        voice_blocks: voiceBlocks,
        api_key: apiKey
      };
      console.log('📦 Request data:', requestData);
      
      const response = await axios.post('/api/generate-voices', requestData);
      console.log('✅ Response úspěšná:', response.data);

      setResult(response.data);
      
      // Informuje parent komponentu o nových souborech včetně původních textů
      if (response.data.generated_files && onVoicesGenerated) {
        // Přidá původní texty k souborům pro lepší UX
        const filesWithTexts = response.data.generated_files.map(file => ({
          ...file,
          original_text: voiceBlocks[file.block_name]?.text || ''
        }));
        onVoicesGenerated(filesWithTexts);
      }
    } catch (err) {
      console.error('❌ Request error:', err);
      console.error('❌ Response data:', err.response?.data);
      console.error('❌ Error message:', err.message);
      // Nová logika: Zobrazí detailní zprávu z backendu pokud existuje
      const backendData = err.response?.data;
      let friendlyMsg = err.message || 'Došlo k chybě při generování hlasů!';
      if (backendData) {
        if (backendData.errors && Array.isArray(backendData.errors) && backendData.errors.length > 0) {
          friendlyMsg = backendData.errors[0];
        } else if (backendData.error) {
          friendlyMsg = backendData.error;
        } else if (backendData.message) {
          friendlyMsg = backendData.message;
        }
      }
      setError(friendlyMsg);
    } finally {
      console.log('🏁 Generování dokončeno');
      setIsGenerating(false);
    }
  };

  const loadExampleJson = () => {
    try {
      const formattedJson = JSON.stringify(exampleJson, null, 2);
      setVoiceBlocksJson(formattedJson);
      setError(''); // Vymaže předchozí chyby
      setResult(null); // Vymaže předchozí výsledky
      console.log('✅ Ukázka načtena úspěšně');
    } catch (err) {
      setError('Chyba při načítání ukázky: ' + err.message);
      console.error('❌ Chyba při načítání ukázky:', err);
    }
  };

  // Funkce pro generování JSON z tématu pomocí OpenAI
  const handleGenerateFromTopic = async () => {
    console.log('🎬 Generuji dokumentární naraci z tématu...');
    console.log('📝 Téma:', documentaryTopic);
    console.log('🎭 Styl:', documentaryStyle);

    if (!documentaryTopic.trim()) {
      setError('Zadejte téma dokumentu!');
      return;
    }

    setIsGeneratingFromTopic(true);
    setError('');
    setResult(null);

    try {
      const requestData = {
        topic: documentaryTopic.trim(),
        style: documentaryStyle.trim()
      };
      console.log('📤 Odesílám request na /api/generate-narration:', requestData);
      
      const response = await axios.post('/api/generate-narration', requestData);
      console.log('✅ Response úspěšná:', response.data);

      if (response.data.success && response.data.data.narration) {
        // Převede naraci do správného formátu a vloží do JSON textarea
        const generatedNarration = response.data.data.narration;
        const formattedJson = JSON.stringify(generatedNarration, null, 2);
        setVoiceBlocksJson(formattedJson);
        
        // Zobrazí úspěšnou zprávu
        setResult({
          success: true,
          message: `✅ Dokumentární narrace vygenerována úspěšně! ${response.data.data.metadata.blocks_count} bloků připraveno ke generování hlasu.`,
          generated_count: response.data.data.metadata.blocks_count,
          topic: documentaryTopic,
          style: documentaryStyle
        });
        
        console.log('✅ JSON narrace vložena do textarea');
      } else {
        setError('Neočekávaná odpověď ze serveru');
      }
    } catch (err) {
      console.error('❌ Request error:', err);
      const backendData = err.response?.data;
      let friendlyMsg = err.message || 'Došlo k chybě při generování dokumentární narrace!';
      if (backendData?.error) {
        friendlyMsg = backendData.error;
      }
      setError(friendlyMsg);
    } finally {
      console.log('🏁 Generování z tématu dokončeno');
      setIsGeneratingFromTopic(false);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-gray-900">
          🎤 Generování hlasů (ElevenLabs API)
        </h2>
        <button
          onClick={loadExampleJson}
          className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200 transition duration-200"
        >
          📝 Načíst ukázku
        </button>
      </div>

      {/* API klíč */}
      <div className="mb-4">
        <div className="flex justify-between items-center mb-2">
          <label className="block text-sm font-medium text-gray-700">
            🔑 ElevenLabs API klíč:
          </label>
          {apiKey && (
            <button
              onClick={() => handleApiKeyChange('')}
              className="text-xs text-red-600 hover:text-red-800 underline"
            >
              🗑️ Vymazat
            </button>
          )}
        </div>
        <input
          type="password"
          value={apiKey}
          onChange={(e) => handleApiKeyChange(e.target.value)}
          placeholder="sk-..."
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-primary-500 focus:border-primary-500"
        />
        <div className="flex justify-between items-center mt-1">
          <p className="text-xs text-gray-500">
            Získejte API klíč na <a href="https://elevenlabs.io" target="_blank" rel="noopener noreferrer" className="text-primary-600 hover:underline">elevenlabs.io</a>
          </p>
          {apiKey && (
            <p className="text-xs text-green-600 font-medium">
              💾 Uloženo
            </p>
          )}
        </div>
      </div>

      {/* NOVÁ SEKCE: Automatické generování z tématu */}
      <div className="mb-6 border-t border-gray-200 pt-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          🎬 Automatické generování dokumentu z tématu
        </h3>
        
        {/* Téma dokumentu */}
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            📝 Téma dokumentu:
          </label>
          <input
            type="text"
            value={documentaryTopic}
            onChange={(e) => setDocumentaryTopic(e.target.value)}
            placeholder="např. The Fall of the Roman Empire, World War II, Evolution of Technology..."
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-primary-500 focus:border-primary-500"
          />
          <p className="text-xs text-gray-500 mt-1">
            Zadejte téma, o kterém chcete vytvořit 20-minutový dokumentární voiceover
          </p>
        </div>

        {/* Styl dokumentu */}
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            🎭 Styl dokumentu:
          </label>
          <select
            value={documentaryStyle}
            onChange={(e) => setDocumentaryStyle(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-primary-500 focus:border-primary-500"
          >
            <option value="Cinematic, BBC-style, serious tone">🎥 Filmový, BBC styl, vážný tón</option>
            <option value="Educational, National Geographic style, engaging">📚 Vzdělávací, National Geographic styl</option>
            <option value="Dramatic, History Channel style, suspenseful">🎭 Dramatický, History Channel styl</option>
            <option value="Conversational, podcast style, accessible">🎙️ Konverzační, podcast styl</option>
            <option value="Academic, scholarly tone, detailed">🎓 Akademický, odborný tón</option>
          </select>
          <p className="text-xs text-gray-500 mt-1">
            Vyberte styl a tón dokumentu
          </p>
        </div>

        {/* Informační box o funkci */}
        <div className="bg-blue-50 border border-blue-200 rounded-md p-3 mb-4">
          <p className="text-sm text-blue-800 font-medium mb-1">
            🤖 Jak funguje automatické generování:
          </p>
          <ol className="text-xs text-blue-700 space-y-1 ml-4">
            <li>1. Zadejte téma a styl dokumentu</li>
            <li>2. OpenAI GPT-4o vygeneruje 40 narativních bloků (20 minut obsahu)</li>
            <li>3. JSON se automaticky vloží do pole níže</li>
            <li>4. Poté můžete JSON upravit nebo rovnou generovat hlasy</li>
          </ol>
        </div>

        {/* Tlačítko pro generování z tématu */}
        <button
          onClick={handleGenerateFromTopic}
          disabled={isGeneratingFromTopic || !documentaryTopic.trim()}
          className={`
            w-full py-3 px-4 rounded-md font-medium text-white mb-4
            ${isGeneratingFromTopic || !documentaryTopic.trim()
              ? 'bg-gray-400 cursor-not-allowed' 
              : 'bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2'
            }
            transition duration-200
          `}
        >
          {isGeneratingFromTopic ? (
            <span className="flex items-center justify-center">
              <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Generuji dokumentární naraci...
            </span>
          ) : (
            '🎬 Generovat dokumentární naraci z tématu'
          )}
        </button>
      </div>

      {/* JSON definice */}
      <div className="mb-4">
        <div className="flex justify-between items-center mb-2">
          <label className="block text-sm font-medium text-gray-700">
            📋 JSON definice hlasových bloků:
          </label>
          <span className="text-xs text-gray-500">
            {voiceBlocksJson ? '📝 Upravit' : '✍️ Ručně zadat'} 
          </span>
        </div>
        <textarea
          value={voiceBlocksJson}
          onChange={(e) => setVoiceBlocksJson(e.target.value)}
          placeholder='{"Tesla_1": {"text": "...", "voice_id": "..."}, ...}'
          className="w-full h-40 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-primary-500 focus:border-primary-500 text-sm font-mono"
        />
        <div className="flex justify-between items-center mt-1">
          <p className="text-xs text-gray-500">
            Formát: {`{"name": {"text": "text k namluvení", "voice_id": "ElevenLabs voice ID"}}`}
          </p>
          <p className="text-xs text-gray-400">
            {voiceBlocksJson.length} znaků
          </p>
        </div>
      </div>

      {/* Informační box */}
      <div className="bg-blue-50 border border-blue-200 rounded-md p-3 mb-4">
        <p className="text-sm text-blue-800 font-medium mb-1">
          💡 Jak získat Voice ID:
        </p>
        <ol className="text-xs text-blue-700 space-y-1 ml-4">
          <li>1. Přihlaste se na <a href="https://elevenlabs.io" target="_blank" rel="noopener noreferrer" className="underline">elevenlabs.io</a></li>
          <li>2. Jděte na "Voice Library" nebo vytvořte vlastní hlas</li>
          <li>3. Zkopírujte Voice ID (např. "21m00Tcm4TlvDq8ikWAM")</li>
          <li>4. Každý blok může použít jiný hlas pro různé postavy</li>
        </ol>
      </div>

      {/* Chybová zpráva */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md">
          <p className="text-sm text-red-600">❌ {error}</p>
        </div>
      )}

      {/* Tlačítko generování */}
      <button
        onClick={handleGenerateVoices}
        disabled={isGenerating || !voiceBlocksJson.trim() || !apiKey.trim()}
        className={`
          w-full py-3 px-4 rounded-md font-medium text-white
          ${isGenerating || !voiceBlocksJson.trim() || !apiKey.trim()
            ? 'bg-gray-400 cursor-not-allowed' 
            : 'bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2'
          }
          transition duration-200
        `}
      >
        {isGenerating ? (
          <span className="flex items-center justify-center">
            <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Generuji hlasy...
          </span>
        ) : (
          '🎤 Generovat hlasy'
        )}
      </button>

      {/* Výsledky */}
      {result && (
        <div className="mt-6 p-4 bg-gray-50 rounded-md">
          <h3 className="text-lg font-semibold text-gray-900 mb-3">
            {result.success ? '✅' : '❌'} Výsledky generování
          </h3>
          
          <div className="space-y-2">
            <p className="text-sm text-gray-700">
              <strong>Status:</strong> {result.message}
            </p>
            <p className="text-sm text-gray-700">
              <strong>Vygenerováno:</strong> {result.total_generated}/{result.total_requested} hlasových bloků
            </p>
          </div>

          {result.generated_files && result.generated_files.length > 0 && (
            <div className="mt-3">
              <p className="text-sm font-medium text-green-800 mb-2">
                🎵 Vygenerované soubory:
              </p>
              <div className="space-y-1">
                {result.generated_files.map((file, index) => (
                  <div key={index} className="text-xs text-green-700 bg-green-50 p-2 rounded">
                    <strong>{file.filename}</strong> - {file.block_name}
                  </div>
                ))}
              </div>
              <p className="text-xs text-gray-600 mt-2">
                💡 Soubory jsou automaticky dostupné v sekci "Hlavní audio soubory" níže.
              </p>
            </div>
          )}

          {result.errors && result.errors.length > 0 && (
            <div className="mt-3">
              <p className="text-sm font-medium text-red-800 mb-2">
                ❌ Chyby ({result.error_count}):
              </p>
              <div className="space-y-1">
                {result.errors.map((error, index) => (
                  <div key={index} className="text-xs text-red-700 bg-red-50 p-2 rounded">
                    {error}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default VoiceGenerator; 