import React, { useState, useEffect } from 'react';
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
  const [showAssistantManagerModal, setShowAssistantManagerModal] = useState(false);
  const [apiTestResults, setApiTestResults] = useState(null);
  const [isTestingApi, setIsTestingApi] = useState(false);
  
  // Nové stavy pro loading a queue projektů
  const [loadingProjects, setLoadingProjects] = useState(new Set()); // Set ID projektů, které se načítají
  const [projectQueue, setProjectQueue] = useState([]); // Fronta projektů čekajících na zpracování
  
  // Stavy pro frontový systém - s localStorage podporou
  const [videoQueue, setVideoQueue] = useState(() => {
    try {
      const saved = localStorage.getItem('video_queue');
      return saved ? JSON.parse(saved) : [];
    } catch (error) {
      console.error('Chyba při načítání video fronty:', error);
      return [];
    }
  });
  const [voiceQueue, setVoiceQueue] = useState(() => {
    try {
      const saved = localStorage.getItem('voice_queue');
      return saved ? JSON.parse(saved) : [];
    } catch (error) {
      console.error('Chyba při načítání voice fronty:', error);
      return [];
    }
  });
  const [videoProductionQueue, setVideoProductionQueue] = useState(() => {
    try {
      const saved = localStorage.getItem('video_production_queue');
      return saved ? JSON.parse(saved) : [];
    } catch (error) {
      console.error('Chyba při načítání video production fronty:', error);
      return [];
    }
  });
  const [videoQueueStatus, setVideoQueueStatus] = useState(() => {
    try {
      return localStorage.getItem('video_queue_status') || 'stopped';
    } catch (error) {
      return 'stopped';
    }
  });
  const [voiceQueueStatus, setVoiceQueueStatus] = useState(() => {
    try {
      return localStorage.getItem('voice_queue_status') || 'stopped';
    } catch (error) {
      return 'stopped';
    }
  });
  const [videoProductionQueueStatus, setVideoProductionQueueStatus] = useState(() => {
    try {
      return localStorage.getItem('video_production_queue_status') || 'stopped';
    } catch (error) {
      return 'stopped';
    }
  });
  const [busyAssistants, setBusyAssistants] = useState(new Set()); // Set asistentů, kteří právě zpracovávají projekt
  const [selectedVoiceProjects, setSelectedVoiceProjects] = useState(new Set()); // Pro hromadný výběr voice projektů
  const [selectedVideoProjects, setSelectedVideoProjects] = useState(new Set()); // Pro hromadný výběr video projektů
  
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

  // Hotový dokončený projekt (ostrý)
  const completedProject = {
    id: 'completed-tesla-socrates',
    title: "Tesla vs Socrates - Elektřina a filosofie",
    assistant_type: "podcast",
    original_prompt: "Vytvořte dialog mezi Teslou a Sokratem o elektřině a filosofii",
    response: "Fascinující dialog mezi dvěma mysliteli různých epoch o podstatě elektřiny, vědy a poznání. Tesla představuje moderní vědecký přístup, zatímco Socrates klade filosofické otázky o podstatě reality a poznání.",
    character_count: 2847,
    created_at: "2025-07-06T10:00:00.000Z",
    preview: "Fascinující dialog mezi dvěma mysliteli různých epoch o podstatě elektřiny, vědy a poznání...",
    status: "completed",
    elevenlabs_json: {
      "Tesla_01": {
        "voice_id": "fb6f5b20hmCY0fO9Gr8v",
        "text": "Dobrý den, Sokrate. Jsem fascinován tím, jak elektřina prostupuje celým vesmírem jako neviditelná síla života."
      },
      "Socrates_01": {
        "voice_id": "Ezn5SsWzN9rYHvvWrFnm", 
        "text": "Zajímavé, Nikolo. Ale než budeme mluvit o elektřině, měli bychom se zeptat: Co to vlastně elektřina je?"
      }
    },
    generated_files: [
      { filename: "Tesla_01.mp3", block_name: "Tesla_01" },
      { filename: "Socrates_01.mp3", block_name: "Socrates_01" }
    ]
  };

  // Testovací projekt pro demonstraci voice fronty (status: ready)
  const readyProject = {
    id: 'ready-demo-project',
    title: "Demo projekt - Připraven k ElevenLabs",
    assistant_type: "podcast", 
    original_prompt: "Vytvořte krátký dialog pro testování voice fronty",
    response: "Krátký demonstrační dialog připravený k odeslání do ElevenLabs pro generování hlasů.",
    character_count: 150,
    created_at: "2025-07-06T11:00:00.000Z",
    preview: "Krátký demonstrační dialog připravený k odeslání do ElevenLabs...",
    status: "ready",
    elevenlabs_json: {
      "Tesla_02": {
        "voice_id": "fb6f5b20hmCY0fO9Gr8v",
        "text": "Toto je testovací zpráva pro demonstraci voice fronty."
      },
      "Socrates_02": {
        "voice_id": "Ezn5SsWzN9rYHvvWrFnm",
        "text": "Ano, tento projekt je připraven k odeslání do ElevenLabs."
      }
    }
  };

  // Vygenerované projekty stavy - načte pouze z localStorage
  const [generatedProjects, setGeneratedProjects] = useState(() => {
    try {
      const saved = localStorage.getItem('generated_projects');
      const savedProjects = saved ? JSON.parse(saved) : [];
      
      // Pokud není v localStorage nic, je to první spuštění - přidáme ukázkové projekty
      if (saved === null) {
        const initialProjects = [completedProject, readyProject];
        localStorage.setItem('generated_projects', JSON.stringify(initialProjects));
        return initialProjects;
      }
      
      // Jinak vrátíme přesně to co je uložené (i prázdný seznam)
      return savedProjects;
    } catch (error) {
      console.error('Chyba při načítání projektů z localStorage:', error);
      return [];
    }
  });
  const [selectedProject, setSelectedProject] = useState(null);
  const [showProjectDetail, setShowProjectDetail] = useState(false);
  const [activeDetailTab, setActiveDetailTab] = useState('preview'); // Tab stav pro detail projektu
  const [projectFilter, setProjectFilter] = useState('all'); // Filtr pro projekty
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false); // Stav pro potvrzení smazání
  const [projectToDelete, setProjectToDelete] = useState(null); // Projekt ke smazání
  const [showVideoConfigModal, setShowVideoConfigModal] = useState(false); // Stav pro video konfiguraci
  const [videoConfigItem, setVideoConfigItem] = useState(null); // Aktuální video item pro konfiguraci
  
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
    setActiveDetailTab('preview'); // Reset na první tab
  };

  // Funkce pro zavření detailu projektu
  const closeProjectDetail = () => {
    setSelectedProject(null);
    setShowProjectDetail(false);
  };

  // Funkce pro otevření potvrzení smazání
  const openDeleteConfirm = (project) => {
    setProjectToDelete(project);
    setShowDeleteConfirm(true);
  };

  // Funkce pro zavření potvrzení smazání
  const closeDeleteConfirm = () => {
    setProjectToDelete(null);
    setShowDeleteConfirm(false);
  };

  // Funkce pro skutečné smazání projektu
  const handleDeleteProject = () => {
    if (projectToDelete) {
      // Odebereme projekt ze seznamu
      setGeneratedProjects(prev => {
        const updatedProjects = prev.filter(p => p.id !== projectToDelete.id);
        // Uložíme do localStorage
        try {
          localStorage.setItem('generated_projects', JSON.stringify(updatedProjects));
        } catch (error) {
          console.error('Chyba při ukládání projektů:', error);
        }
        return updatedProjects;
      });
      
      // Uzavřeme modaly
      closeDeleteConfirm();
      closeProjectDetail();
      
      // Zobrazíme zprávu o úspěchu
      setResult({ success: true, message: `Projekt "${projectToDelete.title}" byl úspěšně smazán.` });
    }
  };

  // Funkce pro zastavení a smazání běžícího projektu
  const handleDeleteLoadingProject = (project) => {
    console.log('⏹️ Zastavuji a mažu běžící projekt:', project.title);
    
    // Odebereme projekt ze seznamu
    setGeneratedProjects(prev => {
      const updatedProjects = prev.filter(p => p.id !== project.id);
      // Uložíme do localStorage
      try {
        localStorage.setItem('generated_projects', JSON.stringify(updatedProjects));
      } catch (error) {
        console.error('Chyba při ukládání projektů:', error);
      }
      return updatedProjects;
    });
    
    // Zobrazíme zprávu o úspěchu
    setResult({ success: true, message: `Běžící projekt "${project.title}" byl zastavený a smazán.` });
  };

  // Funkce pro otevření video konfigurace
  const openVideoConfig = (videoItem) => {
    setVideoConfigItem(videoItem);
    setShowVideoConfigModal(true);
  };

  // Funkce pro zavření video konfigurace
  const closeVideoConfig = () => {
    setVideoConfigItem(null);
    setShowVideoConfigModal(false);
  };

  // Funkce pro uložení video konfigurace
  const saveVideoConfig = (updatedConfig) => {
    if (videoConfigItem) {
      setVideoProductionQueue(prev => prev.map(item => 
        item.id === videoConfigItem.id
          ? { ...item, video_config: updatedConfig }
          : item
      ));
      closeVideoConfig();
      console.log('🎬 Video konfigurace uložena:', updatedConfig);
    }
  };

  // Funkce pro potvrzení projektu
  const handleProjectConfirm = async (project) => {
    console.log('🚀 handleProjectConfirm ZAČÍNÁ');
    console.log('📋 Projekt potvrzen:', project);
    console.log('🔑 ElevenLabs API klíč:', elevenlabsApiKey ? '✅ Nastaven' : '❌ Chybí');
    
    // Pokud projekt nemá elevenlabs_json, nelze ho zpracovat
    if (!project.elevenlabs_json) {
      console.error('❌ Projekt nemá elevenlabs_json');
      setError('Projekt nemá připravený JSON pro ElevenLabs');
      return;
    }
    
    // Zkontrolujeme, zda máme ElevenLabs API klíč
    if (!elevenlabsApiKey) {
      console.error('❌ ElevenLabs API klíč chybí');
      setError('ElevenLabs API klíč není nastaven. Jděte do API Management.');
      return;
    }
    
    console.log('📤 JSON pro ElevenLabs:', project.elevenlabs_json);
    
    // Označíme projekt jako zpracovává se
    setGeneratedProjects(prev => {
      return prev.map(p => {
        if (p.id === project.id) {
          return { ...p, status: 'processing' };
        }
        return p;
      });
    });
    
    try {
      console.log('🎙️ Odesílám projekt do ElevenLabs:', project.title);
      console.log('📊 Payload:', {
        voice_blocks: project.elevenlabs_json,
        api_key: elevenlabsApiKey ? '***nastaven***' : 'CHYBÍ'
      });
      
      const response = await axios.post('/api/generate-voices', {
        voice_blocks: project.elevenlabs_json,
        api_key: elevenlabsApiKey
      });
      
      console.log('📨 Odpověď z API:', response.data);
      
      if (response.data.success) {
        console.log('✅ Hlasy úspěšně vygenerovány:', response.data.generated_files);
        
        // Označíme projekt jako dokončený a automaticky přidáme do video production fronty
        setGeneratedProjects(prev => {
          console.log('🔄 Aktualizuji stav projektu na completed');
          const updated = prev.map(p => {
            if (p.id === project.id) {
              console.log('✅ Nalezen projekt k aktualizaci:', p.id);
              const updatedProject = { 
                ...p, 
                status: 'completed',
                generated_files: response.data.generated_files
              };
              
              // Automaticky přidáme do video production fronty
              console.log('🎬 Automaticky přidávám projekt do Video Production fronty');
              addToVideoProductionQueue(updatedProject);
              
              return updatedProject;
            }
            return p;
          });
          
          console.log('💾 Ukládám projekty:', updated);
          
          // Uložíme do localStorage
          try {
            localStorage.setItem('generated_projects', JSON.stringify(updated));
            console.log('✅ Projekty uloženy do localStorage');
          } catch (error) {
            console.error('❌ Chyba při ukládání projektů:', error);
          }
          return updated;
        });
        
        // Předáme vygenerované soubory do hlavní aplikace
        if (response.data.generated_files) {
          console.log('🎤 Předávám soubory do VoiceGenerator:', response.data.generated_files);
          const filesWithTexts = response.data.generated_files.map(file => ({
            ...file,
            original_text: project.elevenlabs_json[file.block_name]?.text || ''
          }));
          handleVoicesGenerated(filesWithTexts);
        }
        
        setResult({ 
          success: true, 
          message: `Projekt "${project.title}" byl úspěšně zpracován! Vygenerováno ${response.data.generated_files?.length || 0} hlasových souborů.` 
        });
        
        console.log('🎉 handleProjectConfirm ÚSPĚŠNĚ DOKONČEN');
      } else {
        console.error('❌ API odpověď neobsahuje success=true:', response.data);
        throw new Error(response.data.error || 'Neznámá chyba při generování hlasů');
      }
    } catch (error) {
      console.error('❌ Chyba při odesílání do ElevenLabs:', error);
      console.error('❌ Error response:', error.response?.data);
      console.error('❌ Error message:', error.message);
      
      // Označíme projekt jako chybný
      setGeneratedProjects(prev => {
        console.log('❌ Označuji projekt jako error stav');
        const updated = prev.map(p => {
          if (p.id === project.id) {
            console.log('❌ Nalezen projekt pro error stav:', p.id);
            return { ...p, status: 'error' };
          }
          return p;
        });
        
        // Uložíme do localStorage
        try {
          localStorage.setItem('generated_projects', JSON.stringify(updated));
          console.log('💾 Error stav uložen do localStorage');
        } catch (storageError) {
          console.error('❌ Chyba při ukládání error stavu:', storageError);
        }
        
        return updated;
      });
      
      const errorMessage = error.response?.data?.error || error.message || 'Chyba při odesílání do ElevenLabs';
      setError(errorMessage);
      console.error('❌ Finální error message:', errorMessage);
    }
  };

  // Funkce pro práci s modaly
  const openAddAssistantModal = () => {
    setShowAddAssistantModal(true);
    setNewAssistantName('');
    setNewAssistantId('');
    setNewAssistantDescription('');
    setNewAssistantCategory('podcast');
    setError(''); // Vyčistíme error zprávy
    setResult(null); // Vyčistíme result zprávy
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

  const openAssistantManagerModal = () => {
    setShowAssistantManagerModal(true);
  };

  const closeAssistantManagerModal = () => {
    setShowAssistantManagerModal(false);
  };

  // Funkce pro přidání nového asistenta
  const handleAddAssistant = () => {
    console.log('🚀 handleAddAssistant SPUŠTĚN');
    console.log('📝 Název:', newAssistantName);
    console.log('🆔 ID:', newAssistantId);
    console.log('📂 Kategorie:', newAssistantCategory);
    console.log('📄 Popis:', newAssistantDescription);
    
    if (!newAssistantName.trim() || !newAssistantId.trim()) {
      console.log('❌ Chyba: prázdné pole');
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
      console.log('✅ Asistent úspěšně přidán:', newAssistant);
      setResult({
        success: true,
        message: `OpenAI Asistent "${newAssistantName}" byl úspěšně přidán!`
      });
    } catch (error) {
      console.error('❌ Chyba při ukládání asistentů:', error);
      setError('Chyba při ukládání asistenta');
      return;
    }

    // Vyčištění formuláře
    console.log('🧹 Čistím formulář a zavírám modal');
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

  // Automatické ukládání front do localStorage
  React.useEffect(() => {
    try {
      localStorage.setItem('video_queue', JSON.stringify(videoQueue));
    } catch (error) {
      console.error('Chyba při ukládání video fronty:', error);
    }
  }, [videoQueue]);

  React.useEffect(() => {
    try {
      localStorage.setItem('voice_queue', JSON.stringify(voiceQueue));
    } catch (error) {
      console.error('Chyba při ukládání voice fronty:', error);
    }
  }, [voiceQueue]);

  React.useEffect(() => {
    try {
      localStorage.setItem('video_production_queue', JSON.stringify(videoProductionQueue));
    } catch (error) {
      console.error('Chyba při ukládání video production fronty:', error);
    }
  }, [videoProductionQueue]);

  // Automatické ukládání statusů front do localStorage
  React.useEffect(() => {
    try {
      localStorage.setItem('video_queue_status', videoQueueStatus);
    } catch (error) {
      console.error('Chyba při ukládání statusu video fronty:', error);
    }
  }, [videoQueueStatus]);

  React.useEffect(() => {
    try {
      localStorage.setItem('voice_queue_status', voiceQueueStatus);
    } catch (error) {
      console.error('Chyba při ukládání statusu voice fronty:', error);
    }
  }, [voiceQueueStatus]);

  React.useEffect(() => {
    try {
      localStorage.setItem('video_production_queue_status', videoProductionQueueStatus);
    } catch (error) {
      console.error('Chyba při ukládání statusu video production fronty:', error);
    }
  }, [videoProductionQueueStatus]);

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
    
    // Automatické obnovení běžících front po refreshi
    if (videoQueueStatus === 'running' && videoQueue.length > 0) {
      console.log('🔄 Obnovuji běžící asistentí frontu po refresh - počet položek:', videoQueue.length);
      setTimeout(() => processVideoQueue(), 1000);
    }
    if (voiceQueueStatus === 'running' && voiceQueue.length > 0) {
      console.log('🔄 Obnovuji běžící voice frontu po refresh - počet položek:', voiceQueue.length);
      setTimeout(() => processVoiceQueue(), 1000);
    }
    if (videoProductionQueueStatus === 'running' && videoProductionQueue.length > 0) {
      console.log('🔄 Obnovuji běžící video frontu po refresh - počet položek:', videoProductionQueue.length);
      setTimeout(() => processVideoProductionQueue(), 1000);
    }
    
    // Debug info o frontách po startu
    console.log('📊 Fronty po startu:');
    console.log('   🤖 Asistenti fronta:', videoQueue.length, 'položek, status:', videoQueueStatus);
    console.log('   🎙️ Voice fronta:', voiceQueue.length, 'položek, status:', voiceQueueStatus);
    console.log('   🎬 Video fronta:', videoProductionQueue.length, 'položek, status:', videoProductionQueueStatus);
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

  // Funkce pro zpracování vygenerovaných hlasů z ElevenLabs
  const handleVoicesGenerated = (generatedFiles) => {
    console.log('🎤 handleVoicesGenerated VOLÁNA s:', generatedFiles);
    
    if (!generatedFiles || generatedFiles.length === 0) {
      console.warn('⚠️ Žádné soubory k přidání');
      return;
    }
    
    // Uložíme do stavu pro další použití
    setGeneratedVoiceFiles(generatedFiles);
    
    // Automaticky zaškrtneme titulky a video
    setGenerateSubtitles(true);
    setGenerateVideo(true);
    
    // Předvyplní JSON pro titulky na základě vygenerovaných souborů
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
      virtualFile.original_text = file.original_text || '';
      virtualFile.block_name = file.block_name || '';
      virtualFile.voice_id = file.voice_id || '';
      
      return virtualFile;
    });
    
    console.log('🎵 Přidávám soubory do audioFiles:', virtualFiles);
    
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
      // Aktualizujeme existující loading projekt
      setGeneratedProjects(prev => {
        const updated = prev.map(project => {
          // Najdeme loading projekt podle ID nebo podle toho, že je loading
          if (project.status === 'loading' && project.original_prompt === finalProject.video_info?.title) {
            return {
              ...project,
              title: finalProject.title || 'Nový video projekt',
              assistant_type: 'video_pipeline',
              response: generateProjectPreview(elevenlabsJson),
              character_count: calculateCharacterCount(elevenlabsJson),
              preview: generateProjectPreview(elevenlabsJson).substring(0, 150) + '...',
              elevenlabs_json: elevenlabsJson, // Uložíme JSON pro pozdější použití
              final_project: finalProject, // Uložíme původní projekt
              status: 'ready' // ready pro potvrzení
            };
          }
          return project;
        });
        
        // Uložíme do localStorage
        try {
          localStorage.setItem('generated_projects', JSON.stringify(updated));
        } catch (error) {
          console.error('Chyba při ukládání projektů:', error);
        }
        return updated;
      });
      
      // Odstraníme projekt z loading stavu
      setLoadingProjects(prev => {
        const newSet = new Set(prev);
        // Odstraníme všechny loading projekty pro tento prompt
        prev.forEach(id => {
          const project = generatedProjects.find(p => p.id === id);
          if (project && project.original_prompt === finalProject.video_info?.title) {
            newSet.delete(id);
          }
        });
        return newSet;
      });
      
      console.log('✅ Projekt aktualizován v Vygenerované projekty');
      
      // Zobrazíme zprávu o úspěchu
      setResult({
        success: true,
        message: `Projekt "${finalProject.title}" je připraven! Zkontrolujte ho v sekci "Vygenerované projekty" a potvrďte pro odesílání do ElevenLabs.`
      });
    } else {
      console.warn('⚠️ Nepodařilo se vytvořit JSON pro ElevenLabs - možná chybí voice_blocks');
      console.warn('⚠️ FinalProject struktura:', JSON.stringify(finalProject, null, 2));
      
      // Označíme loading projekt jako chybný
      setGeneratedProjects(prev => {
        return prev.map(project => {
          if (project.status === 'loading' && project.original_prompt === finalProject.video_info?.title) {
            return {
              ...project,
              status: 'error',
              preview: 'Chyba při generování'
            };
          }
          return project;
        });
      });
    }
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
    // Také aktualizujeme localStorage s aktuálním stavem
    localStorage.setItem('available_assistants', JSON.stringify(availableAssistants));
  };

  // Helper funkce pro generování náhledu projektu
  const generateProjectPreview = (elevenlabsJson) => {
    const blocks = Object.entries(elevenlabsJson || {});
    if (blocks.length === 0) return 'Žádný obsah';
    
    return blocks.map(([blockName, blockData]) => {
      const speaker = blockName.split('_')[0]; // Tesla_01 -> Tesla
      return `${speaker}: ${blockData.text}`;
    }).join('\n\n');
  };

  // Helper funkce pro počítání znaků
  const calculateCharacterCount = (elevenlabsJson) => {
    const blocks = Object.entries(elevenlabsJson || {});
    return blocks.reduce((total, [blockName, blockData]) => {
      return total + (blockData.text?.length || 0);
    }, 0);
  };

  // Funkce pro vytvoření loading projektu
  const createLoadingProject = (prompt) => {
    const loadingProject = {
      id: Date.now(),
      title: prompt.substring(0, 50) + '...',
      assistant_type: 'video_pipeline',
      original_prompt: prompt,
      response: '',
      character_count: 0,
      created_at: new Date().toISOString(),
      preview: 'Generuje se obsah...',
      status: 'loading' // loading stav
    };
    
    // Přidáme loading projekt do seznamu
    setGeneratedProjects(prev => [loadingProject, ...prev]);
    
    // Označíme projekt jako načítající se
    setLoadingProjects(prev => new Set(prev).add(loadingProject.id));
    
    return loadingProject.id;
  };

  // Funkce pro filtrování projektů podle stavu
  const getFilteredProjects = () => {
    switch (projectFilter) {
      case 'processing':
        return generatedProjects.filter(p => p.status === 'loading' || p.status === 'ready');
      case 'ready':
        return generatedProjects.filter(p => p.status === 'ready' || p.status === 'processing' || p.status === 'completed');
      case 'completed':
        return generatedProjects.filter(p => p.status === 'completed' || p.status === 'video_completed');
      case 'video_ready':
        return generatedProjects.filter(p => p.status === 'video_completed');
      default: // 'all'
        return generatedProjects;
    }
  };

  // Funkce pro získání počtu projektů v každém filtru
  const getFilterCounts = () => {
    return {
      all: generatedProjects.length,
      processing: generatedProjects.filter(p => p.status === 'loading' || p.status === 'ready').length,
      ready: generatedProjects.filter(p => p.status === 'ready' || p.status === 'processing' || p.status === 'completed').length,
      completed: generatedProjects.filter(p => p.status === 'completed' || p.status === 'video_completed').length,
      video_ready: generatedProjects.filter(p => p.status === 'video_completed').length
    };
  };

  // ==================== FRONTOVÝ SYSTÉM ====================
  
  // Funkce pro ovládání video fronty
  const startVideoQueue = () => {
    console.log('🚀 Spouštím Asistentí frontu...');
    console.log('   📊 Počet projektů ve frontě:', videoQueue.length);
    console.log('   🔍 Projekty ve frontě:', videoQueue.map(p => `${p.prompt} (${p.selectedAssistant})`));
    console.log('   🔑 OpenAI API klíč:', openaiApiKey ? 'NASTAVEN ✅' : 'CHYBÍ ❌');
    
    // Kontrola API klíče před spuštěním
    if (!openaiApiKey || openaiApiKey.trim() === '') {
      alert('❌ CHYBA: OpenAI API klíč není nastaven!\n\n' +
            'Pro generování textů potřebujete OpenAI API klíč.\n' +
            'Nastavte ho v sekci API klíčů na hlavní stránce.');
      console.error('❌ ZASTAVUJI FRONTU: Chybí OpenAI API klíč');
      return;
    }
    
    if (videoQueue.length === 0) {
      alert('❌ CHYBA: Asistenti fronta je prázdná!\n\n' +
            'Přidejte alespoň jeden projekt do fronty pomocí "Přidat do fronty" tlačítka.');
      console.error('❌ ZASTAVUJI FRONTU: Fronta je prázdná');
      return;
    }
    
    setVideoQueueStatus('running');
    processVideoQueue();
  };

  const pauseVideoQueue = () => {
    setVideoQueueStatus('paused');
  };

  const stopVideoQueue = () => {
    console.log('🛑 Zastavuji Asistentí frontu...');
    setVideoQueueStatus('stopped');
  };

  const clearVideoQueue = () => {
    console.log('🗑️ Mažu Asistentí frontu...');
    setVideoQueue([]);
    setVideoQueueStatus('stopped');
  };

  // Funkce pro ovládání voice fronty
  const startVoiceQueue = () => {
    setVoiceQueueStatus('running');
    processVoiceQueue();
  };

  const pauseVoiceQueue = () => {
    setVoiceQueueStatus('paused');
  };

  const stopVoiceQueue = () => {
    setVoiceQueueStatus('stopped');
  };

  const clearVoiceQueue = () => {
    setVoiceQueue([]);
    setVoiceQueueStatus('stopped');
    setSelectedVoiceProjects(new Set());
  };

  // Funkce pro ovládání video production fronty
  const startVideoProductionQueue = () => {
    setVideoProductionQueueStatus('running');
    processVideoProductionQueue();
  };

  const pauseVideoProductionQueue = () => {
    setVideoProductionQueueStatus('paused');
  };

  const stopVideoProductionQueue = () => {
    setVideoProductionQueueStatus('stopped');
  };

  const clearVideoProductionQueue = () => {
    setVideoProductionQueue([]);
    setVideoProductionQueueStatus('stopped');
    setSelectedVideoProjects(new Set());
  };

  // Funkce pro přidání do video fronty
  const addToVideoQueue = (prompt, selectedAssistant) => {
    const queueItem = {
      id: Date.now(),
      prompt,
      selectedAssistant,
      status: 'waiting',
      created_at: new Date().toISOString()
    };
    
    console.log('➕ Přidávám projekt do Asistentí fronty:');
    console.log('   📝 Prompt:', prompt);
    console.log('   🤖 Asistent:', selectedAssistant);
    console.log('   🆔 ID:', queueItem.id);
    
    setVideoQueue(prev => {
      const newQueue = [...prev, queueItem];
      console.log('   📊 Nová velikost fronty:', newQueue.length);
      return newQueue;
    });
  };

  // Funkce pro přidání do voice fronty
  const addToVoiceQueue = (projects) => {
    const queueItems = projects.map(project => ({
      id: project.id,
      project,
      status: 'waiting',
      created_at: new Date().toISOString()
    }));
    setVoiceQueue(prev => [...prev, ...queueItems]);
  };

  // Funkce pro přidání do video production fronty
  const addToVideoProductionQueue = (project) => {
    const videoItem = {
      id: Date.now() + Math.random(), // Jedinečný identifikátor
      project,
      status: 'waiting',
      added_at: new Date().toISOString(),
      video_config: {
        // Výchozí konfigurace videa
        resolution: '1920x1080',
        fps: 30,
        background_type: 'image',
        background_source: null,
        show_subtitles: true,
        avatar_style: 'static'
      }
    };

    setVideoProductionQueue(prev => [...prev, videoItem]);
    console.log('🎬 Projekt přidán do Video Production fronty:', project.title);
  };

  // Funkce pro zpracování asistentů fronty (FIFO - jeden projekt za druhým)
  const processVideoQueue = async () => {
    console.log('🔄 processVideoQueue() - kontrola stavu...');
    console.log('   Status fronty:', videoQueueStatus);
    console.log('   Počet projektů:', videoQueue.length);
    
    if (videoQueueStatus !== 'running' || videoQueue.length === 0) {
      console.log('❌ Zastavuji zpracování - fronta není running nebo je prázdná');
      return;
    }

    // Najdi PRVNÍ projekt čekající na zpracování (FIFO)
    const currentItem = videoQueue.find(item => item.status === 'waiting');

    if (!currentItem) {
      console.log('⏳ Žádný projekt čeká na zpracování - čekám 1 sekundu...');
      setTimeout(() => {
        if (videoQueueStatus === 'running') {
          processVideoQueue();
        }
      }, 1000);
      return;
    }

         console.log(`🚀 Zpracovávám projekt: "${currentItem.prompt}" s ${currentItem.selectedAssistant}`);
     
     // Označíme projekt jako zpracovává se
     setVideoQueue(prev => prev.map(item => 
       item.id === currentItem.id 
         ? { ...item, status: 'processing' }
         : item
     ));

      try {
        console.log('🤖 Volám API pro projekt:', currentItem.prompt);
        console.log('🤖 Asistent ID:', currentItem.selectedAssistant);
        console.log('🔑 API klíč k dispozici:', openaiApiKey ? 'Ano' : 'Ne');
        console.log('🔑 API klíč hodnota pro debug:', openaiApiKey ? `${openaiApiKey.substring(0,10)}...` : 'PRAZDNE');
        console.log('🔑 localStorage hodnota:', localStorage.getItem('openai_api_key') ? `${localStorage.getItem('openai_api_key').substring(0,10)}...` : 'PRAZDNE');
        
        // Vytvoříme loading projekt
        const loadingProjectId = createLoadingProject(currentItem.prompt);
        
        // SKUTEČNÉ VOLÁNÍ API PRO GENEROVÁNÍ PROJEKTU
        const payload = {
          topic: currentItem.prompt,
          target_minutes: 12,
          target_words: 1800,
          detail_assistant_id: currentItem.selectedAssistant,
          api_key: openaiApiKey
        };
        console.log('📦 Payload pro backend:', {
          ...payload,
          api_key: payload.api_key ? `${payload.api_key.substring(0,10)}...` : 'PRAZDNE'
        });
        
        const response = await axios.post('/api/generate-video-structure', payload, {
          timeout: 60000 // 1 minuta
        });

        if (!response.data.success) {
          throw new Error(response.data.error);
        }

        const { detail_assistant_id, segments, video_context } = response.data.data;
        
        // Paralelní generování všech segmentů
        const segmentPromises = segments.map(async (segment) => {
          const segmentResponse = await axios.post('/api/generate-segment-content', {
            detail_assistant_id: detail_assistant_id,
            segment_info: segment,
            video_context: video_context,
            api_key: openaiApiKey,
            assistant_category: 'podcast', // Výchozí kategorie
            narrator_voice_id: 'fb6f5b20hmCY0fO9Gr8v' // Výchozí voice
          }, {
            timeout: 200000
          });

          return {
            segmentId: segment.id,
            content: segmentResponse.data.data.segment_content
          };
        });

        const segmentResults = await Promise.all(segmentPromises);
        
        // Sestavení výsledného objektu
        const segmentContentsMap = {};
        segmentResults.forEach(result => {
          segmentContentsMap[result.segmentId] = result.content;
        });
        
        // Sestavení finálního projektu
        const finalVideoProject = {
          id: loadingProjectId,
          title: currentItem.prompt.substring(0, 50) + '...',
          created_at: new Date().toISOString(),
          assistant_type: currentItem.selectedAssistant,
          original_prompt: currentItem.prompt,
          video_info: {
            title: currentItem.prompt,
            total_duration_minutes: 12,
            total_words_estimate: 1800,
            target_audience: "Obecná veřejnost",
            tone: "Vzdělávací"
          },
          segments: segments.map(segment => ({
            ...segment,
            content: segmentContentsMap[segment.id]
          })),
          metadata: {
            total_segments: segments.length,
            generation_time: new Date().toISOString()
          }
        };

        // Předáme do handleVideoProjectGenerated pro dokončení
        handleVideoProjectGenerated(finalVideoProject);
        
        // Označíme jako dokončené a odstraníme z fronty
        setVideoQueue(prev => prev.filter(item => item.id !== currentItem.id));
        
        console.log('✅ Projekt úspěšně dokončen:', finalVideoProject.title);
        console.log('✅ Projekt odebrán z fronty, zbývá:', videoQueue.length - 1, 'projektů');
        
      } catch (error) {
        console.error('❌ CHYBA při zpracování projektu:', error);
        console.error('❌ Detaily chyby:', error.response?.data || error.message);
        setError(`Chyba při zpracování "${currentItem.prompt}": ${error.message}`);
        
        // Označíme jako chybný
        setVideoQueue(prev => prev.map(item => 
          item.id === currentItem.id 
            ? { ...item, status: 'error' }
            : item
        ));
      }
    
    // Pokračujeme zpracováním dalšího projektu za 2 sekundy
    console.log('🔄 Pokračuji na další projekt za 2 sekundy...');
    setTimeout(() => {
      if (videoQueueStatus === 'running') {
        processVideoQueue();
      }
    }, 2000);
  };

  // Funkce pro zpracování voice fronty (FIFO)
  const processVoiceQueue = async () => {
    if (voiceQueueStatus !== 'running' || voiceQueue.length === 0) {
      return;
    }

    const currentItem = voiceQueue[0];
    if (currentItem.status === 'waiting') {
      // Označíme jako zpracovává se
      setVoiceQueue(prev => prev.map(item => 
        item.id === currentItem.id 
          ? { ...item, status: 'processing' }
          : item
      ));

      try {
        // Zde se volá handleProjectConfirm pro skutečné zpracování
        console.log('🎙️ Zpracovávám voice projekt:', currentItem.project.title);
        
        await handleProjectConfirm(currentItem.project);
        
        // Označíme jako dokončené a odstraníme z fronty
        setVoiceQueue(prev => prev.filter(item => item.id !== currentItem.id));
        
        // Pokračujeme s dalším projektem
        setTimeout(() => {
          if (voiceQueueStatus === 'running') {
            processVoiceQueue();
          }
        }, 1000);
        
      } catch (error) {
        console.error('Chyba při zpracování voice projektu:', error);
        // Označíme jako chybný
        setVoiceQueue(prev => prev.map(item => 
          item.id === currentItem.id 
            ? { ...item, status: 'error' }
            : item
        ));
      }
    }
  };

  // Funkce pro zpracování video production fronty (FIFO)
  const processVideoProductionQueue = async () => {
    if (videoProductionQueueStatus !== 'running' || videoProductionQueue.length === 0) {
      return;
    }

    const currentItem = videoProductionQueue[0];
    if (currentItem.status === 'waiting') {
      // Označíme jako zpracovává se
      setVideoProductionQueue(prev => prev.map(item => 
        item.id === currentItem.id 
          ? { ...item, status: 'processing' }
          : item
      ));

      try {
        // Zde se bude volat video rendering API
        console.log('🎬 Zpracovávám video produkci:', currentItem.project.title);
        console.log('🎬 Video konfigurace:', currentItem.video_config);
        
        // Simulace video renderingu (později se nahradí skutečným API)
        await new Promise(resolve => setTimeout(resolve, 5000));
        
        // Označíme jako dokončené a odstraníme z fronty
        setVideoProductionQueue(prev => prev.filter(item => item.id !== currentItem.id));
        
        // Aktualizujeme stav projektu na video_completed
        setGeneratedProjects(prev => prev.map(p => 
          p.id === currentItem.project.id 
            ? { ...p, status: 'video_completed', video_file: `${p.title}.mp4` }
            : p
        ));
        
        // Pokračujeme s dalším projektem
        setTimeout(() => {
          if (videoProductionQueueStatus === 'running') {
            processVideoProductionQueue();
          }
        }, 1000);
        
      } catch (error) {
        console.error('Chyba při zpracování video produkce:', error);
        // Označíme jako chybný
        setVideoProductionQueue(prev => prev.map(item => 
          item.id === currentItem.id 
            ? { ...item, status: 'error' }
            : item
        ));
      }
    }
  };

  // Funkce pro hromadný výběr projektů
  const toggleVoiceProjectSelection = (projectId) => {
    setSelectedVoiceProjects(prev => {
      const newSet = new Set(prev);
      if (newSet.has(projectId)) {
        newSet.delete(projectId);
      } else {
        newSet.add(projectId);
      }
      return newSet;
    });
  };

  const selectAllVoiceProjects = () => {
    const readyProjects = generatedProjects.filter(p => p.status === 'ready');
    setSelectedVoiceProjects(new Set(readyProjects.map(p => p.id)));
  };

  const deselectAllVoiceProjects = () => {
    setSelectedVoiceProjects(new Set());
  };

  // Funkce pro hromadné přidání vybraných projektů do voice fronty
  const addSelectedToVoiceQueue = () => {
    const readyProjects = generatedProjects.filter(p => 
      p.status === 'ready' && selectedVoiceProjects.has(p.id)
    );
    addToVoiceQueue(readyProjects);
    setSelectedVoiceProjects(new Set());
  };

  // Funkce pro hromadný výběr video projektů
  const toggleVideoProjectSelection = (projectId) => {
    setSelectedVideoProjects(prev => {
      const newSet = new Set(prev);
      if (newSet.has(projectId)) {
        newSet.delete(projectId);
      } else {
        newSet.add(projectId);
      }
      return newSet;
    });
  };

  const selectAllVideoProjects = () => {
    const completedProjects = generatedProjects.filter(p => p.status === 'completed');
    setSelectedVideoProjects(new Set(completedProjects.map(p => p.id)));
  };

  const deselectAllVideoProjects = () => {
    setSelectedVideoProjects(new Set());
  };

  // Funkce pro hromadné přidání vybraných projektů do video production fronty
  const addSelectedToVideoProductionQueue = () => {
    const completedProjects = generatedProjects.filter(p => 
      p.status === 'completed' && selectedVideoProjects.has(p.id)
    );
    completedProjects.forEach(project => addToVideoProductionQueue(project));
    setSelectedVideoProjects(new Set());
  };

  // Debug funkce pro analýzu stavu při načtení stránky
  useEffect(() => {
    console.log('🔍 STAV APLIKACE PŘI NAČTENÍ:');
    console.log('   🔑 OpenAI API klíč from localStorage:', localStorage.getItem('openai_api_key'));
    console.log('   🔑 OpenAI API klíč from state:', openaiApiKey ? `NASTAVEN (${openaiApiKey.substring(0,7)}...)` : 'CHYBÍ ❌');
    console.log('   🔑 ElevenLabs API klíč from localStorage:', localStorage.getItem('elevenlabs_api_key'));
    console.log('   🔑 ElevenLabs API klíč from state:', elevenlabsApiKey ? `NASTAVEN (${elevenlabsApiKey.substring(0,7)}...)` : 'CHYBÍ ❌');
    console.log('   📊 Asistenti fronta:', videoQueue.length, 'projektů');
    console.log('   📊 Voice fronta:', voiceQueue.length, 'projektů');
    console.log('   📊 Video production fronta:', videoProductionQueue.length, 'projektů');
    console.log('   📊 Vygenerované projekty:', generatedProjects.length, 'projektů');
    console.log('   🚦 Status asistenti fronty:', videoQueueStatus);
    console.log('   🚦 Status voice fronty:', voiceQueueStatus);
    console.log('   🚦 Status video fronty:', videoProductionQueueStatus);
    console.log('   👥 Dostupní asistenti:', availableAssistants.map(a => a.name).join(', '));
  }, []); // Spustí se pouze při prvním načtení

  // Automatické ukládání API klíčů do localStorage při změně
  useEffect(() => {
    if (openaiApiKey) {
      localStorage.setItem('openai_api_key', openaiApiKey);
      console.log('💾 OpenAI API klíč automaticky uložen do localStorage');
    }
  }, [openaiApiKey]);

  useEffect(() => {
    if (elevenlabsApiKey) {
      localStorage.setItem('elevenlabs_api_key', elevenlabsApiKey);
      console.log('💾 ElevenLabs API klíč automaticky uložen do localStorage');
    }
  }, [elevenlabsApiKey]);

  useEffect(() => {
    if (youtubeApiKey) {
      localStorage.setItem('youtube_api_key', youtubeApiKey);
      console.log('💾 YouTube API klíč automaticky uložen do localStorage');
    }
  }, [youtubeApiKey]);

  // Automatické ukládání front do localStorage při změně
  useEffect(() => {
    localStorage.setItem('video_queue', JSON.stringify(videoQueue));
    console.log('💾 Video fronta automaticky uložena do localStorage:', videoQueue.length, 'projektů');
  }, [videoQueue]);

  useEffect(() => {
    localStorage.setItem('voice_queue', JSON.stringify(voiceQueue));
    console.log('💾 Voice fronta automaticky uložena do localStorage:', voiceQueue.length, 'projektů');
  }, [voiceQueue]);

  useEffect(() => {
    localStorage.setItem('video_production_queue', JSON.stringify(videoProductionQueue));
    console.log('💾 Video production fronta automaticky uložena do localStorage:', videoProductionQueue.length, 'projektů');
  }, [videoProductionQueue]);

  useEffect(() => {
    localStorage.setItem('video_queue_status', videoQueueStatus);
    console.log('💾 Video queue status automaticky uložen:', videoQueueStatus);
  }, [videoQueueStatus]);

  useEffect(() => {
    localStorage.setItem('voice_queue_status', voiceQueueStatus);
    console.log('💾 Voice queue status automaticky uložen:', voiceQueueStatus);
  }, [voiceQueueStatus]);

  useEffect(() => {
    localStorage.setItem('video_production_queue_status', videoProductionQueueStatus);
    console.log('💾 Video production queue status automaticky uložen:', videoProductionQueueStatus);
  }, [videoProductionQueueStatus]);

  // Export všech dat pro backup
  const exportAllData = () => {
    const allData = {
      openai_api_key: localStorage.getItem('openai_api_key') || '',
      elevenlabs_api_key: localStorage.getItem('elevenlabs_api_key') || '',
      youtube_api_key: localStorage.getItem('youtube_api_key') || '',
      available_assistants: localStorage.getItem('available_assistants') || '[]',
      generated_projects: localStorage.getItem('generated_projects') || '[]',
      video_queue: localStorage.getItem('video_queue') || '[]',
      voice_queue: localStorage.getItem('voice_queue') || '[]',
      video_production_queue: localStorage.getItem('video_production_queue') || '[]',
      video_queue_status: localStorage.getItem('video_queue_status') || 'stopped',
      voice_queue_status: localStorage.getItem('voice_queue_status') || 'stopped', 
      video_production_queue_status: localStorage.getItem('video_production_queue_status') || 'stopped',
      voice_volumes: localStorage.getItem('voice_volumes') || '{}',
      export_date: new Date().toISOString()
    };
    
    const dataStr = JSON.stringify(allData, null, 2);
    const dataBlob = new Blob([dataStr], {type: 'application/json'});
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `podcast_backup_${new Date().toISOString().split('T')[0]}.json`;
    link.click();
    URL.revokeObjectURL(url);
    
    setResult({
      success: true,
      message: '🗂️ Všechna data byla exportována do souboru!'
    });
  };

  // Import všech dat z backup souboru
  const importAllData = (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const allData = JSON.parse(e.target.result);
        
        // Obnovení všech dat do localStorage
        Object.entries(allData).forEach(([key, value]) => {
          if (key !== 'export_date') {
            localStorage.setItem(key, value);
          }
        });
        
        // Reload stránky pro aplikaci změn
        setResult({
          success: true,
          message: `🔄 Data úspěšně importována z ${allData.export_date || 'neznámého data'}! Stránka se za 2 sekundy obnoví...`
        });
        
        setTimeout(() => {
          window.location.reload();
        }, 2000);
        
      } catch (error) {
        console.error('Chyba při importu:', error);
        setError('❌ Chyba při importu dat. Zkontrolujte formát souboru.');
      }
    };
    reader.readAsText(file);
    
    // Reset input
    event.target.value = '';
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
            availableAssistants={availableAssistants}
            onOpenApiManagement={openApiKeyModal}
            onOpenAddAssistant={openAddAssistantModal}
            onOpenAssistantManager={openAssistantManagerModal}
            onVideoProjectGenerated={handleVideoProjectGenerated}
            onVideoProjectStarted={createLoadingProject}
            onAddToVideoQueue={addToVideoQueue}
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
              
              {/* Filtry projektů */}
              <div className="flex flex-wrap gap-2 mb-4">
                {[
                  { key: 'all', label: 'Všechny', count: getFilterCounts().all },
                  { key: 'processing', label: 'Ke zpracování', count: getFilterCounts().processing },
                  { key: 'ready', label: 'Texty hotové', count: getFilterCounts().ready },
                  { key: 'completed', label: 'Hlasy hotové', count: getFilterCounts().completed },
                  { key: 'video_ready', label: 'Video hotové', count: getFilterCounts().video_ready }
                ].map(filter => (
                  <button
                    key={filter.key}
                    onClick={() => setProjectFilter(filter.key)}
                    className={`px-3 py-2 text-sm font-medium rounded-md transition-colors ${
                      projectFilter === filter.key
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    }`}
                  >
                    {filter.label} ({filter.count})
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {getFilteredProjects().map((project) => {
                // Určíme barvy a ikony podle stavu
                let statusColor, statusIcon, statusText, borderColor;
                switch (project.status) {
                  case 'loading':
                    statusColor = 'bg-yellow-100 text-yellow-700';
                    statusIcon = '⏳';
                    statusText = 'Generuje se...';
                    borderColor = 'border-yellow-300';
                    break;
                  case 'ready':
                    statusColor = 'bg-green-100 text-green-700';
                    statusIcon = '✅';
                    statusText = 'Připraveno';
                    borderColor = 'border-green-300';
                    break;
                  case 'processing':
                    statusColor = 'bg-blue-100 text-blue-700';
                    statusIcon = '🔄';
                    statusText = 'Zpracovává se...';
                    borderColor = 'border-blue-300';
                    break;
                  case 'completed':
                    statusColor = 'bg-purple-100 text-purple-700';
                    statusIcon = '🎉';
                    statusText = 'Dokončeno';
                    borderColor = 'border-purple-300';
                    break;
                  case 'error':
                    statusColor = 'bg-red-100 text-red-700';
                    statusIcon = '❌';
                    statusText = 'Chyba';
                    borderColor = 'border-red-300';
                    break;
                  default:
                    statusColor = 'bg-gray-100 text-gray-700';
                    statusIcon = '📄';
                    statusText = 'Neznámý';
                    borderColor = 'border-gray-300';
                }

                return (
                  <div 
                    key={project.id} 
                    className={`p-4 border-2 ${borderColor} rounded-lg hover:shadow-md transition-all ${
                      project.status === 'loading' || project.status === 'processing' ? 'opacity-75' : ''
                    }`}
                  >
                    <div className="mb-3">
                      <div className="flex items-center justify-between mb-1">
                        <h4 className="text-sm font-semibold text-gray-900 truncate">
                          {project.title}
                        </h4>
                        <span className={`px-2 py-1 text-xs rounded-full ${statusColor}`}>
                          {statusIcon} {statusText}
                        </span>
                      </div>
                      <div className="flex items-center space-x-2 text-xs text-gray-500">
                        <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded-md">
                          {project.assistant_type === 'video_pipeline' ? 'Video Pipeline' : 
                           getVisibleAssistants().find(a => a.id === project.assistant_type)?.name || 'Asistent'}
                        </span>
                        <span>{project.character_count.toLocaleString()} znaků</span>
                      </div>
                    </div>
                    
                    <p className="text-xs text-gray-600 mb-3 line-clamp-3">
                      {project.status === 'loading' && (
                        <span className="flex items-center">
                          <span className="animate-spin w-3 h-3 border border-gray-400 border-t-transparent rounded-full mr-2"></span>
                          Generuje se obsah...
                        </span>
                      )}
                      {project.status === 'processing' && (
                        <span className="flex items-center">
                          <span className="animate-pulse w-3 h-3 bg-blue-500 rounded-full mr-2"></span>
                          Odesílá se do ElevenLabs...
                        </span>
                      )}
                      {project.status !== 'loading' && project.status !== 'processing' && project.preview}
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
                        className="flex-1 px-3 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50"
                        disabled={project.status === 'loading'}
                      >
                        Detail
                      </button>
                      
                      {project.status === 'loading' && (
                        <button
                          onClick={() => handleDeleteLoadingProject(project)}
                          className="flex-1 px-3 py-2 bg-red-600 text-white text-sm font-medium rounded-md hover:bg-red-700 transition-colors"
                        >
                          ⏹️ Zastavit
                        </button>
                      )}
                      
                      {project.status === 'ready' && (
                        <button
                          onClick={() => handleProjectConfirm(project)}
                          className="flex-1 px-3 py-2 bg-green-600 text-white text-sm font-medium rounded-md hover:bg-green-700 transition-colors"
                        >
                          Potvrdit
                        </button>
                      )}
                      
                      {project.status === 'processing' && (
                        <button
                          className="flex-1 px-3 py-2 bg-gray-400 text-white text-sm font-medium rounded-md cursor-not-allowed"
                          disabled
                        >
                          Zpracovává se...
                        </button>
                      )}
                      
                      {project.status === 'completed' && (
                        <button
                          className="flex-1 px-3 py-2 bg-purple-600 text-white text-sm font-medium rounded-md cursor-default"
                          disabled
                        >
                          Dokončeno
                        </button>
                      )}
                      
                      {project.status === 'error' && (
                        <button
                          onClick={() => handleProjectConfirm(project)}
                          className="flex-1 px-3 py-2 bg-red-600 text-white text-sm font-medium rounded-md hover:bg-red-700 transition-colors"
                        >
                          Opakovat
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Sekce front pro zpracování */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
          <div className="mb-4">
            <h3 className="text-lg font-semibold text-gray-900 mb-3 flex items-center">
              <span className="w-6 h-6 bg-orange-100 rounded-md flex items-center justify-center mr-3">
                <span className="text-orange-600 text-xs font-bold">Q</span>
              </span>
              Frontový systém
            </h3>
            <p className="text-sm text-gray-600">
              Automatické zpracování: 🤖 Asistenti → 🎙️ Hlasy → 🎬 Video
            </p>
          </div>

          {/* Vertikální uspořádání front */}
          <div className="space-y-6">
            
            {/* Asistenti fronta */}
            <div className="border border-gray-200 rounded-lg p-4">
              <div className="flex items-center justify-between mb-4">
                <h4 className="text-md font-semibold text-gray-900 flex items-center">
                  🤖 Asistenti fronta ({videoQueue.length})
                </h4>
                <span className={`px-2 py-1 text-xs rounded-full ${
                  videoQueueStatus === 'running' ? 'bg-green-100 text-green-700' :
                  videoQueueStatus === 'paused' ? 'bg-yellow-100 text-yellow-700' :
                  'bg-gray-100 text-gray-700'
                }`}>
                  {videoQueueStatus === 'running' ? '▶️ Běží' :
                   videoQueueStatus === 'paused' ? '⏸️ Pozastavena' :
                   '⏹️ Zastavena'}
                </span>
              </div>

              {/* Ovládací tlačítka video fronty */}
              <div className="flex gap-2 mb-4">
                <button
                  onClick={startVideoQueue}
                  disabled={videoQueueStatus === 'running' || videoQueue.length === 0}
                  className="px-3 py-1 bg-green-600 text-white text-sm rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  ▶️ Start
                </button>
                <button
                  onClick={pauseVideoQueue}
                  disabled={videoQueueStatus !== 'running'}
                  className="px-3 py-1 bg-yellow-600 text-white text-sm rounded-md hover:bg-yellow-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  ⏸️ Pauza
                </button>
                <button
                  onClick={stopVideoQueue}
                  disabled={videoQueueStatus === 'stopped'}
                  className="px-3 py-1 bg-red-600 text-white text-sm rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  ⏹️ Stop
                </button>
                <button
                  onClick={clearVideoQueue}
                  disabled={videoQueue.length === 0}
                  className="px-3 py-1 bg-gray-600 text-white text-sm rounded-md hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  🗑️ Vyčistit
                </button>
              </div>

              {/* Seznam asistentí fronty */}
              <div className="space-y-3 max-h-80 overflow-y-auto">
                {videoQueue.length === 0 ? (
                  <div className="text-sm text-gray-500 text-center py-8 bg-gray-50 rounded-lg">
                    <div className="mb-2">🤖</div>
                    <div>Žádné projekty ve frontě</div>
                    <div className="text-xs mt-1">Přidejte nový projekt pomocí "⏱️ Přidat do fronty"</div>
                  </div>
                ) : (
                  videoQueue.map((item, index) => (
                    <div key={item.id} className="bg-white border rounded-lg p-4 shadow-sm">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center space-x-3">
                          <div className="flex items-center justify-center w-8 h-8 bg-blue-100 rounded-full">
                            <span className="text-blue-600 font-semibold text-sm">#{index + 1}</span>
                          </div>
                          <div className="flex-1">
                            <h5 className="text-sm font-semibold text-gray-900 mb-1">
                              {item.prompt.length > 80 ? item.prompt.substring(0, 80) + '...' : item.prompt}
                            </h5>
                            <div className="flex items-center space-x-4 text-xs text-gray-600">
                              <span className="flex items-center">
                                🤖 {getVisibleAssistants().find(a => a.id === item.selectedAssistant)?.name || item.selectedAssistant}
                                {busyAssistants.has(item.selectedAssistant) && item.status === 'waiting' && (
                                  <span className="ml-1 px-1 py-0.5 text-xs bg-orange-100 text-orange-700 rounded font-medium">BUSY</span>
                                )}
                              </span>
                              <span className="flex items-center">
                                📅 {new Date(item.created_at).toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' })}
                              </span>
                              <span className="flex items-center">
                                📝 ~1800 slov
                              </span>
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center space-x-3">
                          <span className={`px-3 py-1 text-xs rounded-full font-medium ${
                            item.status === 'waiting' ? 
                              (busyAssistants.has(item.selectedAssistant) ? 'bg-orange-100 text-orange-700' : 'bg-yellow-100 text-yellow-700') :
                            item.status === 'processing' ? 'bg-blue-100 text-blue-700' :
                            item.status === 'error' ? 'bg-red-100 text-red-700' :
                            'bg-gray-100 text-gray-700'
                          }`}>
                            {item.status === 'waiting' ? 
                              (busyAssistants.has(item.selectedAssistant) ? '🚧 Čeká (asistent zaneprázdněn)' : '⏳ Připraven k zpracování') :
                             item.status === 'processing' ? '🔄 Generuje text' :
                             item.status === 'error' ? '❌ Chyba při generování' :
                             'Neznámý stav'}
                          </span>
                          {item.status === 'processing' && (
                            <div className="w-6 h-6">
                              <div className="animate-spin w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full"></div>
                            </div>
                          )}
                        </div>
                      </div>
                      
                      {/* Progress bar pro processing */}
                      {item.status === 'processing' && (
                        <div className="w-full bg-gray-200 rounded-full h-2 mb-2">
                          <div className="bg-blue-600 h-2 rounded-full animate-pulse" style={{width: '45%'}}></div>
                        </div>
                      )}
                      
                      {/* Akční tlačítka */}
                      <div className="flex justify-end space-x-2">
                        {item.status === 'waiting' && (
                          <button
                            onClick={() => {
                              setVideoQueue(prev => prev.filter(i => i.id !== item.id));
                            }}
                            className="px-3 py-1 text-xs bg-red-100 text-red-700 rounded-md hover:bg-red-200 transition-colors"
                          >
                            🗑️ Odebrat
                          </button>
                        )}
                        {item.status === 'error' && (
                          <button
                            onClick={() => {
                              setVideoQueue(prev => prev.map(i => 
                                i.id === item.id ? { ...i, status: 'waiting' } : i
                              ));
                            }}
                            className="px-3 py-1 text-xs bg-blue-100 text-blue-700 rounded-md hover:bg-blue-200 transition-colors"
                          >
                            🔄 Zkusit znovu
                          </button>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Voice fronta */}
            <div className="border border-gray-200 rounded-lg p-4">
              <div className="flex items-center justify-between mb-4">
                <h4 className="text-md font-semibold text-gray-900 flex items-center">
                  🎙️ Voice fronta ({voiceQueue.length})
                </h4>
                <span className={`px-2 py-1 text-xs rounded-full ${
                  voiceQueueStatus === 'running' ? 'bg-green-100 text-green-700' :
                  voiceQueueStatus === 'paused' ? 'bg-yellow-100 text-yellow-700' :
                  'bg-gray-100 text-gray-700'
                }`}>
                  {voiceQueueStatus === 'running' ? '▶️ Běží' :
                   voiceQueueStatus === 'paused' ? '⏸️ Pozastavena' :
                   '⏹️ Zastavena'}
                </span>
              </div>

              {/* Ovládací tlačítka voice fronty */}
              <div className="flex gap-2 mb-4">
                <button
                  onClick={startVoiceQueue}
                  disabled={voiceQueueStatus === 'running' || voiceQueue.length === 0}
                  className="px-3 py-1 bg-green-600 text-white text-sm rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  ▶️ Start
                </button>
                <button
                  onClick={pauseVoiceQueue}
                  disabled={voiceQueueStatus !== 'running'}
                  className="px-3 py-1 bg-yellow-600 text-white text-sm rounded-md hover:bg-yellow-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  ⏸️ Pauza
                </button>
                <button
                  onClick={stopVoiceQueue}
                  disabled={voiceQueueStatus === 'stopped'}
                  className="px-3 py-1 bg-red-600 text-white text-sm rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  ⏹️ Stop
                </button>
                <button
                  onClick={clearVoiceQueue}
                  disabled={voiceQueue.length === 0}
                  className="px-3 py-1 bg-gray-600 text-white text-sm rounded-md hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  🗑️ Vyčistit
                </button>
              </div>

              {/* Hromadný výběr projektů */}
              <div className="mb-4 p-3 bg-blue-50 rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-blue-900">
                    Hromadný výběr ({selectedVoiceProjects.size} vybraných)
                  </span>
                  <div className="flex gap-2">
                    <button
                      onClick={selectAllVoiceProjects}
                      className="px-2 py-1 bg-blue-600 text-white text-xs rounded-md hover:bg-blue-700"
                    >
                      Vybrat vše
                    </button>
                    <button
                      onClick={deselectAllVoiceProjects}
                      className="px-2 py-1 bg-gray-600 text-white text-xs rounded-md hover:bg-gray-700"
                    >
                      Zrušit výběr
                    </button>
                  </div>
                </div>
                <div className="space-y-1 max-h-32 overflow-y-auto">
                  {generatedProjects.filter(p => p.status === 'ready').map(project => (
                    <label key={project.id} className="flex items-center">
                      <input
                        type="checkbox"
                        checked={selectedVoiceProjects.has(project.id)}
                        onChange={() => toggleVoiceProjectSelection(project.id)}
                        className="mr-2 h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                      />
                      <span className="text-sm text-gray-700 truncate">
                        {project.title}
                      </span>
                    </label>
                  ))}
                </div>
                <button
                  onClick={addSelectedToVoiceQueue}
                  disabled={selectedVoiceProjects.size === 0}
                  className="w-full mt-2 px-3 py-2 bg-blue-600 text-white text-sm rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Přidat vybrané do fronty ({selectedVoiceProjects.size})
                </button>
              </div>

              {/* Seznam voice fronty */}
              <div className="space-y-3 max-h-80 overflow-y-auto">
                {voiceQueue.length === 0 ? (
                  <div className="text-sm text-gray-500 text-center py-8 bg-gray-50 rounded-lg">
                    <div className="mb-2">🎙️</div>
                    <div>Žádné projekty ve frontě</div>
                    <div className="text-xs mt-1">Vyberte projekty a přidejte je pomocí "Přidat vybrané do fronty"</div>
                  </div>
                ) : (
                  voiceQueue.map((item, index) => (
                    <div key={item.id} className="bg-white border rounded-lg p-4 shadow-sm">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center space-x-3">
                          <div className="flex items-center justify-center w-8 h-8 bg-green-100 rounded-full">
                            <span className="text-green-600 font-semibold text-sm">#{index + 1}</span>
                          </div>
                          <div className="flex-1">
                            <h5 className="text-sm font-semibold text-gray-900 mb-1">
                              {item.project.title}
                            </h5>
                            <div className="flex items-center space-x-4 text-xs text-gray-600">
                              <span className="flex items-center">
                                🤖 {getVisibleAssistants().find(a => a.id === item.project.assistant_type)?.name || 'Asistent'}
                              </span>
                              <span className="flex items-center">
                                📊 {item.project.character_count?.toLocaleString()} znaků
                              </span>
                              <span className="flex items-center">
                                🎵 {Object.keys(item.project.elevenlabs_json || {}).length} hlasů
                              </span>
                              <span className="flex items-center">
                                📅 {new Date(item.project.created_at).toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' })}
                              </span>
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center space-x-3">
                          <span className={`px-3 py-1 text-xs rounded-full font-medium ${
                            item.status === 'waiting' ? 'bg-yellow-100 text-yellow-700' :
                            item.status === 'processing' ? 'bg-blue-100 text-blue-700' :
                            item.status === 'error' ? 'bg-red-100 text-red-700' :
                            'bg-gray-100 text-gray-700'
                          }`}>
                            {item.status === 'waiting' ? '⏳ Čeká na ElevenLabs' :
                             item.status === 'processing' ? '🔄 Generuje hlasy' :
                             item.status === 'error' ? '❌ Chyba ElevenLabs' :
                             'Neznámý stav'}
                          </span>
                          {item.status === 'processing' && (
                            <div className="w-6 h-6">
                              <div className="animate-spin w-4 h-4 border-2 border-green-600 border-t-transparent rounded-full"></div>
                            </div>
                          )}
                        </div>
                      </div>
                      
                      {/* Progress bar pro processing */}
                      {item.status === 'processing' && (
                        <div className="w-full bg-gray-200 rounded-full h-2 mb-2">
                          <div className="bg-green-600 h-2 rounded-full animate-pulse" style={{width: '65%'}}></div>
                        </div>
                      )}
                      
                      {/* Preview hlasových bloků */}
                      {item.project.elevenlabs_json && (
                        <div className="mb-3 p-2 bg-gray-50 rounded-md">
                          <div className="text-xs text-gray-600 mb-1">Hlasové bloky:</div>
                          <div className="flex flex-wrap gap-1">
                            {Object.keys(item.project.elevenlabs_json).slice(0, 3).map(blockName => (
                              <span key={blockName} className="px-2 py-1 text-xs bg-blue-100 text-blue-700 rounded">
                                {blockName}
                              </span>
                            ))}
                            {Object.keys(item.project.elevenlabs_json).length > 3 && (
                              <span className="px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded">
                                +{Object.keys(item.project.elevenlabs_json).length - 3} dalších
                              </span>
                            )}
                          </div>
                        </div>
                      )}
                      
                      {/* Akční tlačítka */}
                      <div className="flex justify-end space-x-2">
                        {item.status === 'waiting' && (
                          <button
                            onClick={() => {
                              setVoiceQueue(prev => prev.filter(i => i.id !== item.id));
                            }}
                            className="px-3 py-1 text-xs bg-red-100 text-red-700 rounded-md hover:bg-red-200 transition-colors"
                          >
                            🗑️ Odebrat
                          </button>
                        )}
                        {item.status === 'error' && (
                          <button
                            onClick={() => {
                              setVoiceQueue(prev => prev.map(i => 
                                i.id === item.id ? { ...i, status: 'waiting' } : i
                              ));
                            }}
                            className="px-3 py-1 text-xs bg-blue-100 text-blue-700 rounded-md hover:bg-blue-200 transition-colors"
                          >
                            🔄 Zkusit znovu
                          </button>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Video fronta */}
            <div className="border border-gray-200 rounded-lg p-4">
              <div className="flex items-center justify-between mb-4">
                <h4 className="text-md font-semibold text-gray-900 flex items-center">
                  🎬 Video fronta ({videoProductionQueue.length})
                </h4>
                <span className={`px-2 py-1 text-xs rounded-full ${
                  videoProductionQueueStatus === 'running' ? 'bg-green-100 text-green-700' :
                  videoProductionQueueStatus === 'paused' ? 'bg-yellow-100 text-yellow-700' :
                  'bg-gray-100 text-gray-700'
                }`}>
                  {videoProductionQueueStatus === 'running' ? '▶️ Běží' :
                   videoProductionQueueStatus === 'paused' ? '⏸️ Pozastavena' :
                   '⏹️ Zastavena'}
                </span>
              </div>

              {/* Ovládací tlačítka video production fronty */}
              <div className="flex gap-2 mb-4">
                <button
                  onClick={startVideoProductionQueue}
                  disabled={videoProductionQueueStatus === 'running' || videoProductionQueue.length === 0}
                  className="px-3 py-1 bg-green-600 text-white text-sm rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  ▶️ Start
                </button>
                <button
                  onClick={pauseVideoProductionQueue}
                  disabled={videoProductionQueueStatus !== 'running'}
                  className="px-3 py-1 bg-yellow-600 text-white text-sm rounded-md hover:bg-yellow-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  ⏸️ Pauza
                </button>
                <button
                  onClick={stopVideoProductionQueue}
                  disabled={videoProductionQueueStatus === 'stopped'}
                  className="px-3 py-1 bg-red-600 text-white text-sm rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  ⏹️ Stop
                </button>
                <button
                  onClick={clearVideoProductionQueue}
                  disabled={videoProductionQueue.length === 0}
                  className="px-3 py-1 bg-gray-600 text-white text-sm rounded-md hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  🗑️ Vyčistit
                </button>
              </div>

              {/* Hromadný výběr video projektů */}
              <div className="mb-4 p-3 bg-purple-50 rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-purple-900">
                    Hromadný výběr ({selectedVideoProjects.size} vybraných)
                  </span>
                  <div className="flex gap-2">
                    <button
                      onClick={selectAllVideoProjects}
                      className="px-2 py-1 bg-purple-600 text-white text-xs rounded-md hover:bg-purple-700"
                    >
                      Vybrat vše
                    </button>
                    <button
                      onClick={deselectAllVideoProjects}
                      className="px-2 py-1 bg-gray-600 text-white text-xs rounded-md hover:bg-gray-700"
                    >
                      Zrušit výběr
                    </button>
                  </div>
                </div>
                <div className="space-y-1 max-h-32 overflow-y-auto">
                  {generatedProjects.filter(p => p.status === 'completed').map(project => (
                    <label key={project.id} className="flex items-center">
                      <input
                        type="checkbox"
                        checked={selectedVideoProjects.has(project.id)}
                        onChange={() => toggleVideoProjectSelection(project.id)}
                        className="mr-2 h-4 w-4 text-purple-600 focus:ring-purple-500 border-gray-300 rounded"
                      />
                      <span className="text-sm text-gray-700 truncate">
                        {project.title}
                      </span>
                    </label>
                  ))}
                </div>
                <button
                  onClick={addSelectedToVideoProductionQueue}
                  disabled={selectedVideoProjects.size === 0}
                  className="w-full mt-2 px-3 py-2 bg-purple-600 text-white text-sm rounded-md hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Přidat vybrané do fronty ({selectedVideoProjects.size})
                </button>
              </div>

              {/* Seznam video fronty */}
              <div className="space-y-3 max-h-80 overflow-y-auto">
                {videoProductionQueue.length === 0 ? (
                  <div className="text-sm text-gray-500 text-center py-8 bg-gray-50 rounded-lg">
                    <div className="mb-2">🎬</div>
                    <div>Žádné projekty ve frontě</div>
                    <div className="text-xs mt-1">Vyberte dokončené projekty a přidejte je do video produkce</div>
                  </div>
                ) : (
                  videoProductionQueue.map((item, index) => (
                    <div key={item.id} className="bg-white border rounded-lg p-4 shadow-sm">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center space-x-3">
                          <div className="flex items-center justify-center w-8 h-8 bg-purple-100 rounded-full">
                            <span className="text-purple-600 font-semibold text-sm">#{index + 1}</span>
                          </div>
                          <div className="flex-1">
                            <h5 className="text-sm font-semibold text-gray-900 mb-1">
                              {item.project.title}
                            </h5>
                            <div className="flex items-center space-x-4 text-xs text-gray-600">
                              <span className="flex items-center">
                                🎥 {item.video_config.resolution}
                              </span>
                              <span className="flex items-center">
                                📺 {item.video_config.fps}fps
                              </span>
                              <span className="flex items-center">
                                🎨 {item.video_config.background_type === 'image' ? 'Obrázek' : item.video_config.background_type === 'video' ? 'Video' : 'Gradient'}
                              </span>
                              <span className="flex items-center">
                                📋 {item.video_config.show_subtitles ? 'S titulky' : 'Bez titulků'}
                              </span>
                              <span className="flex items-center">
                                📅 {new Date(item.added_at).toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' })}
                              </span>
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center space-x-3">
                          <button
                            onClick={() => openVideoConfig(item)}
                            className="px-3 py-1 bg-blue-600 text-white text-xs rounded-md hover:bg-blue-700 transition-colors"
                          >
                            ⚙️ Konfigurace
                          </button>
                          <span className={`px-3 py-1 text-xs rounded-full font-medium ${
                            item.status === 'waiting' ? 'bg-yellow-100 text-yellow-700' :
                            item.status === 'processing' ? 'bg-blue-100 text-blue-700' :
                            item.status === 'error' ? 'bg-red-100 text-red-700' :
                            'bg-gray-100 text-gray-700'
                          }`}>
                            {item.status === 'waiting' ? '⏳ Čeká na rendering' :
                             item.status === 'processing' ? '🔄 Renderuje video' :
                             item.status === 'error' ? '❌ Chyba renderingu' :
                             'Neznámý stav'}
                          </span>
                          {item.status === 'processing' && (
                            <div className="w-6 h-6">
                              <div className="animate-spin w-4 h-4 border-2 border-purple-600 border-t-transparent rounded-full"></div>
                            </div>
                          )}
                        </div>
                      </div>
                      
                      {/* Progress bar pro processing */}
                      {item.status === 'processing' && (
                        <div className="w-full bg-gray-200 rounded-full h-2 mb-2">
                          <div className="bg-purple-600 h-2 rounded-full animate-pulse" style={{width: '30%'}}></div>
                        </div>
                      )}
                      
                      {/* Detaily video konfigurace */}
                      <div className="mb-3 p-2 bg-gray-50 rounded-md">
                        <div className="text-xs text-gray-600 mb-1">Video konfigurace:</div>
                        <div className="flex flex-wrap gap-2">
                          <span className="px-2 py-1 text-xs bg-purple-100 text-purple-700 rounded">
                            📐 {item.video_config.resolution}
                          </span>
                          <span className="px-2 py-1 text-xs bg-blue-100 text-blue-700 rounded">
                            ⚡ {item.video_config.fps}fps
                          </span>
                          <span className="px-2 py-1 text-xs bg-green-100 text-green-700 rounded">
                            🎨 {item.video_config.background_type}
                          </span>
                          {item.video_config.show_subtitles && (
                            <span className="px-2 py-1 text-xs bg-yellow-100 text-yellow-700 rounded">
                              📋 Titulky
                            </span>
                          )}
                        </div>
                      </div>
                      
                      {/* Akční tlačítka */}
                      <div className="flex justify-end space-x-2">
                        {item.status === 'waiting' && (
                          <>
                            <button
                              onClick={() => openVideoConfig(item)}
                              className="px-3 py-1 text-xs bg-blue-100 text-blue-700 rounded-md hover:bg-blue-200 transition-colors"
                            >
                              ⚙️ Upravit nastavení
                            </button>
                            <button
                              onClick={() => {
                                setVideoProductionQueue(prev => prev.filter(i => i.id !== item.id));
                              }}
                              className="px-3 py-1 text-xs bg-red-100 text-red-700 rounded-md hover:bg-red-200 transition-colors"
                            >
                              🗑️ Odebrat
                            </button>
                          </>
                        )}
                        {item.status === 'error' && (
                          <button
                            onClick={() => {
                              setVideoProductionQueue(prev => prev.map(i => 
                                i.id === item.id ? { ...i, status: 'waiting' } : i
                              ));
                            }}
                            className="px-3 py-1 text-xs bg-blue-100 text-blue-700 rounded-md hover:bg-blue-200 transition-colors"
                          >
                            🔄 Zkusit znovu
                          </button>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>

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

                {/* Stav projektu */}
                {selectedProject.status && (
                  <div className="mb-4">
                    <h3 className="text-sm font-semibold text-gray-700 mb-2">Stav projektu:</h3>
                    <div className="p-3 bg-blue-50 rounded-lg text-sm">
                      {selectedProject.status === 'loading' && (
                        <span className="flex items-center text-yellow-700">
                          <span className="animate-spin w-4 h-4 border border-yellow-600 border-t-transparent rounded-full mr-2"></span>
                          Generuje se obsah...
                        </span>
                      )}
                      {selectedProject.status === 'ready' && (
                        <span className="text-green-700">✅ Připraveno k odesílání do ElevenLabs</span>
                      )}
                      {selectedProject.status === 'processing' && (
                        <span className="flex items-center text-blue-700">
                          <span className="animate-pulse w-4 h-4 bg-blue-500 rounded-full mr-2"></span>
                          Zpracovává se v ElevenLabs...
                        </span>
                      )}
                      {selectedProject.status === 'completed' && (
                        <span className="text-purple-700">🎉 Dokončeno! Hlasy byly vygenerovány.</span>
                      )}
                      {selectedProject.status === 'error' && (
                        <span className="text-red-700">❌ Chyba při zpracování</span>
                      )}
                    </div>
                  </div>
                )}

                {/* Tabs pro různé pohledy */}
                <div className="mb-4">
                  <div className="border-b border-gray-200">
                    <nav className="-mb-px flex space-x-8">
                      <button
                        onClick={() => setActiveDetailTab('preview')}
                        className={`py-2 px-1 border-b-2 font-medium text-sm ${
                          activeDetailTab === 'preview'
                            ? 'border-blue-500 text-blue-600'
                            : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                        }`}
                      >
                        📖 Náhled textu
                      </button>
                      <button
                        onClick={() => setActiveDetailTab('json')}
                        className={`py-2 px-1 border-b-2 font-medium text-sm ${
                          activeDetailTab === 'json'
                            ? 'border-blue-500 text-blue-600'
                            : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                        }`}
                      >
                        🔧 JSON pro ElevenLabs
                      </button>
                    </nav>
                  </div>
                </div>

                {/* Tab Content */}
                {activeDetailTab === 'preview' && (
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700 mb-2">Vygenerovaný obsah (náhled):</h3>
                    <div className="p-4 bg-blue-50 rounded-lg text-sm text-gray-800 whitespace-pre-wrap">
                      {selectedProject.status === 'loading' ? (
                        <span className="flex items-center text-gray-600">
                          <span className="animate-spin w-4 h-4 border border-gray-400 border-t-transparent rounded-full mr-2"></span>
                          Čekejte, obsah se generuje...
                        </span>
                      ) : (
                        selectedProject.response
                      )}
                    </div>
                  </div>
                )}

                {activeDetailTab === 'json' && (
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700 mb-2">JSON pro ElevenLabs:</h3>
                    {selectedProject.elevenlabs_json ? (
                      <div className="p-4 bg-gray-900 rounded-lg text-sm text-green-400 font-mono overflow-x-auto">
                        <pre>{JSON.stringify(selectedProject.elevenlabs_json, null, 2)}</pre>
                      </div>
                    ) : (
                      <div className="p-4 bg-yellow-50 rounded-lg text-sm text-yellow-800">
                        {selectedProject.status === 'loading' ? (
                          <span className="flex items-center">
                            <span className="animate-spin w-4 h-4 border border-yellow-600 border-t-transparent rounded-full mr-2"></span>
                            JSON se generuje...
                          </span>
                        ) : (
                          '⚠️ JSON není dostupný pro tento projekt'
                        )}
                      </div>
                    )}
                    
                    {selectedProject.elevenlabs_json && (
                      <div className="mt-3 p-3 bg-green-50 rounded-lg">
                        <p className="text-sm text-green-700">
                          <strong>📊 Statistiky JSON:</strong>
                        </p>
                        <ul className="text-xs text-green-600 mt-1 space-y-1">
                          <li>• Počet bloků: {Object.keys(selectedProject.elevenlabs_json).length}</li>
                          <li>• Voice ID Tesla: {Object.values(selectedProject.elevenlabs_json).find(block => block.voice_id?.includes('TZJ3e6'))?.voice_id || 'nenalezeno'}</li>
                          <li>• Voice ID Socrates: {Object.values(selectedProject.elevenlabs_json).find(block => block.voice_id?.includes('2oYYnH'))?.voice_id || 'nenalezeno'}</li>
                          <li>• Celkový počet znaků: {Object.values(selectedProject.elevenlabs_json).reduce((total, block) => total + (block.text?.length || 0), 0)}</li>
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                {/* Informace o vygenerovaných souborech */}
                {selectedProject.status === 'completed' && selectedProject.generated_files && (
                  <div className="mt-4">
                    <h3 className="text-sm font-semibold text-gray-700 mb-2">Vygenerované soubory:</h3>
                    <div className="p-3 bg-purple-50 rounded-lg">
                      <p className="text-sm text-purple-700 mb-2">
                        Úspěšně vygenerováno {selectedProject.generated_files.length} hlasových souborů:
                      </p>
                      <ul className="text-xs text-purple-600 space-y-1">
                        {selectedProject.generated_files.map((file, index) => (
                          <li key={index} className="flex items-center">
                            <span className="w-2 h-2 bg-purple-500 rounded-full mr-2"></span>
                            {file.filename}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
              </div>

              {/* Footer modalu */}
              <div className="p-6 border-t border-gray-200 bg-gray-50">
                <div className="flex justify-between items-center">
                  {/* Tlačítko smazat vlevo */}
                  <button
                    onClick={() => openDeleteConfirm(selectedProject)}
                    className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 transition-colors"
                  >
                    🗑️ Smazat projekt
                  </button>
                  
                  {/* Ostatní tlačítka vpravo */}
                  <div className="flex space-x-3">
                    {activeDetailTab === 'preview' && (
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(selectedProject.response);
                          setResult({ success: true, message: 'Obsah zkopírován do schránky!' });
                        }}
                        className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                      >
                        📋 Kopírovat text
                      </button>
                    )}
                    {activeDetailTab === 'json' && selectedProject.elevenlabs_json && (
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(JSON.stringify(selectedProject.elevenlabs_json, null, 2));
                          setResult({ success: true, message: 'JSON zkopírován do schránky!' });
                        }}
                        className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors"
                      >
                        🔧 Kopírovat JSON
                      </button>
                    )}
                    {/* Tlačítko pro odeslání do ElevenLabs - vždy viditelné když je projekt připravený */}
                    {selectedProject.elevenlabs_json && (selectedProject.status === 'ready' || selectedProject.status === 'completed') && (
                      <button
                        onClick={() => {
                          handleProjectConfirm(selectedProject);
                          closeProjectDetail();
                        }}
                        className="px-4 py-2 bg-orange-600 text-white rounded-md hover:bg-orange-700 transition-colors"
                      >
                        🎙️ Odeslat do ElevenLabs
                      </button>
                    )}
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
                    onChange={(e) => {
                      setNewAssistantName(e.target.value);
                      if (error) setError(''); // Vyčistí error při změně
                    }}
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
                    onChange={(e) => {
                      setNewAssistantId(e.target.value);
                      if (error) setError(''); // Vyčistí error při změně
                    }}
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

                {/* Chybová zpráva */}
                {error && (
                  <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
                    <p className="text-sm text-red-600">❌ {error}</p>
                  </div>
                )}

                {/* Úspěšná zpráva */}
                {result && result.success && (
                  <div className="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg">
                    <p className="text-sm text-green-600">✅ {result.message}</p>
                  </div>
                )}
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

        {/* Modal pro správu asistentů */}
        {showAssistantManagerModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-lg max-w-4xl w-full max-h-[90vh] overflow-y-auto">
              {/* Header modalu */}
              <div className="p-6 border-b border-gray-200">
                <div className="flex items-center justify-between">
                  <h2 className="text-xl font-semibold text-gray-900">
                    🤖 Správa OpenAI Asistentů
                  </h2>
                  <button
                    onClick={closeAssistantManagerModal}
                    className="text-gray-400 hover:text-gray-600 text-2xl font-bold"
                  >
                    ×
                  </button>
                </div>
                <p className="text-sm text-gray-600 mt-2">
                  Načítejte, skrývejte a spravujte své OpenAI asistenty
                </p>
              </div>

              {/* Obsah modalu - AssistantManager komponenta */}
              <div className="p-0">
                <AssistantManager 
                  onRefreshNeeded={refreshHiddenAssistants}
                  availableAssistants={availableAssistants}
                  setAvailableAssistants={setAvailableAssistants}
                  hiddenAssistants={hiddenAssistants}
                  setHiddenAssistants={setHiddenAssistants}
                  openaiApiKey={openaiApiKey}
                />
              </div>
            </div>
          </div>
        )}

        {/* Modal pro potvrzení smazání projektu */}
        {showDeleteConfirm && projectToDelete && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-lg max-w-md w-full">
              {/* Header modalu */}
              <div className="p-6 border-b border-gray-200">
                <div className="flex items-center justify-between">
                  <h2 className="text-xl font-semibold text-gray-900">
                    ⚠️ Potvrdit smazání
                  </h2>
                  <button
                    onClick={closeDeleteConfirm}
                    className="text-gray-400 hover:text-gray-600 text-2xl font-bold"
                  >
                    ×
                  </button>
                </div>
              </div>

              {/* Obsah modalu */}
              <div className="p-6">
                <div className="mb-4">
                  <p className="text-gray-700 mb-2">
                    Opravdu chcete smazat tento projekt?
                  </p>
                  <div className="p-3 bg-gray-50 rounded-lg">
                    <p className="font-medium text-gray-900">
                      {projectToDelete.title}
                    </p>
                    <p className="text-sm text-gray-600 mt-1">
                      {projectToDelete.character_count.toLocaleString()} znaků • {' '}
                      {new Date(projectToDelete.created_at).toLocaleDateString('cs-CZ')}
                    </p>
                  </div>
                </div>
                
                <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                  <p className="text-sm text-red-700">
                    <strong>Pozor:</strong> Tato akce je nevratná. Projekt bude trvale smazán a nebude možné jej obnovit.
                  </p>
                </div>
              </div>

              {/* Footer modalu */}
              <div className="p-6 border-t border-gray-200 bg-gray-50">
                <div className="flex justify-end space-x-3">
                  <button
                    onClick={closeDeleteConfirm}
                    className="px-4 py-2 bg-gray-300 text-gray-700 rounded-md hover:bg-gray-400 transition-colors"
                  >
                    Zrušit
                  </button>
                  <button
                    onClick={handleDeleteProject}
                    className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 transition-colors"
                  >
                    🗑️ Smazat projekt
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
                
                <div className="bg-green-50 border border-green-200 rounded-md p-3 mb-4">
                  <p className="text-sm text-green-800">
                    ✅ <strong>Automatické ukládání:</strong> Všechna data (API klíče, asistenti, projekty, fronty) se automaticky ukládají do localStorage a přežijí restarty prohlížeče!
                  </p>
                </div>
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
                  
                  <div className="mt-4 pt-4 border-t border-gray-200">
                    <h4 className="text-lg font-semibold text-gray-900 mb-3">🗂️ Backup dat</h4>
                    <div className="flex flex-col space-y-2">
                      <button
                        onClick={exportAllData}
                        className="w-full px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors"
                      >
                        📤 Exportovat všechna data
                      </button>
                      
                      <div className="flex items-center">
                        <input
                          type="file"
                          accept=".json"
                          onChange={importAllData}
                          id="import-data"
                          className="hidden"
                        />
                        <label
                          htmlFor="import-data"
                          className="w-full px-4 py-2 bg-orange-600 text-white rounded-md hover:bg-orange-700 transition-colors cursor-pointer text-center"
                        >
                          📥 Importovat data
                        </label>
                      </div>
                      
                      <p className="text-xs text-gray-600 mt-2">
                        💡 Tip: Exportujte data před restartem pro jistotu!
                      </p>
                    </div>
                  </div>
                  

              </div>
            </div>
          </div>
        )}



        {/* Voice Generator Card */}
        <div className="bg-white rounded-lg shadow-sm mb-6">
          <VoiceGenerator 
            onVoicesGenerated={handleVoicesGenerated}
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
              className="w-full py-4 px-6 rounded-lg font-medium text-white text-lg bg-primary-600 hover:bg-primary-700 transition-colors"
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

      {/* YouTube modal */}
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

      {/* Modal pro video konfiguraci */}
      {showVideoConfigModal && videoConfigItem && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            {/* Header modalu */}
            <div className="p-6 border-b border-gray-200">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-semibold text-gray-900 mb-2">
                    🎬 Konfigurace videa
                  </h2>
                  <p className="text-sm text-gray-600">
                    {videoConfigItem.project.title}
                  </p>
                </div>
                <button
                  onClick={closeVideoConfig}
                  className="text-gray-400 hover:text-gray-600 text-2xl font-bold"
                >
                  ×
                </button>
              </div>
            </div>

            {/* Obsah modalu */}
            <div className="p-6 space-y-6">
              {/* Základní nastavení */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Rozlišení a FPS */}
                <div>
                  <h3 className="text-sm font-semibold text-gray-700 mb-3">📐 Rozlišení a kvalita</h3>
                  <div className="space-y-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Rozlišení</label>
                      <select 
                        value={videoConfigItem.video_config.resolution}
                        onChange={(e) => {
                          const updatedItem = {
                            ...videoConfigItem,
                            video_config: {
                              ...videoConfigItem.video_config,
                              resolution: e.target.value
                            }
                          };
                          setVideoConfigItem(updatedItem);
                        }}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                      >
                        <option value="1920x1080">1920x1080 (Full HD)</option>
                        <option value="1280x720">1280x720 (HD)</option>
                        <option value="1080x1920">1080x1920 (TikTok)</option>
                        <option value="1080x1080">1080x1080 (Instagram)</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">FPS</label>
                      <select 
                        value={videoConfigItem.video_config.fps}
                        onChange={(e) => {
                          const updatedItem = {
                            ...videoConfigItem,
                            video_config: {
                              ...videoConfigItem.video_config,
                              fps: parseInt(e.target.value)
                            }
                          };
                          setVideoConfigItem(updatedItem);
                        }}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                      >
                        <option value={24}>24 FPS</option>
                        <option value={30}>30 FPS</option>
                        <option value={60}>60 FPS</option>
                      </select>
                    </div>
                  </div>
                </div>

                {/* Pozadí */}
                <div>
                  <h3 className="text-sm font-semibold text-gray-700 mb-3">🖼️ Pozadí</h3>
                  <div className="space-y-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Typ pozadí</label>
                      <select 
                        value={videoConfigItem.video_config.background_type}
                        onChange={(e) => {
                          const updatedItem = {
                            ...videoConfigItem,
                            video_config: {
                              ...videoConfigItem.video_config,
                              background_type: e.target.value
                            }
                          };
                          setVideoConfigItem(updatedItem);
                        }}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                      >
                        <option value="image">Statický obrázek</option>
                        <option value="video">Video smyčka</option>
                        <option value="gradient">Barevný gradient</option>
                        <option value="solid">Jednolitá barva</option>
                      </select>
                    </div>
                    <div className="p-3 bg-gray-50 rounded-lg">
                      <p className="text-xs text-gray-600">
                        💡 Tip: Video pozadí zvyšuje velikost souboru, ale vypadá dynamičtěji
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Titulky a styl */}
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-3">📝 Titulky a text</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="flex items-center">
                    <input
                      type="checkbox"
                      checked={videoConfigItem.video_config.show_subtitles}
                      onChange={(e) => {
                        const updatedItem = {
                          ...videoConfigItem,
                          video_config: {
                            ...videoConfigItem.video_config,
                            show_subtitles: e.target.checked
                          }
                        };
                        setVideoConfigItem(updatedItem);
                      }}
                      className="mr-2 h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                    />
                    <label className="text-sm text-gray-700">Zobrazit titulky</label>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Styl avatarů</label>
                    <select 
                      value={videoConfigItem.video_config.avatar_style}
                      onChange={(e) => {
                        const updatedItem = {
                          ...videoConfigItem,
                          video_config: {
                            ...videoConfigItem.video_config,
                            avatar_style: e.target.value
                          }
                        };
                        setVideoConfigItem(updatedItem);
                      }}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                    >
                      <option value="static">Statické obrázky</option>
                      <option value="animated">Animované přechody</option>
                      <option value="speaking">Vizualizace mluvení</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Náhled konfigurace */}
              <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <h4 className="text-sm font-semibold text-blue-800 mb-2">📊 Souhrn konfigurace</h4>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <div>
                    <span className="text-blue-600 font-medium">Rozlišení:</span>
                    <br />
                    <span className="text-blue-800">{videoConfigItem.video_config.resolution}</span>
                  </div>
                  <div>
                    <span className="text-blue-600 font-medium">FPS:</span>
                    <br />
                    <span className="text-blue-800">{videoConfigItem.video_config.fps}</span>
                  </div>
                  <div>
                    <span className="text-blue-600 font-medium">Pozadí:</span>
                    <br />
                    <span className="text-blue-800">{videoConfigItem.video_config.background_type}</span>
                  </div>
                  <div>
                    <span className="text-blue-600 font-medium">Titulky:</span>
                    <br />
                    <span className="text-blue-800">{videoConfigItem.video_config.show_subtitles ? 'Ano' : 'Ne'}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer modalu */}
            <div className="p-6 border-t border-gray-200 bg-gray-50">
              <div className="flex justify-end space-x-3">
                <button
                  onClick={closeVideoConfig}
                  className="px-4 py-2 bg-gray-300 text-gray-700 rounded-md hover:bg-gray-400 transition-colors"
                >
                  Zrušit
                </button>
                <button
                  onClick={() => saveVideoConfig(videoConfigItem.video_config)}
                  className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors font-medium"
                >
                  💾 Uložit konfiguraci
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

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