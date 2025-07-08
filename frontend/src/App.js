import React, { useState } from 'react';
import axios from 'axios';
import FileUploader from './components/FileUploader';
import VoiceGenerator from './components/VoiceGenerator';
import VideoProductionPipeline from './components/VideoProductionPipeline';
import BackgroundUploader from './components/BackgroundUploader';
import VideoBackgroundUploader from './components/VideoBackgroundUploader';
import AssistantManager from './components/AssistantManager';

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
  
  // OpenAI Asistenti stavy - POZOR: Nepoužité po odstranění rychlého testu
  // eslint-disable-next-line no-unused-vars
  const [selectedAssistant, setSelectedAssistant] = useState('general');
  const [assistantPrompt, setAssistantPrompt] = useState('');
  // eslint-disable-next-line no-unused-vars
  const [assistantResponse, setAssistantResponse] = useState('');
  // eslint-disable-next-line no-unused-vars
  const [isAssistantLoading, setIsAssistantLoading] = useState(false);

  // Nové modaly stavy
  const [showAddAssistantModal, setShowAddAssistantModal] = useState(false);
  const [showApiKeyModal, setShowApiKeyModal] = useState(false);
  const [apiTestResults, setApiTestResults] = useState(null);
  const [isTestingApi, setIsTestingApi] = useState(false);
  
  // DALL-E stavy
  const [dallePrompt, setDallePrompt] = useState('');
  const [isGeneratingImage, setIsGeneratingImage] = useState(false);
  const [generatedImage, setGeneratedImage] = useState(null);
  
  // Test OpenAI Assistants stavy
  const [selectedTestAssistant, setSelectedTestAssistant] = useState('');
  const [testAssistantPrompt, setTestAssistantPrompt] = useState('Ahoj, kdo jsi?');
  const [isTestingAssistant, setIsTestingAssistant] = useState(false);
  const [testAssistantResult, setTestAssistantResult] = useState(null);
  
  const [newAssistantName, setNewAssistantName] = useState('');
  const [newAssistantId, setNewAssistantId] = useState('');
  const [newAssistantDescription, setNewAssistantDescription] = useState('');
  const [newAssistantCategory, setNewAssistantCategory] = useState('podcast'); // Nový stav pro kategorii
  // API klíče stav
  const [openaiApiKey, setOpenaiApiKey] = useState(() => {
    try {
      return localStorage.getItem('openai_api_key') || '';
    } catch (error) {
      return '';
    }
  });
  
  const [elevenlabsApiKey, setElevenlabsApiKey] = useState(() => {
    try {
      return localStorage.getItem('elevenlabs_api_key') || '';
    } catch (error) {
      return '';
    }
  });
  
  const [youtubeApiKey, setYoutubeApiKey] = useState(() => {
    try {
      return localStorage.getItem('youtube_api_key') || '';
    } catch (error) {
      return '';
    }
  });

    // YouTube projekty stavy
  const [showYouTubeModal, setShowYouTubeModal] = useState(false);
  const [selectedYouTubeProject, setSelectedYouTubeProject] = useState(null);
  const [showUploadConfirm, setShowUploadConfirm] = useState(false);

  // Mock data pro YouTube projekty
  const mockYouTubeProjects = [
    {
      id: 1,
      title: "Tesla vs Socrates: Elektrické vynálezy a filosofie",
      thumbnail: "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIwIiBoZWlnaHQ9IjE4MCIgdmlld0JveD0iMCAwIDMyMCAxODAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIzMjAiIGhlaWdodD0iMTgwIiBmaWxsPSIjMjU2M2ViIi8+Cjx0ZXh0IHg9IjE2MCIgeT0iOTAiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxNCIgZmlsbD0id2hpdGUiIHRleHQtYW5jaG9yPSJtaWRkbGUiPllvdVR1YmUgVmlkZW88L3RleHQ+Cjwvc3ZnPg==",
      description: "Fascinující dialog mezi Nikolou Teslou a Sokratem o elektrických vynálezech, filosofii vědy a budoucnosti technologií. Video kombinuje historické postavy s moderním přístupem k vzdělávání.",
      duration: "24:37",
      files: {
        mp3: "final_output_tesla_socrates_debate.mp3",
        srt: "final_output_tesla_socrates_debate.srt", 
        mp4: "final_output_tesla_socrates_debate.mp4"
      },
      created_at: "2025-07-03T12:30:00.000Z",
      filesSizes: {
        mp3: 35672840, // ~35 MB
        srt: 12450,    // ~12 KB  
        mp4: 156892304 // ~157 MB
      },
      tags: ["Tesla", "Socrates", "filosofie", "věda", "historie"],
      category: "Vzdělávání"
    },
    {
      id: 2,
      title: "Průvodce React Hooks pro začátečníky",
      thumbnail: "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIwIiBoZWlnaHQ9IjE4MCIgdmlld0JveD0iMCAwIDMyMCAxODAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIzMjAiIGhlaWdodD0iMTgwIiBmaWxsPSIjMTBiOTgxIi8+Cjx0ZXh0IHg9IjE2MCIgeT0iOTAiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxNCIgZmlsbD0id2hpdGUiIHRleHQtYW5jaG9yPSJtaWRkbGUiPlJlYWN0IFR1dG9yaWFsPC90ZXh0Pgo8L3N2Zz4=",
      description: "Kompletní průvodce React Hooks s praktickými příklady. Naučte se useState, useEffect, useContext a další pokročilé hooks. Ideální pro začátečníky i pokročilé vývojáře.",
      duration: "18:42",
      files: {
        mp3: "react_hooks_tutorial.mp3",
        srt: "react_hooks_tutorial.srt",
        mp4: "react_hooks_tutorial.mp4"
      },
      created_at: "2025-07-03T09:15:00.000Z",
      filesSizes: {
        mp3: 26890150, // ~27 MB
        srt: 8920,     // ~9 KB
        mp4: 112405678 // ~112 MB  
      },
      tags: ["React", "JavaScript", "tutorial", "programování", "hooks"],
      category: "Technologie"
    },
    {
      id: 3,
      title: "Kreativní tipy pro YouTube tvůrce",
      thumbnail: "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIwIiBoZWlnaHQ9IjE4MCIgdmlld0JveD0iMCAwIDMyMCAxODAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIzMjAiIGhlaWdodD0iMTgwIiBmaWxsPSIjZGMyNjI2Ii8+Cjx0ZXh0IHg9IjE2MCIgeT0iOTAiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxNCIgZmlsbD0id2hpdGUiIHRleHQtYW5jaG9yPSJtaWRkbGUiPllvdVR1YmUgVGlwczwvdGV4dD4KPC9zdmc+",
      description: "Objevte nejlepší kreativní techniky pro tvorbu YouTube obsahu. Tipy na thumbnaily, storytelling, editaci a engagement. Získejte více views a subscribers.",
      duration: "16:28",
      files: {
        mp3: "youtube_creative_tips.mp3",
        srt: "youtube_creative_tips.srt",
        mp4: "youtube_creative_tips.mp4"
      },
      created_at: "2025-07-02T16:45:00.000Z",
      filesSizes: {
        mp3: 23750320, // ~24 MB
        srt: 7680,     // ~8 KB
        mp4: 95328756  // ~95 MB
      },
      tags: ["YouTube", "kreativita", "marketing", "video", "obsah"],
      category: "Marketing"
    }
  ];

  // Mock data pro demonstraci
  const mockProjects = [
    {
      id: 1,
      title: "Jak vytvořit úspěšný podcast",
      assistant_type: "podcast", 
      original_prompt: "Navrhni mi kompletní průvodce jak začít úspěšný podcast",
      response: "Vytvoření úspěšného podcastu vyžaduje pečlivé plánování a konzistentní práci. Začněte výběrem tématu, které vás skutečně zajímá a v kterém máte expertise. Definujte svou cílovou skupinu a typ obsahu. Investujte do kvalitního mikrofonu a naučte se základy editace zvuku. Vytvořte konzistentní harmonogram vydávání a budujte komunitu kolem svého obsahu. Nezapomeňte na marketing a propagaci na sociálních sítích.",
      character_count: 1247,
      created_at: "2025-07-03T10:30:00.000Z",
      preview: "Vytvoření úspěšného podcastu vyžaduje pečlivé plánování a konzistentní práci. Začněte výběrem tématu..."
    },
    {
      id: 2,
      title: "Technický návod na React hooks",
      assistant_type: "technical",
      original_prompt: "Vysvětli mi React hooks a kdy je použít",
      response: "React Hooks jsou funkce, které umožňují používat state a další React funkcionality ve funkčních komponentách. Nejčastěji používané hooks jsou useState pro správu lokálního stavu, useEffect pro side effects a lifecycle metody. UseContext umožňuje přístup k Context API, useMemo a useCallback optimalizují výkon. Hooks musí být volány vždy ve stejném pořadí a pouze na top-level funkce.",
      character_count: 892,
      created_at: "2025-07-03T09:15:00.000Z", 
      preview: "React Hooks jsou funkce, které umožňují používat state a další React funkcionality ve funkčních..."
    },
    {
      id: 3,
      title: "Kreativní nápady pro video obsah",
      assistant_type: "creative",
      original_prompt: "Potřebuji kreativní nápady na video obsah pro YouTube",
      response: "Pro YouTube obsah zkuste formáty jako 'Den v životě', tutoriály, reaction videa, nebo Q&A s followers. Populární jsou také challenge videa, behind-the-scenes obsah, a kolaborace s jinými tvůrci. Experimentujte s různými žánry - komedi, edukace, lifestyle. Používejte trendy hashtags a aktuální témata. Investujte do kvalitního thumbnail designu a poutavých titulků. Analyzujte svou cílovou skupinu a přizpůsobte obsah jejich zájmům.",
      character_count: 1156,
      created_at: "2025-07-02T16:45:00.000Z",
      preview: "Pro YouTube obsah zkuste formáty jako 'Den v životě', tutoriály, reaction videa, nebo Q&A s followers..."
    }
  ];

  // Vygenerované projekty stavy - načte z localStorage nebo použije mock data
  const [generatedProjects, setGeneratedProjects] = useState(() => {
    try {
      const saved = localStorage.getItem('generated_projects');
      const savedProjects = saved ? JSON.parse(saved) : [];
      // Pokud nejsou žádné uložené projekty, použij mock data
      return savedProjects.length > 0 ? savedProjects : mockProjects;
    } catch (error) {
      console.error('Chyba při načítání projektů z localStorage:', error);
      return mockProjects; // Fallback na mock data
    }
  });
  const [selectedProject, setSelectedProject] = useState(null);
  const [showProjectDetail, setShowProjectDetail] = useState(false);
  
  // Nový stav pro hlasitosti podle voice_id (v dB, 0 = bez změny) - načte z localStorage
  const [voiceVolumes, setVoiceVolumes] = useState(() => {
    try {
      const saved = localStorage.getItem('voice_volumes');
      const parsed = saved ? JSON.parse(saved) : {};
      console.log('Načítám uložená nastavení hlasitosti:', parsed);
      return parsed;
    } catch (error) {
      console.error('Chyba při načítání nastavení hlasitosti:', error);
      return {};
    }
  });

  // Stav pro propojení Video Production Pipeline -> VoiceGenerator
  const [autoJsonFromPipeline, setAutoJsonFromPipeline] = useState(null);

  // Stav pro skryté asistenty
  const [hiddenAssistants, setHiddenAssistants] = useState([]);

  // Dostupní OpenAI asistenti - načte z localStorage nebo použije výchozí
  const [availableAssistants, setAvailableAssistants] = useState(() => {
    try {
      const saved = localStorage.getItem('available_assistants');
      if (saved) {
        return JSON.parse(saved);
      }
    } catch (error) {
      console.error('Chyba při načítání asistentů:', error);
    }
    // Výchozí asistenti
    return [
      { id: 'general', name: 'Obecný asistent', description: 'Univerzální pomocník pro různé úkoly' },
      { id: 'creative', name: 'Kreativní asistent', description: 'Pomoc s tvůrčím psaním a nápady' },
      { id: 'technical', name: 'Technický asistent', description: 'Programování a technické dotazy' },
      { id: 'podcast', name: 'Podcast asistent', description: 'Pomoc s tvorbou podcastů a dialogů' },
      { id: 'research', name: 'Výzkumný asistent', description: 'Analýza dat a výzkum' }
    ];
  });

  // Funkce pro načtení skrytých asistentů
  const loadHiddenAssistants = async () => {
    if (!openaiApiKey) return;

    try {
      const response = await fetch('/api/list-hidden-assistants', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          openai_api_key: openaiApiKey
        }),
      });

      const data = await response.json();

      if (response.ok) {
        setHiddenAssistants(data.hidden_assistants?.map(a => a.id) || []);
      }
    } catch (err) {
      console.error('Chyba při načítání skrytých asistentů:', err);
    }
  };

  // Funkce pro filtrování viditelných asistentů
  const getVisibleAssistants = () => {
    return availableAssistants.filter(assistant => 
      !hiddenAssistants.includes(assistant.id)
    );
  };

  // Načti skryté asistenty při změně API klíče
  React.useEffect(() => {
    if (openaiApiKey) {
      loadHiddenAssistants();
    }
  }, [openaiApiKey]);

  // Funkce pro otevření detailu projektu
  const openProjectDetail = (project) => {
    setSelectedProject(project);
    setShowProjectDetail(true);
  };

  // Funkce pro zavření detailu projektu
  const closeProjectDetail = () => {
    setSelectedProject(null);
    setShowProjectDetail(false);
  };

  // Funkce pro potvrzení projektu
  const handleProjectConfirm = (project) => {
    console.log('Projekt potvrzen:', project);
    setResult({ 
      success: true, 
      message: `Projekt "${project.title}" byl úspěšně potvrzen!` 
    });
  };

  // Funkce pro práci s modaly
  const openAddAssistantModal = () => {
    setShowAddAssistantModal(true);
    setNewAssistantName('');
    setNewAssistantId('');
    setNewAssistantDescription('');
  };

  const closeAddAssistantModal = () => {
    setShowAddAssistantModal(false);
    setNewAssistantName('');
    setNewAssistantId('');
    setNewAssistantDescription('');
  };

  const openApiKeyModal = () => {
    setShowApiKeyModal(true);
  };

  const closeApiKeyModal = () => {
    setShowApiKeyModal(false);
  };

  // Funkce pro přidání nového asistenta
  const handleAddAssistant = () => {
    if (!newAssistantName.trim() || !newAssistantId.trim()) {
      setError('Vyplňte prosím název a OpenAI Assistant ID');
      return;
    }

    // Validace formátu OpenAI Assistant ID
    if (!newAssistantId.trim().startsWith('asst_')) {
      setError('OpenAI Assistant ID musí začínat "asst_"');
      return;
    }

    // Kontrola duplicity ID
    if (availableAssistants.find(a => a.id === newAssistantId.trim())) {
      setError('Asistent s tímto ID již existuje');
      return;
    }

    const newAssistant = {
      id: newAssistantId.trim(),
      name: newAssistantName.trim(),
      description: newAssistantDescription.trim() || 'Vlastní OpenAI asistent',
      type: 'openai_assistant', // Označíme, že je to OpenAI Assistant
      category: newAssistantCategory // Přidáme kategorii (podcast/document)
    };

    const updatedAssistants = [...availableAssistants, newAssistant];
    setAvailableAssistants(updatedAssistants);

    // Uložit do localStorage
    try {
      localStorage.setItem('available_assistants', JSON.stringify(updatedAssistants));
      setResult({
        success: true,
        message: `OpenAI Asistent "${newAssistantName}" byl úspěšně přidán!`
      });
    } catch (error) {
      console.error('Chyba při ukládání asistentů:', error);
      setError('Chyba při ukládání asistenta');
      return;
    }

    // Vyčištění formuláře
    setNewAssistantName('');
    setNewAssistantId('');
    setNewAssistantDescription('');
    setNewAssistantCategory('podcast');
    
    closeAddAssistantModal();
  };

  // Funkce pro uložení API klíče
  const handleSaveApiKey = () => {
    try {
      localStorage.setItem('openai_api_key', openaiApiKey);
      localStorage.setItem('elevenlabs_api_key', elevenlabsApiKey);
      localStorage.setItem('youtube_api_key', youtubeApiKey);
      
      setResult({
        success: true,
        message: 'API klíče byly úspěšně uloženy!'
      });
      closeApiKeyModal();
    } catch (error) {
      setError('Chyba při ukládání API klíčů');
      console.error('Chyba při ukládání API klíčů:', error);
    }
  };

  // Funkce pro testování API připojení
  const handleTestApiConnections = async () => {
    setIsTestingApi(true);
    setApiTestResults(null);
    
    try {
      const response = await axios.post('/api/test-api-connections', {
        openai_api_key: openaiApiKey,
        elevenlabs_api_key: elevenlabsApiKey,
        youtube_api_key: youtubeApiKey
      }, {
        timeout: 30000
      });
      
      setApiTestResults(response.data.results);
      
    } catch (err) {
      console.error('Chyba při testování API:', err);
      setError(err.response?.data?.error || 'Chyba při testování API připojení');
    } finally {
      setIsTestingApi(false);
    }
  };

  // Funkce pro testování OpenAI Assistant
  const handleTestAssistant = async () => {
    if (!selectedTestAssistant || !testAssistantPrompt.trim()) {
      setError('Vyberte assistant a zadejte test prompt');
      return;
    }

    if (!openaiApiKey) {
      setError('OpenAI API klíč není nastaven');
      return;
    }

    setIsTestingAssistant(true);
    setTestAssistantResult(null);
    setError('');

    try {
      const response = await axios.post('/api/openai-assistant-call', {
        assistant_id: selectedTestAssistant,
        prompt: testAssistantPrompt,
        api_key: openaiApiKey
      }, {
        timeout: 90000 // 90 sekund timeout
      });

      if (response.data.success) {
        setTestAssistantResult({
          success: true,
          response: response.data.data.response,
          assistant_id: selectedTestAssistant
        });
      }

    } catch (err) {
      console.error('Chyba při testování assistant:', err);
      setTestAssistantResult({
        success: false,
        error: err.response?.data?.error || 'Chyba při testování assistant'
      });
      setError(err.response?.data?.error || 'Chyba při testování OpenAI Assistant');
    } finally {
      setIsTestingAssistant(false);
    }
  };

  // Funkce pro generování obrázku pomocí DALL-E 3
  const handleGenerateImage = async () => {
    if (!dallePrompt.trim()) {
      setError('Zadejte prompt pro generování obrázku');
      return;
    }

    if (!openaiApiKey) {
      setError('OpenAI API klíč není nastaven');
      return;
    }

    setIsGeneratingImage(true);
    setError('');
    setGeneratedImage(null);

    try {
      const response = await axios.post('/api/generate-image', {
        prompt: dallePrompt,
        api_key: openaiApiKey,
        size: '1024x1024',
        quality: 'standard'
      }, {
        timeout: 120000 // 2 minuty timeout pro DALL-E
      });

      if (response.data.success) {
        setGeneratedImage(response.data.data);
        setResult({
          success: true,
          message: `Obrázek byl úspěšně vygenerován: ${response.data.data.filename}`
        });
        
        // Vymaže prompt po úspěšném generování
        setDallePrompt('');
      }

    } catch (err) {
      console.error('Chyba při generování obrázku:', err);
      setError(err.response?.data?.error || 'Chyba při generování obrázku pomocí DALL-E 3');
    } finally {
      setIsGeneratingImage(false);
    }
  };

  // Funkce pro YouTube projekty
  const openYouTubeModal = (project) => {
    setSelectedYouTubeProject(project);
    setShowYouTubeModal(true);
  };

  const closeYouTubeModal = () => {
    setSelectedYouTubeProject(null);
    setShowYouTubeModal(false);
    setShowUploadConfirm(false);
  };

  const handleUploadToYouTube = () => {
    setShowUploadConfirm(true);
  };

  const confirmUploadToYouTube = () => {
    // Zde bude logika pro upload na YouTube
    console.log('Nahrávám na YouTube:', selectedYouTubeProject);
    setResult({
      success: true,
      message: `Video "${selectedYouTubeProject.title}" se připravuje k nahrání na YouTube!`
    });
    closeYouTubeModal();
  };

  // Funkce pro odeslání promptu OpenAI asistentovi
  // eslint-disable-next-line no-unused-vars
  const handleSendToAssistant = async () => {
    if (!assistantPrompt.trim()) {
      setError('Zadejte prosím prompt pro asistenta');
      return;
    }

    if (!openaiApiKey) {
      setError('OpenAI API klíč není nastaven. Přejděte do API Management.');
      return;
    }

    const selectedAssistantData = availableAssistants.find(a => a.id === selectedAssistant);
    if (!selectedAssistantData) {
      setError('Vybraný asistent nebyl nalezen');
      return;
    }

    setIsAssistantLoading(true);
    setError('');
    
    try {
      let response;
      let assistantResponseText;

      // Kontrola, zda je to OpenAI Assistant nebo základní GPT
      if (selectedAssistantData.type === 'openai_assistant' && selectedAssistantData.id.startsWith('asst_')) {
        // Volání OpenAI Assistant API
        response = await axios.post('/api/openai-assistant-call', {
          assistant_id: selectedAssistantData.id,
          prompt: assistantPrompt,
          api_key: openaiApiKey
        }, {
          timeout: 90000 // 90 sekund timeout pro Assistant API
        });
        
        assistantResponseText = response.data.data?.response || 'Odpověď od OpenAI Assistant byla prázdná';
      } else {
        // Fallback na původní GPT endpoint pro základní asistenty
        response = await axios.post('/api/openai-assistant', {
          assistant_type: selectedAssistant,
          prompt: assistantPrompt
        }, {
          timeout: 30000
        });
        
        assistantResponseText = response.data.response || 'Odpověď od asistenta byla prázdná';
      }
      
      setAssistantResponse(assistantResponseText);
      
      // Uloží projekt do seznamu
      const newProject = {
        id: Date.now(),
        title: assistantPrompt.substring(0, 50) + (assistantPrompt.length > 50 ? '...' : ''),
        assistant_type: selectedAssistant,
        assistant_name: selectedAssistantData.name,
        original_prompt: assistantPrompt,
        response: assistantResponseText,
        character_count: assistantResponseText.length,
        created_at: new Date().toISOString(),
        preview: assistantResponseText.substring(0, 100) + (assistantResponseText.length > 100 ? '...' : ''),
        is_openai_assistant: selectedAssistantData.type === 'openai_assistant'
      };
      
      setGeneratedProjects(prev => [newProject, ...prev]);
      
      setResult({
        success: true,
        message: `Odpověď úspěšně získána od ${selectedAssistantData.type === 'openai_assistant' ? 'OpenAI Assistant' : 'AI asistenta'} a uložena do projektů!`
      });
      
      // Vymaže pole po úspěšném odeslání
      setAssistantPrompt('');
      
    } catch (err) {
      console.error('Chyba při komunikaci s asistentom:', err);
      setError(err.response?.data?.error || 'Chyba při komunikaci s asistentom');
      setAssistantResponse('');
    } finally {
      setIsAssistantLoading(false);
    }
  };

  // Automatické ukládání projektů do localStorage
  React.useEffect(() => {
    try {
      localStorage.setItem('generated_projects', JSON.stringify(generatedProjects));
    } catch (error) {
      console.error('Chyba při ukládání projektů do localStorage:', error);
    }
  }, [generatedProjects]);

  // Automatické ukládání asistentů do localStorage
  React.useEffect(() => {
    try {
      localStorage.setItem('available_assistants', JSON.stringify(availableAssistants));
    } catch (error) {
      console.error('Chyba při ukládání asistentů do localStorage:', error);
    }
  }, [availableAssistants]);

  // Načte existující soubory při startu aplikace a vymaže staré nahrávky
  React.useEffect(() => {
    // Vymaže staré nahrávky při refreshi
    setAudioFiles([]);
    setGeneratedVoiceFiles([]);
    setResult(null);
    setError('');
    // NERESETUJE selectedBackground - zůstane vybrané pozadí
    
    loadExistingFiles();
    // loadGeneratedProjects(); // Už nemusíme volat, projekty se načítají z localStorage
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
  // Callback pro Video Production Pipeline - automaticky pošle JSON do VoiceGenerator
  const handleVideoProjectGenerated = (finalProject) => {
    console.log('🎬 Video Production Pipeline dokončen:', finalProject);
    
    // Převede video projekt na ElevenLabs JSON formát
    const elevenlabsJson = {};
    
    if (finalProject?.segments) {
      console.log('📊 Zpracovávám', finalProject.segments.length, 'segmentů');
      
      finalProject.segments.forEach((segment, index) => {
        console.log(`📝 Segment ${index + 1}:`, segment.id, segment.content);
        
        // Váš Tesla vs Socrates formát - Tesla_01, Socrates_01 přímo na root úrovni
        const segmentContent = segment.content || {};
        
        console.log(`🔍 Obsah segmentu ${segment.id}:`, segmentContent);
        console.log(`🔍 Počet bloků v segmentu:`, Object.keys(segmentContent).length);
        
        // Zkopíruje všechny voice blocks z segmentu
        Object.entries(segmentContent).forEach(([blockName, blockData]) => {
          console.log(`🎤 Blok ${blockName}:`, blockData);
          
          if (blockData && blockData.text && blockData.voice_id) {
            elevenlabsJson[blockName] = {
              text: blockData.text,
              voice_id: blockData.voice_id
            };
            console.log(`✅ Přidán blok ${blockName}`);
          } else {
            console.warn(`⚠️ Blok ${blockName} nemá potřebná data:`, blockData);
          }
        });
      });
    }
    
    console.log('🎯 Finální ElevenLabs JSON:', elevenlabsJson);
    console.log('🎯 Počet bloků celkem:', Object.keys(elevenlabsJson).length);
    
    if (Object.keys(elevenlabsJson).length > 0) {
      setAutoJsonFromPipeline(elevenlabsJson);
      console.log('✅ JSON připraven pro VoiceGenerator:', Object.keys(elevenlabsJson).length, 'bloků');
    } else {
      console.warn('⚠️ Nepodařilo se vytvořit JSON pro VoiceGenerator - možná chybí voice_blocks');
      console.warn('⚠️ FinalProject struktura:', JSON.stringify(finalProject, null, 2));
    }
  };

  const handleVoicesGenerated = (generatedFiles) => {
    console.log('Vygenerované hlasy:', generatedFiles);
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
      message: `Vygenerováno ${generatedFiles.length} hlasových souborů! Automaticky přidány ke zpracování.`,
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
    console.log(`Nastavuji hlasitost ${voiceId}: ${numericVolume}dB`);
    
    const newVolumes = {
      ...voiceVolumes,
      [voiceId]: numericVolume
    };
    
    // Uloží do localStorage pro budoucí použití
    try {
      localStorage.setItem('voice_volumes', JSON.stringify(newVolumes));
      console.log('Uloženo nastavení hlasitosti do localStorage:', newVolumes);
    } catch (error) {
              console.error('Chyba při ukládání nastavení hlasitosti:', error);
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
      console.log('Vymazána všechna uložená nastavení hlasitosti');
    } catch (error) {
      console.error('Chyba při mazání nastavení hlasitosti:', error);
    }
  };

  // Funkce pro zpracování vybraného pozadí
  const handleBackgroundSelected = (background) => {
    console.log('App.js přijal pozadí:', background);
    setSelectedBackground(background);
    console.log('Vybrané pozadí nastaveno:', background);
  };

  // Funkce pro zpracování vybraného video pozadí
  const handleVideoBackgroundSelected = (videoBackground) => {
    console.log('App.js přijal video pozadí:', videoBackground);
    setSelectedVideoBackground(videoBackground);
    console.log('Vybrané video pozadí nastaveno:', videoBackground);
  };

  // Funkce pro zpracování a spojení audio souborů
  const handleCombineAudio = async () => {
    console.log('handleCombineAudio ZAČÍNÁ');
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

            console.log('Validace prošla, spouštím zpracování...');
    setIsProcessing(true);
    setError('');
    setResult(null);

    try {
      // Připraví FormData pro odeslání
      const formData = new FormData();
      
      // Přidá audio soubory
      console.log('Přidávám audio soubory do FormData:');
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
      console.log('Posílám data hlasitostí na backend:', volumeData);
      if (Object.keys(volumeData).length > 0) {
        formData.append('file_volumes', JSON.stringify(volumeData));
      }

      // Přidá vybrané pozadí (priorita: video > obrázek)
      if (useVideoBackground && selectedVideoBackground) {
        console.log('Posílám video pozadí na backend:', selectedVideoBackground.filename);
        formData.append('video_background_filename', selectedVideoBackground.filename);
      } else if (selectedBackground) {
                  console.log('Posílám obrázek pozadí na backend:', selectedBackground.filename);
        formData.append('background_filename', selectedBackground.filename);
      } else {
                  console.log('Žádné pozadí není vybráno!');
      }

      // Odešle požadavek na backend
      console.log('ODESÍLÁM REQUEST na /api/upload...');
      console.log('FormData připravená, odesílám...');
      
      const response = await axios.post('/api/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: 1200000 // 20 minut timeout pro dlouhé zpracování (vhodné pro 100+ souborů)
      });

              console.log('RESPONSE PŘIJATA:', response.data);
      setResult(response.data);
    } catch (err) {
              console.error('CHYBA při zpracování:', err);
        console.error('Error response:', err.response);
        console.error('Error message:', err.message);
      setError(err.response?.data?.error || err.message || 'Došlo k chybě při zpracování!');
    } finally {
              console.log('Zpracování dokončeno, isProcessing = false');
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

  // Funkce pro obnovení seznamu skrytých asistentů (volá AssistantManager)
  const refreshHiddenAssistants = () => {
    loadHiddenAssistants();
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto px-4 py-8">
        {/* Clean Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-white rounded-lg shadow-sm mb-4">
            <span className="text-2xl font-bold text-primary-600">AI</span>
          </div>
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            Petr's genius video machine
          </h1>
          <p className="text-gray-600 max-w-xl mx-auto">
            Moderní webová aplikace pro generování a kombinování audio souborů
          </p>
        </div>

        {/* Video Production Pipeline - HLAVNÍ KOMPONENTA */}
        <div className="mb-8">
          <VideoProductionPipeline 
            openaiApiKey={openaiApiKey}
            availableAssistants={getVisibleAssistants()}
            onOpenApiManagement={openApiKeyModal}
            onOpenAddAssistant={openAddAssistantModal}
            onVideoProjectGenerated={handleVideoProjectGenerated}
          />
        </div>

        {/* Vygenerované projekty */}
        {generatedProjects.length > 0 && (
          <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-gray-900 mb-3 flex items-center">
                <span className="w-6 h-6 bg-green-100 rounded-md flex items-center justify-center mr-3">
                  <span className="text-green-600 text-xs font-bold">DOC</span>
                </span>
                Vygenerované projekty ({generatedProjects.length})
              </h3>
              <p className="text-sm text-gray-600 mb-4">
                Klikněte na projekt pro zobrazení úplného obsahu
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {generatedProjects.map((project) => (
                <div 
                  key={project.id} 
                  className="p-4 border border-gray-200 rounded-lg hover:border-blue-300 hover:shadow-md transition-all"
                >
                  <div className="mb-3">
                    <h4 className="text-sm font-semibold text-gray-900 mb-1 truncate">
                      {project.title}
                    </h4>
                    <div className="flex items-center space-x-2 text-xs text-gray-500">
                      <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded-md">
                        {getVisibleAssistants().find(a => a.id === project.assistant_type)?.name || 'Asistent'}
                      </span>
                      <span>{project.character_count.toLocaleString()} znaků</span>
                    </div>
                  </div>
                  
                  <p className="text-xs text-gray-600 mb-3 line-clamp-3">
                    {project.preview}
                  </p>
                  
                  <div className="text-xs text-gray-400 mb-3">
                    {new Date(project.created_at).toLocaleDateString('cs-CZ', {
                      day: '2-digit',
                      month: '2-digit', 
                      year: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </div>

                  {/* Buttony pro akce */}
                  <div className="flex space-x-2">
                    <button
                      onClick={() => openProjectDetail(project)}
                      className="flex-1 px-3 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 transition-colors"
                    >
                      Detail
                    </button>
                    <button
                      onClick={() => handleProjectConfirm(project)}
                      className="flex-1 px-3 py-2 bg-green-600 text-white text-sm font-medium rounded-md hover:bg-green-700 transition-colors"
                    >
                      Potvrdit
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Modal pro detail projektu */}
        {showProjectDetail && selectedProject && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-lg max-w-4xl w-full max-h-[90vh] overflow-hidden">
              {/* Header modalu */}
              <div className="p-6 border-b border-gray-200">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-semibold text-gray-900 mb-2">
                      {selectedProject.title}
                    </h2>
                    <div className="flex items-center space-x-3 text-sm text-gray-600">
                      <span className="px-3 py-1 bg-blue-100 text-blue-700 rounded-md">
                        {getVisibleAssistants().find(a => a.id === selectedProject.assistant_type)?.name || 'Asistent'}
                      </span>
                      <span>{selectedProject.character_count.toLocaleString()} znaků</span>
                      <span>
                        {new Date(selectedProject.created_at).toLocaleDateString('cs-CZ', {
                          day: '2-digit',
                          month: '2-digit',
                          year: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit'
                        })}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={closeProjectDetail}
                    className="text-gray-400 hover:text-gray-600 text-2xl font-bold"
                  >
                    ×
                  </button>
                </div>
              </div>

              {/* Obsah modalu */}
              <div className="p-6 overflow-y-auto max-h-[70vh]">
                <div className="mb-4">
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">Původní prompt:</h3>
                  <div className="p-3 bg-gray-50 rounded-lg text-sm text-gray-800">
                    {selectedProject.original_prompt}
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">Vygenerovaný obsah:</h3>
                  <div className="p-4 bg-blue-50 rounded-lg text-sm text-gray-800 whitespace-pre-wrap">
                    {selectedProject.response}
                  </div>
                </div>
              </div>

              {/* Footer modalu */}
              <div className="p-6 border-t border-gray-200 bg-gray-50">
                <div className="flex justify-end space-x-3">
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(selectedProject.response);
                      setResult({ success: true, message: 'Obsah zkopírován do schránky!' });
                    }}
                    className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                  >
                    Kopírovat obsah
                  </button>
                  <button
                    onClick={closeProjectDetail}
                    className="px-4 py-2 bg-gray-300 text-gray-700 rounded-md hover:bg-gray-400 transition-colors"
                  >
                    Zavřít
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Modal pro přidání asistenta */}
        {showAddAssistantModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-lg max-w-md w-full">
              {/* Header modalu */}
              <div className="p-6 border-b border-gray-200">
                <div className="flex items-center justify-between">
                  <h2 className="text-xl font-semibold text-gray-900">
                    Přidat nového asistenta
                  </h2>
                  <button
                    onClick={closeAddAssistantModal}
                    className="text-gray-400 hover:text-gray-600 text-2xl font-bold"
                  >
                    ×
                  </button>
                </div>
              </div>

              {/* Obsah modalu */}
              <div className="p-6">
                <div className="mb-4">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Název asistenta *
                  </label>
                  <input
                    type="text"
                    value={newAssistantName}
                    onChange={(e) => setNewAssistantName(e.target.value)}
                    placeholder="Např. Marketingový asistent"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                </div>

                <div className="mb-4">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    OpenAI Assistant ID *
                  </label>
                  <input
                    type="text"
                    value={newAssistantId}
                    onChange={(e) => setNewAssistantId(e.target.value)}
                    placeholder="asst_abc123xyz..."
                    className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    OpenAI Assistant ID začínající "asst_" - získejte z <a href="https://platform.openai.com/assistants" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">OpenAI Platform</a>
                  </p>
                </div>

                <div className="mb-4">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Kategorie obsahu *
                  </label>
                  <select
                    value={newAssistantCategory}
                    onChange={(e) => setNewAssistantCategory(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  >
                    <option value="podcast">🎙️ Podcast (2 hlasy - Tesla vs Socrates dialog)</option>
                    <option value="document">📄 Dokument (1 hlas - kontinuální narrace)</option>
                  </select>
                  <p className="text-xs text-gray-500 mt-1">
                    Určuje, jaký typ obsahu bude asistent generovat
                  </p>
                </div>

                <div className="mb-4">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Popis asistenta
                  </label>
                  <textarea
                    value={newAssistantDescription}
                    onChange={(e) => setNewAssistantDescription(e.target.value)}
                    placeholder="Krátký popis funkcí asistenta..."
                    rows={3}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                </div>
              </div>

              {/* Footer modalu */}
              <div className="p-6 border-t border-gray-200 bg-gray-50">
                <div className="flex justify-end space-x-3">
                  <button
                    onClick={closeAddAssistantModal}
                    className="px-4 py-2 bg-gray-300 text-gray-700 rounded-md hover:bg-gray-400 transition-colors"
                  >
                    Zrušit
                  </button>
                  <button
                    onClick={handleAddAssistant}
                    className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors"
                  >
                    Přidat asistenta
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Modal pro API klíče */}
        {showApiKeyModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
              {/* Header modalu */}
              <div className="p-6 border-b border-gray-200">
                <div className="flex items-center justify-between">
                  <h2 className="text-xl font-semibold text-gray-900">
                    🔧 API Management
                  </h2>
                  <button
                    onClick={closeApiKeyModal}
                    className="text-gray-400 hover:text-gray-600 text-2xl font-bold"
                  >
                    ×
                  </button>
                </div>
                <p className="text-sm text-gray-600 mt-2">
                  Nakonfigurujte API klíče pro všechny služby
                </p>
              </div>

              {/* Obsah modalu */}
              <div className="p-6 space-y-6">
                {/* OpenAI API */}
                <div className="p-4 border border-gray-200 rounded-lg">
                  <div className="flex items-center mb-3">
                    <div className="w-8 h-8 bg-green-100 rounded-lg flex items-center justify-center mr-3">
                      <span className="text-green-600 text-sm font-bold">AI</span>
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-gray-900">OpenAI (GPT-4 + DALL-E 3)</h3>
                      <p className="text-xs text-gray-500">Pro AI asistenta a generování obrázků</p>
                    </div>
                  </div>
                  <input
                    type="password"
                    value={openaiApiKey}
                    onChange={(e) => setOpenaiApiKey(e.target.value)}
                    placeholder="sk-..."
                    className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-green-500"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    Získejte na: <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">OpenAI Platform</a>
                  </p>
                </div>

                {/* ElevenLabs API */}
                <div className="p-4 border border-gray-200 rounded-lg">
                  <div className="flex items-center mb-3">
                    <div className="w-8 h-8 bg-purple-100 rounded-lg flex items-center justify-center mr-3">
                      <span className="text-purple-600 text-sm font-bold">🎤</span>
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-gray-900">ElevenLabs</h3>
                      <p className="text-xs text-gray-500">Pro generování hlasů</p>
                    </div>
                  </div>
                  <input
                    type="password"
                    value={elevenlabsApiKey}
                    onChange={(e) => setElevenlabsApiKey(e.target.value)}
                    placeholder="sk_..."
                    className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    Získejte na: <a href="https://elevenlabs.io/app/speech-synthesis/text-to-speech" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">ElevenLabs</a>
                  </p>
                </div>

                {/* YouTube API */}
                <div className="p-4 border border-gray-200 rounded-lg">
                  <div className="flex items-center mb-3">
                    <div className="w-8 h-8 bg-red-100 rounded-lg flex items-center justify-center mr-3">
                      <span className="text-red-600 text-sm font-bold">📺</span>
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-gray-900">YouTube Data API</h3>
                      <p className="text-xs text-gray-500">Pro automatické nahrávání videí</p>
                    </div>
                  </div>
                  <input
                    type="password"
                    value={youtubeApiKey}
                    onChange={(e) => setYoutubeApiKey(e.target.value)}
                    placeholder="AIza..."
                    className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-red-500"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    Získejte na: <a href="https://console.developers.google.com/" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">Google Console</a>
                  </p>
                </div>

                {/* Security Notice */}
                <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                  <h4 className="text-sm font-semibold text-blue-800 mb-2">🔒 Bezpečnost</h4>
                  <p className="text-sm text-blue-700">
                    Všechny API klíče se ukládají pouze lokálně ve vašem prohlížeči (localStorage) a jsou používány pouze pro přímou komunikaci s příslušnými službami.
                  </p>
                </div>

                {/* Test API tlačítko */}
                <div className="flex justify-center">
                  <button
                    onClick={handleTestApiConnections}
                    disabled={isTestingApi || (!openaiApiKey && !elevenlabsApiKey && !youtubeApiKey)}
                    className={`px-6 py-2 rounded-md font-medium text-white transition-colors ${
                      isTestingApi || (!openaiApiKey && !elevenlabsApiKey && !youtubeApiKey)
                        ? 'bg-gray-400 cursor-not-allowed'
                        : 'bg-purple-600 hover:bg-purple-700'
                    }`}
                  >
                    {isTestingApi ? (
                      <span className="flex items-center">
                        <span className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full mr-2"></span>
                        Testuji připojení...
                      </span>
                    ) : (
                      '🧪 Otestovat API připojení'
                    )}
                  </button>
                </div>

                {/* API Test Results */}
                {apiTestResults && (
                  <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
                    <h4 className="text-sm font-semibold text-gray-800 mb-3">📊 Výsledky testů API</h4>
                    <div className="space-y-3">
                      {Object.entries(apiTestResults).map(([api, result]) => (
                        <div key={api} className={`p-3 rounded-lg border ${
                          result.status === 'success' ? 'bg-green-50 border-green-200' : 
                          result.status === 'error' ? 'bg-red-50 border-red-200' : 
                          'bg-yellow-50 border-yellow-200'
                        }`}>
                          <div className="flex items-center">
                            <div className={`w-4 h-4 rounded-full mr-3 ${
                              result.status === 'success' ? 'bg-green-500' : 
                              result.status === 'error' ? 'bg-red-500' : 
                              'bg-yellow-500'
                            }`}></div>
                            <div>
                              <p className={`text-sm font-medium ${
                                result.status === 'success' ? 'text-green-800' : 
                                result.status === 'error' ? 'text-red-800' : 
                                'text-yellow-800'
                              }`}>
                                {api === 'openai' ? 'OpenAI' : api === 'elevenlabs' ? 'ElevenLabs' : 'YouTube'}
                              </p>
                              <p className={`text-xs ${
                                result.status === 'success' ? 'text-green-700' : 
                                result.status === 'error' ? 'text-red-700' : 
                                'text-yellow-700'
                              }`}>
                                {result.message}
                              </p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* API Status */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div className={`p-3 rounded-lg border ${openaiApiKey ? 'bg-green-50 border-green-200' : 'bg-gray-50 border-gray-200'}`}>
                    <div className="text-center">
                      <div className={`w-3 h-3 rounded-full mx-auto mb-1 ${openaiApiKey ? 'bg-green-500' : 'bg-gray-300'}`}></div>
                      <p className={`text-xs font-medium ${openaiApiKey ? 'text-green-700' : 'text-gray-500'}`}>
                        OpenAI {openaiApiKey ? 'Konfiguráno' : 'Nekonfiguráno'}
                      </p>
                    </div>
                  </div>
                  <div className={`p-3 rounded-lg border ${elevenlabsApiKey ? 'bg-green-50 border-green-200' : 'bg-gray-50 border-gray-200'}`}>
                    <div className="text-center">
                      <div className={`w-3 h-3 rounded-full mx-auto mb-1 ${elevenlabsApiKey ? 'bg-green-500' : 'bg-gray-300'}`}></div>
                      <p className={`text-xs font-medium ${elevenlabsApiKey ? 'text-green-700' : 'text-gray-500'}`}>
                        ElevenLabs {elevenlabsApiKey ? 'Konfiguráno' : 'Nekonfiguráno'}
                      </p>
                    </div>
                  </div>
                  <div className={`p-3 rounded-lg border ${youtubeApiKey ? 'bg-green-50 border-green-200' : 'bg-gray-50 border-gray-200'}`}>
                    <div className="text-center">
                      <div className={`w-3 h-3 rounded-full mx-auto mb-1 ${youtubeApiKey ? 'bg-green-500' : 'bg-gray-300'}`}></div>
                      <p className={`text-xs font-medium ${youtubeApiKey ? 'text-green-700' : 'text-gray-500'}`}>
                        YouTube {youtubeApiKey ? 'Konfiguráno' : 'Nekonfiguráno'}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Test OpenAI Assistants sekce */}
                {openaiApiKey && getVisibleAssistants().some(a => a.type === 'openai_assistant') && (
                  <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                    <h4 className="text-sm font-semibold text-green-800 mb-3">🤖 Test OpenAI Assistants</h4>
                    
                    <div className="mb-3">
                      <label className="block text-sm font-medium text-green-700 mb-1">
                        Vyberte Assistant:
                      </label>
                      <select
                        value={selectedTestAssistant || ''}
                        onChange={(e) => setSelectedTestAssistant(e.target.value)}
                        className="w-full px-3 py-2 border border-green-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                      >
                        <option value="">-- Vyberte OpenAI Assistant --</option>
                        {getVisibleAssistants()
                          .filter(a => a.type === 'openai_assistant')
                          .map(assistant => (
                            <option key={assistant.id} value={assistant.id}>
                              {assistant.name} ({assistant.id})
                            </option>
                          ))
                        }
                      </select>
                    </div>

                    <div className="mb-3">
                      <label className="block text-sm font-medium text-green-700 mb-1">
                        Test prompt:
                      </label>
                      <input
                        type="text"
                        value={testAssistantPrompt}
                        onChange={(e) => setTestAssistantPrompt(e.target.value)}
                        placeholder="Ahoj, kdo jsi?"
                        className="w-full px-3 py-2 border border-green-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                      />
                    </div>

                    <div className="flex justify-between items-center">
                      <button
                        onClick={handleTestAssistant}
                        disabled={isTestingAssistant || !selectedTestAssistant || !testAssistantPrompt.trim()}
                        className={`px-4 py-2 rounded-md text-sm font-medium text-white transition-colors ${
                          isTestingAssistant || !selectedTestAssistant || !testAssistantPrompt.trim()
                            ? 'bg-gray-400 cursor-not-allowed'
                            : 'bg-green-600 hover:bg-green-700'
                        }`}
                      >
                        {isTestingAssistant ? 'Testuji Assistant...' : 'Test Assistant'}
                      </button>
                      
                      {testAssistantResult && (
                        <span className={`text-sm font-medium ${
                          testAssistantResult.success ? 'text-green-600' : 'text-red-600'
                        }`}>
                          {testAssistantResult.success ? '✅ Úspěch' : '❌ Chyba'}
                        </span>
                      )}
                    </div>

                    {testAssistantResult && testAssistantResult.response && (
                      <div className="mt-3 p-3 bg-white border border-green-200 rounded-md">
                        <h5 className="text-xs font-medium text-green-700 mb-1">Odpověď:</h5>
                        <p className="text-sm text-gray-700">{testAssistantResult.response}</p>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Footer modalu */}
              <div className="p-6 border-t border-gray-200 bg-gray-50">
                <div className="flex justify-end space-x-3">
                  <button
                    onClick={closeApiKeyModal}
                    className="px-4 py-2 bg-gray-300 text-gray-700 rounded-md hover:bg-gray-400 transition-colors"
                  >
                    Zrušit
                  </button>
                  <button
                    onClick={handleSaveApiKey}
                    className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                  >
                    💾 Uložit všechny klíče
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}



        {/* Voice Generator Card */}
        <div className="bg-white rounded-lg shadow-sm mb-6">
          <VoiceGenerator 
            onVoicesGenerated={handleVoicesGenerated}
            autoJsonFromPipeline={autoJsonFromPipeline}
          />
        </div>

        {/* DALL-E Test Section */}
        <div className="bg-white rounded-lg shadow-sm mb-6 p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-lg font-semibold text-gray-900 flex items-center">
                <span className="w-6 h-6 bg-purple-100 rounded-md flex items-center justify-center mr-3">
                  <span className="text-purple-600 text-xs font-bold">🎨</span>
                </span>
                DALL-E 3 Image Generator (Test)
              </h3>
              <p className="text-sm text-gray-600">Rychlý test generování obrázků pomocí DALL-E 3</p>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Prompt pro obrázek
              </label>
              <input
                type="text"
                value={dallePrompt}
                onChange={(e) => setDallePrompt(e.target.value)}
                placeholder="A majestic castle on a hill during sunset..."
                className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
              />
            </div>

            <div className="flex items-center space-x-4">
              <button
                onClick={handleGenerateImage}
                disabled={isGeneratingImage || !dallePrompt.trim() || !openaiApiKey}
                className={`px-6 py-2 rounded-md font-medium text-white transition-colors ${
                  isGeneratingImage || !dallePrompt.trim() || !openaiApiKey
                    ? 'bg-gray-400 cursor-not-allowed'
                    : 'bg-purple-600 hover:bg-purple-700'
                }`}
              >
                {isGeneratingImage ? (
                  <span className="flex items-center">
                    <span className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full mr-2"></span>
                    Generuji obrázek...
                  </span>
                ) : (
                  '🎨 Vygenerovat obrázek'
                )}
              </button>

              {!openaiApiKey && (
                <p className="text-sm text-red-600">
                  ⚠️ OpenAI API klíč není nastaven
                </p>
              )}
            </div>

            {/* Generated Image Preview */}
            {generatedImage && (
              <div className="mt-6 p-4 bg-purple-50 border border-purple-200 rounded-lg">
                <h4 className="text-sm font-semibold text-purple-900 mb-3">✅ Vygenerovaný obrázek</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <img 
                      src={`/api/download/${generatedImage.filename}`}
                      alt="Generated by DALL-E 3"
                      className="w-full h-auto rounded-lg shadow-sm border"
                    />
                  </div>
                  <div className="space-y-3">
                    <div>
                      <p className="text-xs font-medium text-purple-700 mb-1">Původní prompt:</p>
                      <p className="text-xs text-purple-800 bg-white p-2 rounded border">
                        {generatedImage.original_prompt}
                      </p>
                    </div>
                    {generatedImage.revised_prompt && (
                      <div>
                        <p className="text-xs font-medium text-purple-700 mb-1">Upravený prompt (DALL-E):</p>
                        <p className="text-xs text-purple-800 bg-white p-2 rounded border">
                          {generatedImage.revised_prompt}
                        </p>
                      </div>
                    )}
                    <div className="flex items-center space-x-2 text-xs text-purple-600">
                      <span>📏 {generatedImage.size}</span>
                      <span>✨ {generatedImage.quality}</span>
                      <span>📁 {generatedImage.filename}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Main Processing Card */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
          {/* Generated Voice Files */}
          {generatedVoiceFiles.length > 0 && (
            <div className="mb-6 p-5 bg-gray-50 rounded-lg border">
              <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <span className="w-6 h-6 bg-accent-100 rounded-md flex items-center justify-center mr-3">
                  <span className="text-accent-600 text-xs font-bold">TTS</span>
                </span>
                Generated Voice Files ({generatedVoiceFiles.length})
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {generatedVoiceFiles.map((file, index) => (
                  <div key={index} className="flex items-center p-3 bg-white rounded-lg border hover:border-gray-300 transition-colors">
                    <div className="flex-shrink-0 mr-3">
                      <div className="w-8 h-8 bg-success-100 rounded-lg flex items-center justify-center">
                        <span className="text-success-600 text-sm font-bold">
                          OK
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
              <div className="mt-4 p-3 bg-primary-50 border border-primary-200 rounded-lg">
                <p className="text-sm text-primary-800 flex items-center">
                  <span className="mr-2 bg-primary-200 px-2 py-1 rounded text-xs font-bold">AUTO</span>
                  <span><strong>Soubory automaticky přidány ke zpracování!</strong> Nyní můžete kliknout na "Spojit & Exportovat".</span>
                </p>
              </div>
            </div>
          )}

          {/* Audio Files Upload Section */}
          <div className="mb-6">
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-gray-900 mb-3 flex items-center">
                <span className="w-6 h-6 bg-primary-100 rounded-md flex items-center justify-center mr-3">
                  <span className="text-primary-600 text-xs font-bold">MP3</span>
                </span>
                Audio soubory
              </h3>
              <FileUploader
                onFilesSelected={handleAudioFilesSelected}
                acceptedFiles={['mp3', 'wav', 'audio']}
                multiple={true}
                label="Hlavní audio soubory (Tesla_1.mp3, Socrates_1.mp3, atd.)"
                placeholder="Nahrajte MP3 soubory které chcete spojit"
              />
            </div>
            
            {/* Seznam nahraných souborů seskupených podle hlasu */}
            {audioFiles.length > 0 && (
              <div className="mt-4 space-y-4">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-medium text-gray-700">
                    Nahrané soubory seskupené podle hlasu ({audioFiles.length})
                  </h4>
                  <button
                    onClick={() => setAudioFiles(sortFilesForDialog(audioFiles))}
                    className="px-3 py-1 text-xs bg-primary-100 text-primary-700 rounded-md hover:bg-primary-200 transition-colors"
                  >
                    Seřadit pro dialog
                  </button>
                </div>
                
                {Object.entries(groupFilesByVoice()).map(([voiceId, voiceFiles]) => {
                  const currentVolume = getVoiceVolume(voiceId);
                  const voiceName = getVoiceNameFromId(voiceId);
                  
                  return (
                    <div key={voiceId} className="bg-white p-4 rounded-lg border shadow-sm">
                      {/* Hlavička hlasu */}
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex-1">
                          <h5 className="text-sm font-semibold text-gray-900">{voiceName}</h5>
                          <p className="text-xs text-gray-500">{voiceFiles.length} souborů</p>
                        </div>
                        <div className="text-right flex items-center space-x-2">
                          <span className={`text-sm font-medium ${
                            currentVolume > 0 ? 'text-success-600' : 
                            currentVolume < 0 ? 'text-accent-600' : 
                            'text-gray-600'
                          }`}>
                            {currentVolume > 0 ? '+' : ''}{currentVolume}dB
                          </span>
                          {voiceVolumes[voiceId] !== undefined && (
                            <span className="text-xs bg-success-100 text-success-700 px-2 py-1 rounded-md" title="Uložené nastavení">
                              SAVED
                            </span>
                          )}
                        </div>
                      </div>
                      
                      {/* Ovládání hlasitosti pro celý hlas */}
                      <div className="flex items-center space-x-3 mb-3">
                        <label className="text-xs text-gray-600 font-medium">
                          Hlasitost celého hlasu:
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
                      <div className="flex space-x-2 mb-3">
                        <button
                          onClick={() => setVoiceVolume(voiceId, -6)}
                          className="px-3 py-1 text-xs bg-accent-100 text-accent-700 rounded-md hover:bg-accent-200 transition-colors"
                        >
                          Tišší (-6dB)
                        </button>
                        <button
                          onClick={() => setVoiceVolume(voiceId, 0)}
                          className="px-3 py-1 text-xs bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 transition-colors"
                        >
                          Reset (0dB)
                        </button>
                        <button
                          onClick={() => setVoiceVolume(voiceId, 6)}
                          className="px-3 py-1 text-xs bg-success-100 text-success-700 rounded-md hover:bg-success-200 transition-colors"
                        >
                          Hlasitější (+6dB)
                        </button>
                      </div>
                      
                      {/* Seznam souborů v této skupině */}
                      <div className="border-t pt-3">
                        <p className="text-xs text-gray-600 mb-2">Soubory v této skupině:</p>
                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                          {voiceFiles.map((item) => (
                            <div key={item.index} className="flex items-center justify-between bg-gray-50 p-2 rounded-md border">
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
                
                <div className="p-4 bg-primary-50 border border-primary-200 rounded-lg">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <p className="text-sm text-primary-800 mb-2">
                        <strong>Skupinové nastavení hlasitosti:</strong> Změna hlasitosti se aplikuje na všechny soubory stejného hlasu najednou.
                      </p>
                      <p className="text-sm text-primary-700 mb-2">
                        <strong>Pořadí pro dialog:</strong> Soubory se automaticky řadí Tesla_01 → Socrates_01 → Tesla_02...
                      </p>
                      <p className="text-sm text-success-700">
                        <strong>Paměť nastavení:</strong> Hlasitost se automaticky ukládá a pamatuje.
                      </p>
                    </div>
                    <button
                      onClick={resetAllVoiceVolumes}
                      className="ml-3 px-3 py-2 text-xs bg-red-100 text-red-700 rounded-md hover:bg-red-200 transition-colors"
                      title="Vymaže všechna uložená nastavení hlasitosti"
                    >
                      Reset paměti
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Existující soubory ve složce */}
            {existingFiles.length > 0 && (
              <div className="mt-4 space-y-3">
                <h4 className="text-sm font-medium text-gray-700">
                  Dostupné soubory na serveru ({existingFiles.length})
                </h4>
                <div className="max-h-32 overflow-y-auto space-y-2">
                  {existingFiles.map((file, index) => {
                    const isAlreadyAdded = audioFiles.some(af => af.name === file.filename);
                    return (
                      <div key={index} className="flex items-center justify-between bg-gray-50 p-3 rounded-md border">
                        <div className="flex-1">
                          <span className="text-sm text-gray-700">{file.filename}</span>
                          <span className="text-xs text-gray-500 ml-2">
                            ({formatFileSize(file.size)})
                          </span>
                          {isAlreadyAdded && (
                            <span className="text-xs text-success-600 ml-2 font-medium">
                              Přidáno
                            </span>
                          )}
                        </div>
                        <button
                          onClick={() => addExistingFile(file)}
                          disabled={isAlreadyAdded}
                          className={`text-sm px-3 py-1 rounded-md transition-colors ${
                            isAlreadyAdded 
                              ? 'text-gray-400 cursor-not-allowed' 
                              : 'text-primary-600 bg-primary-100 hover:bg-primary-200'
                          }`}
                        >
                          {isAlreadyAdded ? 'OK' : '+ Přidat'}
                        </button>
                      </div>
                    );
                  })}
                </div>
                <p className="text-xs text-gray-500">
                  Klikněte "+ Přidat" pro použití existujících souborů ve spojování
                </p>
              </div>
            )}
          </div>

          {/* Intro a Outro soubory */}
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-3 flex items-center">
              <span className="w-6 h-6 bg-accent-100 rounded-md flex items-center justify-center mr-3">
                <span className="text-accent-600 text-xs font-bold">I/O</span>
              </span>
              Intro a Outro soubory
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-gray-50 p-4 rounded-lg border">
                <FileUploader
                  onFilesSelected={handleIntroFileSelected}
                  acceptedFiles={['mp3', 'wav', 'audio']}
                  multiple={false}
                  label="Intro soubor (volitelné)"
                  placeholder="Přetáhněte intro MP3"
                />
                {introFile && (
                  <p className="text-xs text-gray-600 mt-2">
                    {introFile.name} ({formatFileSize(introFile.size)})
                  </p>
                )}
              </div>
              
              <div className="bg-gray-50 p-4 rounded-lg border">
                <FileUploader
                  onFilesSelected={handleOutroFileSelected}
                  acceptedFiles={['mp3', 'wav', 'audio']}
                  multiple={false}
                  label="Outro soubor (volitelné)"
                  placeholder="Přetáhněte outro MP3"
                />
                {outroFile && (
                  <p className="text-xs text-gray-600 mt-2">
                    {outroFile.name} ({formatFileSize(outroFile.size)})
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Nastavení pauzy */}
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-3 flex items-center">
              <span className="w-6 h-6 bg-primary-100 rounded-md flex items-center justify-center mr-3">
                <span className="text-primary-600 text-xs font-bold">PAUSE</span>
              </span>
              Nastavení pauzy
            </h3>
            <div className="bg-gray-50 p-4 rounded-lg border">
              <label className="block text-sm font-medium text-gray-700 mb-3">
                Délka pauzy mezi bloky: {pauseDuration}s
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
              <div className="flex justify-between text-xs text-gray-500 mt-2">
                <span>0.5s</span>
                <span>2.0s</span>
              </div>
            </div>
          </div>

          {/* Generování titulků */}
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-3 flex items-center">
              <span className="w-6 h-6 bg-accent-100 rounded-md flex items-center justify-center mr-3">
                <span className="text-accent-600 text-xs font-bold">SRT</span>
              </span>
              Titulky
            </h3>
            <div className="bg-gray-50 p-4 rounded-lg border">
              <div className="flex items-center mb-4">
                <input
                  type="checkbox"
                  id="generateSubtitles"
                  checked={generateSubtitles}
                  onChange={(e) => setGenerateSubtitles(e.target.checked)}
                  className={`h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded ${
                    generatedVoiceFiles.length > 0 && generateSubtitles ? 'ring-2 ring-success-400' : ''
                  }`}
                />
                <label htmlFor="generateSubtitles" className="ml-2 text-sm font-medium text-gray-700 flex items-center">
                  Generovat titulky (.srt)
                  {generatedVoiceFiles.length > 0 && generateSubtitles && (
                    <span className="ml-2 px-2 py-1 text-xs bg-success-100 text-success-700 rounded-md">
                      Auto
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
                    className="w-full h-24 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-primary-500 focus:border-primary-500 text-sm"
                  />
                  <p className="text-xs text-gray-500 mt-2">
                    {generatedVoiceFiles.length > 0 ? (
                      <>
                        <strong>Automaticky předvyplněno</strong> texty z vygenerovaných hlasů - můžete upravit podle potřeby
                      </>
                    ) : (
                      'Zadejte JSON s mapováním názvů souborů na text pro titulky'
                    )}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Pozadí pro video */}
          {generateVideo && (
            <div className="mb-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-3 flex items-center">
                <span className="w-6 h-6 bg-accent-100 rounded-md flex items-center justify-center mr-3">
                  <span className="text-accent-600 text-xs font-bold">BG</span>
                </span>
                Pozadí pro video
              </h3>
              
              <div className="bg-gray-50 p-4 rounded-lg border mb-4">
                <h4 className="text-sm font-medium text-gray-900 mb-3">Typ pozadí:</h4>
                <div className="space-y-2">
                  <div className="flex items-center">
                    <input
                      type="radio"
                      id="image-background"
                      name="background-type"
                      checked={!useVideoBackground}
                      onChange={() => setUseVideoBackground(false)}
                      className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300"
                    />
                    <label htmlFor="image-background" className="ml-2 text-sm text-gray-700">
                      Obrázek pozadí (statický)
                    </label>
                  </div>
                  <div className="flex items-center">
                    <input
                      type="radio"
                      id="video-background"
                      name="background-type"
                      checked={useVideoBackground}
                      onChange={() => setUseVideoBackground(true)}
                      className="h-4 w-4 text-accent-600 focus:ring-accent-500 border-gray-300"
                    />
                    <label htmlFor="video-background" className="ml-2 text-sm text-gray-700">
                      Video pozadí (animované)
                    </label>
                  </div>
                </div>
              </div>

              {/* Zobrazí příslušný uploader podle výběru */}
              <div className="bg-gray-50 p-4 rounded-lg border">
                {useVideoBackground ? (
                  <VideoBackgroundUploader onVideoBackgroundSelected={handleVideoBackgroundSelected} />
                ) : (
                  <BackgroundUploader onBackgroundSelected={handleBackgroundSelected} />
                )}
              </div>
            </div>
          )}

          {/* Generování videa */}
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-3 flex items-center">
              <span className="w-6 h-6 bg-primary-100 rounded-md flex items-center justify-center mr-3">
                <span className="text-primary-600 text-xs font-bold">MP4</span>
              </span>
              Video generování
            </h3>
            <div className="bg-gray-50 p-4 rounded-lg border">
              <div className="flex items-center mb-4">
                <input
                  type="checkbox"
                  id="generateVideo"
                  checked={generateVideo}
                  onChange={(e) => setGenerateVideo(e.target.checked)}
                  className={`h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded ${
                    generatedVoiceFiles.length > 0 && generateVideo ? 'ring-2 ring-success-400' : ''
                  }`}
                />
                <label htmlFor="generateVideo" className="ml-2 text-sm font-medium text-gray-700 flex items-center">
                  Generovat video (.mp4)
                  {generatedVoiceFiles.length > 0 && generateVideo && (
                    <span className="ml-2 px-2 py-1 text-xs bg-success-100 text-success-700 rounded-md">
                      Auto
                    </span>
                  )}
                </label>
              </div>
              
              {generateVideo && (
                <div className="bg-primary-50 border border-primary-200 rounded-lg p-3">
                  <p className="text-sm text-primary-800 font-medium mb-2">
                    Video bude obsahovat:
                  </p>
                  <ul className="text-sm text-primary-700 space-y-1 ml-4">
                    <li>• {
                      useVideoBackground && selectedVideoBackground 
                        ? `Video pozadí: ${selectedVideoBackground.filename}` 
                        : selectedBackground 
                          ? `Obrázek pozadí: ${selectedBackground.filename}` 
                          : 'Vizuální waveform zobrazení zvuku'
                    }</li>
                    <li>• Audio z vygenerovaného MP3 souboru</li>
                    {generateSubtitles && <li>• Titulky ze SRT souboru (pokud jsou zapnuté)</li>}
                    <li>• Výstupní rozlišení: 1920x1080 (Full HD)</li>
                  </ul>
                  <p className="text-xs text-primary-600 mt-2">
                    Generování videa může trvat několik minut v závislosti na délce audia.
                    {useVideoBackground && selectedVideoBackground && <span className="block mt-1">Video pozadí bude automaticky loopováno podle délky audia.</span>}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Chybová zpráva */}
          {error && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-600">CHYBA: {error}</p>
            </div>
          )}

          {/* Tlačítko pro zpracování */}
          <div className="text-center">
            <button
              onClick={handleCombineAudio}
              disabled={isProcessing || audioFiles.length === 0}
              className={`
                w-full py-4 px-6 rounded-lg font-medium text-white text-lg
                ${isProcessing || audioFiles.length === 0
                  ? 'bg-gray-400 cursor-not-allowed' 
                  : 'bg-primary-600 hover:bg-primary-700 shadow-sm'
                }
                transition-colors
              `}
            >
              {isProcessing ? (
                <div className="flex flex-col items-center justify-center">
                  <span className="flex items-center justify-center mb-2">
                    <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 714 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Zpracovávám {audioFiles.length} audio souborů...
                  </span>
                  {audioFiles.length > 50 && (
                    <span className="text-sm text-white/80">
                      Velké množství souborů - může trvat až 20 minut
                    </span>
                  )}
                </div>
              ) : (
                'Spojit & Exportovat'
              )}
            </button>
          </div>
        </div>

        {/* Výsledky */}
        {result && (
          <div className="bg-white rounded-lg shadow-sm p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
              <span className="w-6 h-6 bg-success-100 rounded-md flex items-center justify-center mr-3">
                <span className="text-success-600 text-xs font-bold">OK</span>
              </span>
              Zpracování dokončeno!
            </h3>
            
            <div className="space-y-3">
              <div className="flex items-center justify-between p-4 bg-success-50 border border-success-200 rounded-lg">
                <div>
                  <p className="text-sm font-medium text-success-800">
                    final_output.mp3
                  </p>
                  <p className="text-xs text-success-600">
                    Délka: {formatDuration(result.duration)} | 
                    Segmentů: {result.segments_count}
                  </p>
                </div>
                <button
                  onClick={() => downloadFile(result.audio_file)}
                  className="px-4 py-2 bg-success-600 text-white text-sm rounded-lg hover:bg-success-700 transition-colors"
                >
                  Stáhnout
                </button>
              </div>

              {result.subtitle_file && (
                <div className="flex items-center justify-between p-4 bg-primary-50 border border-primary-200 rounded-lg">
                  <div>
                    <p className="text-sm font-medium text-primary-800">
                      final_output.srt
                    </p>
                    <p className="text-xs text-primary-600">
                      Soubor s titulky
                    </p>
                  </div>
                  <button
                    onClick={() => downloadFile(result.subtitle_file)}
                    className="px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 transition-colors"
                  >
                    Stáhnout
                  </button>
                </div>
              )}

              {result.video_file && (
                <div className="flex items-center justify-between p-4 bg-accent-50 border border-accent-200 rounded-lg">
                  <div>
                    <p className="text-sm font-medium text-accent-800">
                      final_output.mp4
                    </p>
                    <p className="text-xs text-accent-600">
                      {result.video_background_used 
                        ? `Video s video pozadím${generateSubtitles ? ' a titulky' : ''}`
                        : result.background_used 
                          ? `Video s obrázkem pozadí${generateSubtitles ? ' a titulky' : ''}`
                          : `Video s waveform${generateSubtitles ? ' a titulky' : ''}`
                      }
                    </p>
                    {result.video_message && (
                      <p className="text-xs text-accent-500 mt-1">
                        {result.video_message}
                      </p>
                    )}
                  </div>
                  <button
                    onClick={() => downloadFile(result.video_file)}
                    className="px-4 py-2 bg-accent-600 text-white text-sm rounded-lg hover:bg-accent-700 transition-colors"
                  >
                    Stáhnout
                  </button>
                </div>
              )}

              {result.video_error && (
                <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                  <p className="text-sm font-medium text-red-800">
                    Video se nepodařilo vygenerovat
                  </p>
                  <p className="text-xs text-red-700 mt-1">
                    {result.video_error}
                  </p>
                  <p className="text-xs text-red-600 mt-1">
                    Audio a titulky jsou k dispozici, pouze video generování selhalo.
                  </p>
                </div>
              )}
            </div>
          </div>
                  )}
      </div>

      {/* Modal pro YouTube projekt detail */}
      {showYouTubeModal && selectedYouTubeProject && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg max-w-4xl w-full max-h-[90vh] overflow-hidden">
            {/* Header modalu */}
            <div className="p-6 border-b border-gray-200">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-semibold text-gray-900 mb-2">
                    {selectedYouTubeProject.title}
                  </h2>
                  <div className="flex items-center space-x-3 text-sm text-gray-600">
                    <span className="px-3 py-1 bg-red-100 text-red-700 rounded-md">
                      {selectedYouTubeProject.category}
                    </span>
                    <span>{selectedYouTubeProject.duration}</span>
                    <span>
                      {new Date(selectedYouTubeProject.created_at).toLocaleDateString('cs-CZ', {
                        day: '2-digit',
                        month: '2-digit',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </span>
                  </div>
                </div>
                <button
                  onClick={closeYouTubeModal}
                  className="text-gray-400 hover:text-gray-600 text-2xl font-bold"
                >
                  ×
                </button>
              </div>
            </div>

            {/* Obsah modalu */}
            <div className="p-6 overflow-y-auto max-h-[70vh]">
              {/* Thumbnail a základní info */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                <div>
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">Náhled videa:</h3>
                  <img 
                    src={selectedYouTubeProject.thumbnail} 
                    alt={selectedYouTubeProject.title}
                    className="w-full h-40 object-cover rounded-lg bg-gray-100"
                  />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">Soubory projektu:</h3>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between p-3 bg-green-50 border border-green-200 rounded-lg">
                      <div>
                        <p className="text-sm font-medium text-green-800">
                          {selectedYouTubeProject.files.mp4}
                        </p>
                        <p className="text-xs text-green-600">
                          Video soubor • {formatFileSize(selectedYouTubeProject.filesSizes.mp4)}
                        </p>
                      </div>
                      <span className="px-2 py-1 bg-green-100 text-green-700 rounded text-xs">MP4</span>
                    </div>
                    <div className="flex items-center justify-between p-3 bg-blue-50 border border-blue-200 rounded-lg">
                      <div>
                        <p className="text-sm font-medium text-blue-800">
                          {selectedYouTubeProject.files.mp3}
                        </p>
                        <p className="text-xs text-blue-600">
                          Audio soubor • {formatFileSize(selectedYouTubeProject.filesSizes.mp3)}
                        </p>
                      </div>
                      <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs">MP3</span>
                    </div>
                    <div className="flex items-center justify-between p-3 bg-purple-50 border border-purple-200 rounded-lg">
                      <div>
                        <p className="text-sm font-medium text-purple-800">
                          {selectedYouTubeProject.files.srt}
                        </p>
                        <p className="text-xs text-purple-600">
                          Titulky • {formatFileSize(selectedYouTubeProject.filesSizes.srt)}
                        </p>
                      </div>
                      <span className="px-2 py-1 bg-purple-100 text-purple-700 rounded text-xs">SRT</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Popis */}
              <div className="mb-6">
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Popis videa:</h3>
                <div className="p-4 bg-gray-50 rounded-lg text-sm text-gray-800">
                  {selectedYouTubeProject.description}
                </div>
              </div>

              {/* Tagy */}
              <div className="mb-6">
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Tagy:</h3>
                <div className="flex flex-wrap gap-2">
                  {selectedYouTubeProject.tags.map((tag, index) => (
                    <span key={index} className="px-2 py-1 bg-gray-100 text-gray-700 rounded-md text-xs">
                      #{tag}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Footer modalu */}
            <div className="p-6 border-t border-gray-200 bg-gray-50">
              <div className="flex justify-end space-x-3">
                <button
                  onClick={closeYouTubeModal}
                  className="px-4 py-2 bg-gray-300 text-gray-700 rounded-md hover:bg-gray-400 transition-colors"
                >
                  Zavřít
                </button>
                <button
                  onClick={handleUploadToYouTube}
                  className="px-6 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 transition-colors font-medium"
                >
                  Odeslat na YouTube
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Konfirmační modal pro upload */}
      {showUploadConfirm && selectedYouTubeProject && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg max-w-md w-full">
            <div className="p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">
                Potvrdit nahrání na YouTube
              </h3>
              <p className="text-sm text-gray-600 mb-4">
                Opravdu chcete nahrát video "{selectedYouTubeProject.title}" na YouTube?
              </p>
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg mb-4">
                <p className="text-sm text-red-800">
                  <strong>Pozor:</strong> Tato akce nahraje video veřejně na váš YouTube kanál. 
                  Ujistěte se, že máte příslušná oprávnění.
                </p>
              </div>
              <div className="flex justify-end space-x-3">
                <button
                  onClick={() => setShowUploadConfirm(false)}
                  className="px-4 py-2 bg-gray-300 text-gray-700 rounded-md hover:bg-gray-400 transition-colors"
                >
                  Zrušit
                </button>
                <button
                  onClick={confirmUploadToYouTube}
                  className="px-6 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 transition-colors font-medium"
                >
                  Ano, nahrát na YouTube
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* YouTube projekty - hotové k nahrání */}
      <div className="bg-white rounded-lg shadow-sm mb-6">
        <div className="p-6">
          <h2 className="text-xl font-bold text-gray-900 mb-4 flex items-center">
            <span className="w-6 h-6 bg-red-100 rounded-md flex items-center justify-center mr-3">
              <span className="text-red-600 text-xs font-bold">YT</span>
            </span>
            Hotové projekty na YouTube ({mockYouTubeProjects.length})
          </h2>
          <p className="text-sm text-gray-600 mb-6">
            Projekty připravené k nahrání na YouTube s kompletními soubory
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {mockYouTubeProjects.map((project) => (
              <div 
                key={project.id} 
                className="p-3 border border-gray-200 rounded-lg hover:border-red-300 hover:shadow-md transition-all bg-white"
                style={{ maxHeight: '280px' }}
              >
                {/* Thumbnail */}
                <div className="mb-3">
                  <img 
                    src={project.thumbnail} 
                    alt={project.title}
                    className="w-full h-20 object-cover rounded-md bg-gray-100"
                  />
                </div>

                {/* Title a základní info */}
                <div className="mb-2">
                  <h4 className="text-sm font-semibold text-gray-900 mb-1 line-clamp-2 leading-tight">
                    {project.title}
                  </h4>
                  <div className="flex items-center space-x-2 text-xs text-gray-500">
                    <span className="px-2 py-1 bg-red-100 text-red-700 rounded-md">
                      {project.category}
                    </span>
                    <span>{project.duration}</span>
                  </div>
                </div>
                
                {/* Popis (zkrácený) */}
                <p className="text-xs text-gray-600 mb-2 line-clamp-2">
                  {project.description.length > 80 
                    ? project.description.substring(0, 80) + '...' 
                    : project.description
                  }
                </p>

                {/* Soubory */}
                <div className="mb-3">
                  <div className="flex items-center space-x-1 text-xs">
                    <span className="px-1 py-0.5 bg-green-100 text-green-700 rounded text-xs">MP4</span>
                    <span className="px-1 py-0.5 bg-blue-100 text-blue-700 rounded text-xs">MP3</span>
                    <span className="px-1 py-0.5 bg-purple-100 text-purple-700 rounded text-xs">SRT</span>
                    <span className="text-gray-500 text-xs ml-1">
                      {formatFileSize(project.filesSizes.mp4)}
                    </span>
                  </div>
                </div>

                {/* Datum */}
                <div className="text-xs text-gray-400 mb-3">
                  {new Date(project.created_at).toLocaleDateString('cs-CZ', {
                    day: '2-digit',
                    month: '2-digit', 
                    year: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                  })}
                </div>

                {/* Buttony */}
                <div className="flex space-x-2">
                  <button
                    onClick={() => openYouTubeModal(project)}
                    className="flex-1 px-2 py-1.5 bg-blue-600 text-white text-xs font-medium rounded-md hover:bg-blue-700 transition-colors"
                  >
                    Detail
                  </button>
                  <button
                    onClick={() => {
                      setSelectedYouTubeProject(project);
                      handleUploadToYouTube();
                    }}
                    className="flex-1 px-2 py-1.5 bg-red-600 text-white text-xs font-medium rounded-md hover:bg-red-700 transition-colors"
                  >
                    YouTube
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Assistant Manager Card */}
      <div className="bg-white rounded-lg shadow-sm mb-6">
        <AssistantManager onRefreshNeeded={refreshHiddenAssistants} />
      </div>

      {/* Background Uploader Card */}
      <div className="bg-white rounded-lg shadow-sm mb-6">
        <BackgroundUploader 
          onBackgroundSelected={handleBackgroundSelected}
        />
      </div>

      {/* Video Background Uploader Card */}
      <div className="bg-white rounded-lg shadow-sm">
        <VideoBackgroundUploader 
          onVideoBackgroundSelected={handleVideoBackgroundSelected}
          useVideoBackground={useVideoBackground}
          setUseVideoBackground={setUseVideoBackground}
        />
      </div>
    </div>
  );
}

export default App; 