import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toDisplayString } from '../utils/display';

// Nastavím axios base URL na backend port
const api = axios.create({
  baseURL: 'http://localhost:50000'
});

const VideoGenerationSimple = ({ onClose }) => {
  const [activeTab, setActiveTab] = useState('images'); // images, image-selection, kenburns, preview, video, results
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [openaiConfigured, setOpenaiConfigured] = useState(false);
  
  // Image generování stavy
  const [selectedProject, setSelectedProject] = useState('');
  const [projectData, setProjectData] = useState(null);
  const [isGeneratingImages, setIsGeneratingImages] = useState(false);
  const [generatedImages, setGeneratedImages] = useState(null);
  const [hasExistingImages, setHasExistingImages] = useState(false);
  const [forceRegenerate, setForceRegenerate] = useState(false);
  const [customImageCount, setCustomImageCount] = useState('');
  const [useCustomCount, setUseCustomCount] = useState(false);
  
  // NOVÉ: Výběr obrázků stavy
  const [availableImages, setAvailableImages] = useState([]);
  const [selectedImages, setSelectedImages] = useState([]);
  const [isLoadingAllImages, setIsLoadingAllImages] = useState(false);
  const [showImageSelection, setShowImageSelection] = useState(false);
  const [imageFilter, setImageFilter] = useState('all'); // all, current-project, other-projects
  
  // NOVÉ: Ken Burns efekty stavy
  const [kenBurnsSettings, setKenBurnsSettings] = useState({});
  const [globalEffect, setGlobalEffect] = useState('zoom_in');
  
  // NOVÉ: Ken Burns náhledy stavy
  const [previews, setPreviews] = useState(null);
  const [isGeneratingPreviews, setIsGeneratingPreviews] = useState(false);
  const [previewSettings, setPreviewSettings] = useState({
    duration: 4.0,
    width: 1280,
    height: 720
  });
  
  // Video generování stavy
  const [isGeneratingVideo, setIsGeneratingVideo] = useState(false);
  const [generatingVideoType, setGeneratingVideoType] = useState(null); // null, 'simple', 'fast-kenburns', 'kenburns'
  const [generatedVideo, setGeneratedVideo] = useState(null);
  const [videoSettings, setVideoSettings] = useState({
    width: 1920,
    height: 1080,
    fps: 30
  });
  
  // Načítání projektů z localStorage
  const [availableProjects, setAvailableProjects] = useState([]);

  useEffect(() => {
    loadAvailableProjects();
  }, []);

  useEffect(() => {
    const loadStatus = async () => {
      try {
        const res = await api.get('/api/settings/openai_status', { timeout: 20000 });
        if (res.data?.success) {
          setOpenaiConfigured(!!res.data.configured);
        }
      } catch (e) {
        setOpenaiConfigured(false);
      }
    };
    loadStatus();
  }, []);

  // Vytvořit výchozí Ken Burns nastavení při načtení obrázků
  useEffect(() => {
    if (generatedImages && generatedImages.images) {
      const defaultSettings = {};
      generatedImages.images.forEach((img, index) => {
        // Inteligentní výchozí nastavení podle pozice
        let defaultEffect = 'zoom_in';
        const totalImages = generatedImages.images.length;
        const position = index / Math.max(totalImages - 1, 1);
        
        if (position <= 0.2) {
          defaultEffect = 'zoom_in'; // Začátek - přiblížení
        } else if (position <= 0.8) {
          defaultEffect = index % 2 === 0 ? 'pan_left' : 'pan_right'; // Střed - střídání
        } else {
          defaultEffect = 'zoom_out'; // Konec - oddálení
        }
        
        defaultSettings[img.filename] = {
          effect: defaultEffect,
          effectName: getEffectName(defaultEffect)
        };
      });
      setKenBurnsSettings(defaultSettings);
    }
  }, [generatedImages]);

  const getEffectName = (effect) => {
    const effects = {
      'zoom_in': '🔍 Zoom In (přiblížení)',
      'zoom_out': '🔎 Zoom Out (oddálení)',
      'pan_left': '⬅️ Pan Left (posun zleva)',
      'pan_right': '➡️ Pan Right (posun zprava)'
    };
    return effects[effect] || effect;
  };

  const loadAvailableProjects = () => {
    try {
      const projects = JSON.parse(localStorage.getItem('simpleTasks') || '[]');
      const completedProjects = projects.filter(p => p.status === 'completed' && p.result);
      setAvailableProjects(completedProjects);
    } catch (err) {
      console.error('Chyba při načítání projektů:', err);
    }
  };

  const handleProjectSelect = async (projectId) => {
    const project = availableProjects.find(p => p.id === parseInt(projectId));
    if (project && project.result) {
      setSelectedProject(projectId);
      setProjectData(project.result);
      setError('');
      setSuccess('');
      
      // Zkontroluj, jestli už existují obrázky pro tento projekt
      const projectName = project.result.topic?.replace(/[^a-zA-Z0-9]/g, '_') || 'video_project';
      try {
        const response = await api.head(`/api/images/${projectName}_metadata.json`);
        if (response.status === 200) {
          setHasExistingImages(true);
          setSuccess('📁 Pro tento projekt už existují vygenerované obrázky. Můžete je znovu použít nebo vygenerovat nové.');
        }
      } catch (err) {
        // Metadata soubor neexistuje = žádné existující obrázky
        setHasExistingImages(false);
      }
    }
  };

  const generateImages = async () => {
    if (!projectData || !openaiConfigured) {
      setError('Vyberte projekt a ujistěte se, že je OpenAI API klíč nastaven na serveru');
      return;
    }

    setIsGeneratingImages(true);
    setError('');
    setSuccess('');

    try {
      // Získání text bloků z projektu
      let textBlocks = projectData?.jsonBlocks;
      if (!textBlocks && projectData?.segments && projectData.segments.length > 0 && projectData.segments[0].content) {
        textBlocks = projectData.segments[0].content;
      }

      if (!textBlocks || Object.keys(textBlocks).length === 0) {
        throw new Error('Projekt neobsahuje žádné text bloky');
      }

      // Přidat custom počet obrázků pokud je nastaven
      const requestData = {
        project_name: 'video_project',
        json_blocks: textBlocks,
        force_regenerate: forceRegenerate
      };

      // Pokud uživatel zadal vlastní počet obrázků, přidej ho
      if (useCustomCount && customImageCount && parseInt(customImageCount) > 0) {
        requestData.custom_image_count = parseInt(customImageCount);
      }

      const response = await api.post('/api/generate-images', requestData);

      if (response.data.success) {
        if (response.data.from_cache && !forceRegenerate) {
          // Načtené existující obrázky - zobraz možnost výběru
          setGeneratedImages(response.data.data);
          loadAllAvailableImages(); // Načti všechny dostupné obrázky pro výběr
        } else {
          // Nově vygenerované obrázky - pokračuj rovnou na Ken Burns
          setGeneratedImages(response.data.data);
          setSuccess(`✅ Úspěšně vygenerováno ${response.data.data.total_images} obrázků`);
          setActiveTab('kenburns'); // Automaticky přejít na Ken Burns tab
        }
      } else {
        setError(response.data.error);
      }
    } catch (err) {
      setError(err.response?.data?.error || err.message);
    } finally {
      setIsGeneratingImages(false);
    }
  };

  const loadAllAvailableImages = async () => {
    setIsLoadingAllImages(true);
    try {
      const response = await api.get('/api/list-all-images');
      if (response.data.success) {
        setAvailableImages(response.data.images);
        setShowImageSelection(true);
        setActiveTab('image-selection');
        setSuccess(`📁 Nalezeno ${response.data.total_images} obrázků z ${response.data.total_projects} projektů. Vyberte které chcete použít.`);
      } else {
        setError('Chyba při načítání seznamu obrázků');
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Chyba při načítání seznamu obrázků');
    } finally {
      setIsLoadingAllImages(false);
    }
  };

  const handleImageSelection = (image, isSelected) => {
    if (isSelected) {
      setSelectedImages(prev => [...prev, image]);
    } else {
      setSelectedImages(prev => prev.filter(img => img.filename !== image.filename));
    }
  };

  const handleSelectAllImages = (projectName) => {
    if (projectName === 'all') {
      const filtered = getFilteredImages();
      setSelectedImages(filtered);
    } else {
      const projectImages = availableImages.filter(img => img.project_name === projectName);
      setSelectedImages(prev => {
        const withoutProject = prev.filter(img => img.project_name !== projectName);
        return [...withoutProject, ...projectImages];
      });
    }
  };

  const handleUnselectAllImages = (projectName) => {
    if (projectName === 'all') {
      setSelectedImages([]);
    } else {
      setSelectedImages(prev => prev.filter(img => img.project_name !== projectName));
    }
  };

  const proceedWithSelectedImages = () => {
    if (selectedImages.length === 0) {
      setError('Vyberte alespoň jeden obrázek');
      return;
    }

    // Vytvoř data structure kompatibilní s existujícím kódem
    const imageData = {
      images: selectedImages.map((img, index) => ({
        filename: img.filename,
        group_number: index + 1,
        blocks_count: img.blocks_count || 1,
        original_prompt: img.original_prompt || '',
        project_name: img.project_name
      })),
      total_images: selectedImages.length,
      project_name: 'selected_images'
    };

    setGeneratedImages(imageData);
    setShowImageSelection(false);
    setActiveTab('kenburns');
    setSuccess(`✅ Vybráno ${selectedImages.length} obrázků pro video`);
  };

  const getFilteredImages = () => {
    switch (imageFilter) {
      case 'current-project':
        return availableImages.filter(img => img.project_name === 'video_project');
      case 'other-projects':
        return availableImages.filter(img => img.project_name !== 'video_project' && img.project_name !== 'unknown');
      default:
        return availableImages;
    }
  };

  const getProjectGroups = () => {
    const filtered = getFilteredImages();
    const groups = {};
    
    filtered.forEach(img => {
      const projectName = img.project_name || 'unknown';
      if (!groups[projectName]) {
        groups[projectName] = [];
      }
      groups[projectName].push(img);
    });
    
    return groups;
  };

  const updateKenBurnsEffect = (filename, effect) => {
    setKenBurnsSettings(prev => ({
      ...prev,
      [filename]: {
        effect: effect,
        effectName: getEffectName(effect)
      }
    }));
  };

  const applyEffectToAll = () => {
    if (!generatedImages?.images) return;
    
    const newSettings = {};
    generatedImages.images.forEach(img => {
      // Vytvořím SEKVENCI všech 4 efektů pro každý obrázek
      newSettings[img.filename] = {
        effectSequence: ['zoom_in', 'zoom_out', 'pan_left', 'pan_right'],
        effectNames: ['🔍 Zoom In', '🔍 Zoom Out', '⬅️ Pan Left', '➡️ Pan Right']
      };
    });
    setKenBurnsSettings(newSettings);
    setSuccess('✅ Sekvence 4 efektů aplikována na všechny obrázky!');
  };

  const generatePreview = async () => {
    if (!generatedImages || !kenBurnsSettings) {
      setError('Nejdříve vygenerujte obrázky a nastavte Ken Burns efekty');
      return;
    }

    setIsGeneratingPreviews(true);
    setError('');
    setSuccess('');
    setPreviews(null);

    try {
      // Přidat Ken Burns sekvence k obrázkovým datům
      const imagesWithEffects = generatedImages.images.map(img => ({
        ...img,
        // OPRAVENO: Neposíláme local_path, backend použije filename
        kenBurnsSequence: kenBurnsSettings[img.filename]?.effectSequence || ['zoom_in', 'zoom_out', 'pan_left', 'pan_right']
      }));

      console.log('🎨 Odesílám request pro náhled:', {
        images: imagesWithEffects,
        preview_settings: previewSettings
      });

      const response = await api.post('/api/preview-ken-burns', {
        images: imagesWithEffects,
        preview_settings: previewSettings
      });

      if (response.data.success) {
        setPreviews(response.data);
        setSuccess(`✅ Náhledy úspěšně vygenerovány! (${response.data.total_previews} náhledů, ${response.data.successful_clips} úspěšných klipů)`);
        console.log('🎨 Náhledy obdrženy:', response.data);
      } else {
        setError(response.data.error);
      }
    } catch (err) {
      console.error('❌ Chyba při generování náhledů:', err);
      setError(err.response?.data?.error || err.message);
    } finally {
      setIsGeneratingPreviews(false);
    }
  };

  // ⚡ NOVÁ FUNKCE: Rychlý náhled Ken Burns efektů
  const generateFastPreview = async () => {
    if (!generatedImages || !kenBurnsSettings) {
      setError('Nejdříve vygenerujte obrázky a nastavte Ken Burns efekty');
      return;
    }

    setIsGeneratingPreviews(true);
    setError('');
    setSuccess('');
    setPreviews(null);

    try {
      // Přidat Ken Burns sekvence k obrázkovým datům
      const imagesWithEffects = generatedImages.images.map(img => ({
        ...img,
        kenBurnsSequence: kenBurnsSettings[img.filename]?.effectSequence || ['zoom_in', 'zoom_out', 'pan_left', 'pan_right']
      }));

      console.log('⚡ Odesílám request pro rychlý náhled:', {
        images: imagesWithEffects,
        preview_settings: {
          ...previewSettings,
          duration: 2.0,  // Kratší náhled
          width: 720,     // Menší rozlišení
          height: 480
        }
      });

      const response = await api.post('/api/fast-preview-ken-burns', {
        images: imagesWithEffects,
        preview_settings: {
          ...previewSettings,
          duration: 2.0,
          width: 720,
          height: 480
        }
      });

      if (response.data.success) {
        setPreviews(response.data);
        setSuccess(`✅ Rychlý náhled úspěšně vygenerován! (${response.data.note})`);
        console.log('⚡ Rychlý náhled obdržen:', response.data);
      } else {
        setError(response.data.error);
      }
    } catch (err) {
      console.error('❌ Chyba při generování rychlého náhledu:', err);
      setError(err.response?.data?.error || err.message);
    } finally {
      setIsGeneratingPreviews(false);
    }
  };

  const generateVideo = async () => {
    if (!generatedImages || !kenBurnsSettings) {
      setError('Nejdříve vygenerujte obrázky a nastavte Ken Burns efekty');
      return;
    }

    setIsGeneratingVideo(true);
    setGeneratingVideoType('kenburns');
    setError('');
    setSuccess('');

    try {
      // Získání audio souborů
      let textBlocks = projectData?.jsonBlocks;
      if (!textBlocks && projectData?.segments && projectData.segments.length > 0 && projectData.segments[0].content) {
        textBlocks = projectData.segments[0].content;
      }

      if (!textBlocks || Object.keys(textBlocks).length === 0) {
        throw new Error('Žádné audio bloky nenalezeny v projektu');
      }

      const audioFiles = Object.keys(textBlocks).map(key => `${key}.mp3`);

      // Přidat Ken Burns sekvence k obrázkovým datům
      const imagesWithEffects = generatedImages.images.map(img => ({
        ...img,
        // OPRAVENO: Neposíláme local_path, backend použije filename
        kenBurnsSequence: kenBurnsSettings[img.filename]?.effectSequence || ['zoom_in', 'zoom_out', 'pan_left', 'pan_right']
      }));

      const response = await api.post('/api/generate-video-kenburns-with-audio', {
        project_name: generatedImages.project_name,
        images: imagesWithEffects,
        video_settings: videoSettings,
        max_mp3_files: 0  // 0 = použij VŠECHNY MP3 soubory (105 souborů)
      });

      if (response.data.success) {
        setGeneratedVideo({
          filename: response.data.filename,
          download_url: response.data.download_url,
          file_size: response.data.file_size,
          duration: response.data.duration,
          audio_duration: response.data.audio_duration,
          total_mp3_files: response.data.total_mp3_files,
          duration_per_image: response.data.duration_per_image,
          successful_clips: response.data.successful_clips
        });
        setSuccess(`✅ Ken Burns video s audio úspěšně vygenerováno! 
                   🎭 Efekty: Zoom, Pan a další animace 
                   🎵 Audio: ${response.data.audio_duration?.toFixed(1)}s 
                   📁 MP3 souborů: ${response.data.total_mp3_files}`);
        setActiveTab('results');
      } else {
        setError(response.data.error);
      }
    } catch (err) {
      setError(err.response?.data?.error || err.message);
    } finally {
      setIsGeneratingVideo(false);
      setGeneratingVideoType(null);
    }
  };

  // 🎬 NOVÁ FUNKCE: Rychlé video s audio (bez pomalých Ken Burns efektů)
  const generateVideoWithAudio = async () => {
    if (!generatedImages) {
      setError('Nejdříve vygenerujte obrázky');
      return;
    }

    setIsGeneratingVideo(true);
    setGeneratingVideoType('simple');
    setError('');
    setSuccess('');

    try {
      console.log('🎬 Spouštím rychlé video s audio...');

      const response = await api.post('/api/generate-video-with-audio', {
        project_name: generatedImages.project_name,
        images: generatedImages.images, // Jednoduché obrázky bez Ken Burns
        video_settings: videoSettings,
        max_mp3_files: 0  // 0 = použij VŠECHNY MP3 soubory (105 souborů)
      });

      console.log('🎬 Odpověď z backendu:', response.data);

      if (response.data.success) {
        setGeneratedVideo({
          filename: response.data.filename,
          download_url: response.data.download_url,
          file_size: response.data.file_size,
          duration: response.data.duration,
          audio_duration: response.data.audio_duration,
          total_mp3_files: response.data.total_mp3_files,
          duration_per_image: response.data.duration_per_image,
          successful_clips: response.data.successful_clips
        });
        setSuccess(`✅ Rychlé video s audio úspěšně vygenerováno! 
                   🎵 Audio: ${response.data.audio_duration?.toFixed(1)}s 
                   🎬 Video: ${response.data.duration?.toFixed(1)}s 
                   📁 MP3 souborů: ${response.data.total_mp3_files}`);
        setActiveTab('results');
      } else {
        setError(response.data.error);
      }
    } catch (err) {
      console.error('❌ Chyba při generování rychlého videa:', err);
      setError(err.response?.data?.error || err.message);
    } finally {
      setIsGeneratingVideo(false);
      setGeneratingVideoType(null);
    }
  };

  // ⚡ NOVÁ FUNKCE: Rychlé Ken Burns video s audio (kompromis mezi rychlostí a efekty)
  const generateFastKenBurnsVideoWithAudio = async () => {
    if (!generatedImages) {
      setError('Nejdříve vygenerujte obrázky');
      return;
    }

    setIsGeneratingVideo(true);
    setGeneratingVideoType('fast-kenburns');
    setError('');
    setSuccess('');

    try {
      console.log('⚡ Spouštím rychlé Ken Burns video s audio...');

      // Přidar Ken Burns sekvence k obrázkovým datům - VŽDY STŘÍDEJ EFEKTY!
      const imagesWithEffects = generatedImages.images.map((img, index) => {
        // VŽDY používej střídání efektů - ignoruj uložená nastavení pro rychlé video
        const defaultEffects = ['zoom_in', 'zoom_out', 'pan_left', 'pan_right'];
        const effectSequence = [defaultEffects[index % defaultEffects.length]];
        console.log(`📸 ${img.filename}: Použiju střídající efekt ${effectSequence[0]} (pozice ${index})`);
        
        return {
          ...img,
          kenBurnsSequence: effectSequence
        };
      });

      const response = await api.post('/api/generate-video-fast-kenburns-with-audio', {
        project_name: generatedImages.project_name,
        images: imagesWithEffects,
        video_settings: videoSettings,
        max_mp3_files: 0  // 0 = použij VŠECHNY MP3 soubory (105 souborů)
      }, { 
        timeout: 1800000 // 30 minut timeout pro dlouhé video generování
      });

      console.log('⚡ Odpověď z backendu:', response.data);

      if (response.data.success) {
        setGeneratedVideo({
          filename: response.data.filename,
          download_url: response.data.download_url,
          file_size: response.data.file_size,
          duration: response.data.duration,
          audio_duration: response.data.audio_duration,
          total_mp3_files: response.data.total_mp3_files,
          duration_per_image: response.data.duration_per_image,
          successful_clips: response.data.successful_clips
        });
        setSuccess(`✅ Rychlé Ken Burns video s audio úspěšně vygenerováno! 
                   ⚡ Rychlé efekty: Zoom, Pan animace 
                   🎵 Audio: ${response.data.audio_duration?.toFixed(1)}s 
                   📁 MP3 souborů: ${response.data.total_mp3_files}`);
        setActiveTab('results');
      } else {
        setError(response.data.error);
      }
    } catch (err) {
      console.error('❌ Chyba při generování rychlého Ken Burns videa:', err);
      setError(err.response?.data?.error || err.message);
    } finally {
      setIsGeneratingVideo(false);
      setGeneratingVideoType(null);
    }
  };

  const downloadVideo = async () => {
    if (!generatedVideo) return;
    
    try {
      const response = await api.get(`/api/download/${generatedVideo.filename}`, {
        responseType: 'blob'
      });
      
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', generatedVideo.filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      console.error('Chyba při stahování videa:', err);
      setError('Nepodařilo se stáhnout video');
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 w-full max-w-4xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold text-gray-800">
            🎬 Video Generation Studio
          </h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 text-2xl"
          >
            ✕
          </button>
        </div>

        {/* Tab navigation */}
        <div className="flex space-x-1 bg-gray-100 p-1 rounded-lg mb-6">
          <button
            onClick={() => setActiveTab('images')}
            className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'images'
                ? 'bg-white text-blue-600 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            📸 1. Generovat obrázky
          </button>
          
          <button
            onClick={() => setActiveTab('image-selection')}
            disabled={!showImageSelection}
            className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'image-selection'
                ? 'bg-white text-blue-600 shadow-sm'
                : showImageSelection 
                  ? 'text-gray-500 hover:text-gray-700'
                  : 'text-gray-300 cursor-not-allowed'
            }`}
          >
            🎯 2. Výběr obrázků
          </button>
          
          <button
            onClick={() => setActiveTab('kenburns')}
            disabled={!generatedImages}
            className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'kenburns'
                ? 'bg-white text-blue-600 shadow-sm'
                : generatedImages 
                  ? 'text-gray-500 hover:text-gray-700'
                  : 'text-gray-300 cursor-not-allowed'
            }`}
          >
            🎭 3. Ken Burns efekty
          </button>
          
          <button
            onClick={() => setActiveTab('preview')}
            disabled={!generatedImages}
            className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'preview'
                ? 'bg-white text-blue-600 shadow-sm'
                : generatedImages 
                  ? 'text-gray-500 hover:text-gray-700'
                  : 'text-gray-300 cursor-not-allowed'
            }`}
          >
            🎨 4. Náhled Ken Burns
          </button>
          
          <button
            onClick={() => setActiveTab('video')}
            disabled={!generatedImages}
            className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'video'
                ? 'bg-white text-blue-600 shadow-sm'
                : generatedImages 
                  ? 'text-gray-500 hover:text-gray-700'
                  : 'text-gray-300 cursor-not-allowed'
            }`}
          >
            🎬 5. Sestavit video
          </button>
          
          <button
            onClick={() => setActiveTab('results')}
            disabled={!generatedVideo}
            className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'results'
                ? 'bg-white text-blue-600 shadow-sm'
                : generatedVideo 
                  ? 'text-gray-500 hover:text-gray-700'
                  : 'text-gray-300 cursor-not-allowed'
            }`}
          >
            🎉 6. Výsledek
          </button>
        </div>

        {/* Error/Success Messages */}
        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
            ❌ {toDisplayString(error)}
          </div>
        )}
        {success && (
          <div className="bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded mb-4">
            {success}
          </div>
        )}

        {/* Images Tab */}
        {activeTab === 'images' && (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-semibold text-gray-700 mb-4">
                📋 Vyberte dokončený projekt
              </h3>
              
              {availableProjects.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <div className="text-4xl mb-2">📂</div>
                  <p>Žádné dokončené projekty</p>
                  <p className="text-sm">Nejdříve vytvořte projekt s audio obsahem</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {availableProjects.map(project => (
                    <div 
                      key={project.id}
                      onClick={() => handleProjectSelect(project.id.toString())}
                      className={`p-4 border rounded-lg cursor-pointer transition-colors ${
                        selectedProject === project.id.toString()
                          ? 'border-blue-500 bg-blue-50'
                          : 'border-gray-300 hover:border-gray-400'
                      }`}
                    >
                      <h4 className="font-medium text-gray-800 mb-2">
                        {project.prompt}
                      </h4>
                      <div className="text-sm text-gray-600 space-y-1">
                        <div>📅 {new Date(project.createdAt).toLocaleDateString('cs-CZ')}</div>
                        <div>⏱️ {project.targetDuration} minut</div>
                        <div>🗣️ {project.assistantName}</div>
                        {project.result?.jsonBlocks && (
                          <div>📝 {Object.keys(project.result?.jsonBlocks || {}).length} audio bloků</div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {projectData && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <h4 className="font-semibold text-blue-800 mb-2">
                  📊 Vybraný projekt
                </h4>
                <div className="text-sm space-y-1">
                  <div><strong>Téma:</strong> {projectData.topic || projectData.title}</div>
                  {(() => {
                    // Bezpečný přístup k text blokům pro zobrazení
                    let textBlocks = projectData?.jsonBlocks;
                    if (!textBlocks && projectData?.segments && projectData.segments.length > 0 && projectData.segments[0].content) {
                      textBlocks = projectData.segments[0].content;
                    }
                    return textBlocks ? (
                      <div><strong>Audio bloky:</strong> {Object.keys(textBlocks).length}</div>
                    ) : null;
                  })()}
                  {(() => {
                    // Bezpečný přístup k text blokům pro ukázku
                    let textBlocks = projectData?.jsonBlocks;
                    if (!textBlocks && projectData?.segments && projectData.segments.length > 0 && projectData.segments[0].content) {
                      textBlocks = projectData.segments[0].content;
                    }
                    return textBlocks && Object.keys(textBlocks).length > 0 ? (
                      <div className="mt-2">
                        <strong>Ukázka bloků:</strong>
                        <ul className="ml-4 mt-1">
                          {Object.keys(textBlocks).slice(0, 3).map(key => (
                            <li key={key} className="text-xs text-gray-600">
                              • {key}: {textBlocks[key].text?.substring(0, 50)}...
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null;
                  })()}
                </div>
              </div>
            )}

            {/* API klíč status */}
            <div className={`border rounded-lg p-4 ${openaiConfigured ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
              <h4 className={`font-semibold mb-2 ${openaiConfigured ? 'text-green-800' : 'text-red-800'}`}>
                🔑 OpenAI API klíč
              </h4>
              <div className="text-sm">
                {openaiConfigured ? (
                  <div className="text-green-700">
                    ✅ <strong>Nastaven na serveru</strong>
                  </div>
                ) : (
                  <div className="text-red-700">
                    ❌ <strong>Není nastaven na serveru</strong>
                    <div className="text-xs mt-1">
                      Jděte do hlavní aplikace → "API Management" a uložte OpenAI API klíč (server-side)
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Custom image count setting */}
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
              <div className="flex items-center mb-3">
                <div className="mr-3">
                  <input
                    type="checkbox"
                    id="useCustomCount"
                    checked={useCustomCount}
                    onChange={(e) => setUseCustomCount(e.target.checked)}
                    className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                  />
                </div>
                <label htmlFor="useCustomCount" className="text-blue-800">
                  <strong>🎯 Vlastní počet obrázků</strong>
                  <div className="text-xs text-blue-700 mt-1">
                    Zaškrtněte pro ruční nastavení počtu obrázků místo automatického výpočtu
                  </div>
                </label>
              </div>
              
              {useCustomCount && (
                <div className="mt-3 flex items-center space-x-3">
                  <label className="text-sm font-medium text-blue-700">
                    Počet obrázků:
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="50"
                    value={customImageCount}
                    onChange={(e) => setCustomImageCount(e.target.value)}
                    placeholder="např. 10"
                    className="w-20 px-2 py-1 border border-blue-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                  <span className="text-xs text-blue-600">
                    (1-50 obrázků)
                  </span>
                </div>
              )}
            </div>

            {/* Force regenerate checkbox */}
            {hasExistingImages && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
                <div className="flex items-center">
                  <div className="mr-3">
                    <input
                      type="checkbox"
                      id="forceRegenerate"
                      checked={forceRegenerate}
                      onChange={(e) => setForceRegenerate(e.target.checked)}
                      className="w-4 h-4 text-amber-600 border-gray-300 rounded focus:ring-amber-500"
                    />
                  </div>
                  <label htmlFor="forceRegenerate" className="text-amber-800">
                    <strong>🔄 Force regenerace</strong>
                    <div className="text-xs text-amber-700 mt-1">
                      Zaškrtněte pro vygenerování nových obrázků místo použití existujících. 
                      <strong>Pozor:</strong> Stojí to peníze a čas!
                    </div>
                  </label>
                </div>
              </div>
            )}

            <button
              onClick={generateImages}
              disabled={isGeneratingImages || !projectData || !openaiConfigured}
              className="w-full bg-blue-500 text-white py-3 px-4 rounded hover:bg-blue-600 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
            >
              {isGeneratingImages ? '🔄 Generuji obrázky pomocí DALL·E...' : 
               hasExistingImages && !forceRegenerate ? '🎨 Vygenerovat nové obrázky (DALL·E 3)' :
               '🎨 Vygenerovat obrázky (DALL·E 3)'}
            </button>

            {/* Rychlé tlačítko pro přímý výběr obrázků */}
            <button
              onClick={loadAllAvailableImages}
              disabled={isLoadingAllImages}
              className="w-full mt-2 bg-purple-500 text-white py-2 px-4 rounded hover:bg-purple-600 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
            >
              {isLoadingAllImages ? '🔄 Načítám všechny obrázky...' : '🎯 Vybrat z všech dostupných obrázků'}
            </button>

            {isGeneratingImages && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <div className="flex items-center">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-2"></div>
                  <span className="text-blue-700">Generuji obrázky pomocí DALL·E 3... Toto může trvat několik minut.</span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Image Selection Tab */}
        {activeTab === 'image-selection' && (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-semibold text-gray-700 mb-4">
                🎯 Vyberte obrázky pro video
              </h3>
              <p className="text-sm text-gray-600 mb-4">
                Vyberte konkrétní obrázky, které chcete použít ve vašem videu. Můžete kombinovat obrázky z různých projektů.
              </p>

              {/* Filtrovací tlačítka */}
              <div className="flex space-x-2 mb-4">
                <button
                  onClick={() => setImageFilter('all')}
                  className={`px-3 py-1 text-sm rounded ${
                    imageFilter === 'all'
                      ? 'bg-blue-500 text-white'
                      : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                  }`}
                >
                  Všechny ({availableImages.length})
                </button>
                <button
                  onClick={() => setImageFilter('current-project')}
                  className={`px-3 py-1 text-sm rounded ${
                    imageFilter === 'current-project'
                      ? 'bg-blue-500 text-white'
                      : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                  }`}
                >
                  Aktuální projekt ({availableImages.filter(img => img.project_name === 'video_project').length})
                </button>
                <button
                  onClick={() => setImageFilter('other-projects')}
                  className={`px-3 py-1 text-sm rounded ${
                    imageFilter === 'other-projects'
                      ? 'bg-blue-500 text-white'
                      : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                  }`}
                >
                  Ostatní projekty ({availableImages.filter(img => img.project_name !== 'video_project' && img.project_name !== 'unknown').length})
                </button>
              </div>

              {/* Počet vybraných obrázků */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4">
                <div className="flex items-center justify-between">
                  <span className="text-blue-800 font-medium">
                    ✅ Vybráno: {selectedImages.length} obrázků
                  </span>
                  <div className="space-x-2">
                    <button
                      onClick={() => handleSelectAllImages('all')}
                      className="text-xs bg-blue-500 text-white px-2 py-1 rounded hover:bg-blue-600"
                    >
                      Vybrat vše
                    </button>
                    <button
                      onClick={() => handleUnselectAllImages('all')}
                      className="text-xs bg-gray-500 text-white px-2 py-1 rounded hover:bg-gray-600"
                    >
                      Zrušit vše
                    </button>
                  </div>
                </div>
              </div>

              {isLoadingAllImages ? (
                <div className="text-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-2"></div>
                  <p className="text-gray-600">Načítám všechny dostupné obrázky...</p>
                </div>
              ) : (
                <div className="space-y-6">
                  {Object.entries(getProjectGroups()).map(([projectName, projectImages]) => (
                    <div key={projectName} className="border border-gray-200 rounded-lg p-4">
                      <div className="flex items-center justify-between mb-3">
                        <h4 className="font-medium text-gray-800">
                          📁 {projectName === 'video_project' ? 'Aktuální projekt' : 
                              projectName === 'unknown' ? 'Neznámý projekt' : projectName}
                          <span className="text-sm text-gray-500 ml-2">({projectImages.length} obrázků)</span>
                        </h4>
                        <div className="space-x-2">
                          <button
                            onClick={() => handleSelectAllImages(projectName)}
                            className="text-xs bg-green-500 text-white px-2 py-1 rounded hover:bg-green-600"
                          >
                            Vybrat všechny
                          </button>
                          <button
                            onClick={() => handleUnselectAllImages(projectName)}
                            className="text-xs bg-red-500 text-white px-2 py-1 rounded hover:bg-red-600"
                          >
                            Zrušit všechny
                          </button>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                        {projectImages.map((image, index) => {
                          const isSelected = selectedImages.some(img => img.filename === image.filename);
                          return (
                            <div
                              key={index}
                              className={`relative border-2 rounded-lg p-2 transition-all ${
                                isSelected
                                  ? 'border-blue-500 bg-blue-50'
                                  : 'border-gray-200 hover:border-gray-300'
                              }`}
                            >
                              {/* Checkbox */}
                              <div className="absolute top-1 right-1 z-10">
                                <input
                                  type="checkbox"
                                  checked={isSelected}
                                  onChange={(e) => {
                                    e.stopPropagation();
                                    handleImageSelection(image, !isSelected);
                                  }}
                                  className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                                />
                              </div>

                              {/* Obrázek */}
                              <div 
                                className="aspect-video bg-gray-100 rounded mb-2 overflow-hidden cursor-pointer"
                                onClick={() => handleImageSelection(image, !isSelected)}
                              >
                                <img 
                                  src={image.path || `/api/images/${image.filename}`}
                                  alt={`Obrázek ${image.group_number || index + 1}`}
                                  className="w-full h-full object-cover hover:scale-105 transition-transform"
                                  onError={(e) => {
                                    e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIwIiBoZWlnaHQ9IjE4MCIgdmlld0JveD0iMCAwIDMyMCAxODAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIzMjAiIGhlaWdodD0iMTgwIiBmaWxsPSIjZjNmNGY2Ii8+Cjx0ZXh0IHg9IjE2MCIgeT0iOTAiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxNCIgZmlsbD0iIzY2NjY2NiIgdGV4dC1hbmNob3I9Im1pZGRsZSI+T2Jyw6F6ZWsgc2UgbmVuYcWNdGw8L3RleHQ+Cjwvc3ZnPg==';
                                  }}
                                />
                              </div>

                              {/* Informace o obrázku */}
                              <div className="text-xs">
                                <div className="font-medium text-gray-800">#{image.group_number || index + 1}</div>
                                <div className="text-gray-600">{image.blocks_count} bloků</div>
                                <div className="text-gray-500 truncate" title={image.filename}>
                                  {image.filename}
                                </div>
                                {image.original_prompt && (
                                  <div className="text-gray-400 truncate mt-1" title={image.original_prompt}>
                                    {image.original_prompt.substring(0, 50)}...
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Tlačítko pro pokračování */}
              <div className="flex justify-between items-center mt-6 pt-4 border-t">
                <button
                  onClick={() => setActiveTab('images')}
                  className="bg-gray-500 text-white py-2 px-4 rounded hover:bg-gray-600 transition-colors"
                >
                  ← Zpět na generování
                </button>
                
                <button
                  onClick={proceedWithSelectedImages}
                  disabled={selectedImages.length === 0}
                  className="bg-blue-500 text-white py-2 px-4 rounded hover:bg-blue-600 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
                >
                  Pokračovat s vybranými obrázky ({selectedImages.length}) →
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Ken Burns Tab */}
        {activeTab === 'kenburns' && (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-semibold text-gray-700 mb-4">
                🎭 Nastavení Ken Burns efektů
              </h3>
              
              <div className="grid grid-cols-2 gap-4 mb-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Globální efekt
                  </label>
                  <select
                    value={globalEffect}
                    onChange={(e) => setGlobalEffect(e.target.value)}
                    className="w-full border border-gray-300 rounded px-3 py-2"
                  >
                    <option value="zoom_in">🔍 Zoom In (přiblížení)</option>
                    <option value="zoom_out">🔎 Zoom Out (oddálení)</option>
                    <option value="pan_left">⬅️ Pan Left (pohyb vlevo)</option>
                    <option value="pan_right">➡️ Pan Right (pohyb vpravo)</option>
                  </select>
                </div>
                                 <div className="flex flex-col items-center space-y-3">
                   <button
                     onClick={applyEffectToAll}
                     disabled={!generatedImages}
                     className="px-4 py-2 bg-purple-500 text-white rounded hover:bg-purple-600 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
                   >
                     🚀 Aplikovat na všechny
                   </button>
                   
                   {/* NOVÉ: Rychlé video s audio - HLAVNÍ TLAČÍTKO */}
                   <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 w-full max-w-md">
                     <h4 className="font-semibold text-blue-800 mb-2 text-center">
                       ⚡ RYCHLÉ VIDEO S AUDIO
                     </h4>
                     <p className="text-sm text-blue-700 mb-3 text-center">
                       Přeskočit Ken Burns efekty a vytvořit video s MP3 soubory <strong>ihned!</strong>
                     </p>
                     <button
                       onClick={generateVideoWithAudio}
                       disabled={isGeneratingVideo || !generatedImages}
                       className="w-full bg-blue-500 text-white py-3 px-4 rounded hover:bg-blue-600 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed font-semibold text-lg"
                     >
                       {isGeneratingVideo ? (
                         <div className="flex items-center justify-center">
                           <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white mr-2"></div>
                           ⚡ Sestavuji rychlé video s audio... (Může trvat 2-15 minut)
                         </div>
                       ) : '🎵 SESTAVIT VIDEO S AUDIO 🚀'}
                     </button>
                     
                     {isGeneratingVideo && (
                       <div className="mt-3 bg-blue-100 border border-blue-300 rounded-lg p-3">
                         <div className="flex items-center text-blue-700">
                           <div className="animate-pulse rounded-full h-3 w-3 bg-blue-500 mr-2"></div>
                           <span className="font-medium">Probíhá generování videa s audio...</span>
                         </div>
                         <div className="text-sm text-blue-600 mt-1">
                           • Načítání MP3 souborů ✅<br/>
                           • Vytváření video klipů ⏳<br/>
                           • Spojování s audio ⏳<br/>
                           • Export finálního videa ⏳
                         </div>
                         <div className="text-xs text-blue-500 mt-2">
                           💡 Tip: Nechte tuto záložku otevřenou až do dokončení
                         </div>
                       </div>
                     )}
                   </div>
                 </div>
              </div>

              {generatedImages && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                  <h4 className="font-semibold text-green-800 mb-2">
                    ✅ Obrázky připraveny
                  </h4>
                  <div className="text-sm space-y-1">
                    <div><strong>Projekt:</strong> {generatedImages.project_name}</div>
                    <div><strong>Celkem obrázků:</strong> {generatedImages.total_images}</div>
                    <div><strong>Audio bloků:</strong> {generatedImages.total_blocks}</div>
                    <div><strong>Skupin:</strong> {generatedImages.grouped_blocks?.length || 'N/A'}</div>
                  </div>
                  
                  {/* Náhledy obrázků */}
                  <div className="mt-4">
                    <strong className="text-sm">📸 Náhledy obrázků:</strong>
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 mt-2">
                      {generatedImages.images.map((img, index) => (
                        <div key={index} className="bg-white rounded border p-2 shadow-sm">
                          <div className="aspect-video bg-gray-100 rounded mb-2 overflow-hidden">
                            <img 
                              src={`/api/images/${img.filename}`}
                              alt={`Obrázek ${img.group_number || index + 1}`}
                              className="w-full h-full object-cover hover:scale-105 transition-transform cursor-pointer"
                              onError={(e) => {
                                e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIwIiBoZWlnaHQ9IjE4MCIgdmlld0JveD0iMCAwIDMyMCAxODAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIzMjAiIGhlaWdodD0iMTgwIiBmaWxsPSIjZjNmNGY2Ii8+Cjx0ZXh0IHg9IjE2MCIgeT0iOTAiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxNCIgZmlsbD0iIzY2NjY2NiIgdGV4dC1hbmNob3I9Im1pZGRsZSI+T2Jyw6F6ZWsgc2UgbmVuYcWNdGw8L3RleHQ+Cjwvc3ZnPg==';
                              }}
                            />
                          </div>
                          <div className="text-xs">
                            <div className="font-medium text-gray-800">#{img.group_number || index + 1}</div>
                            <div className="text-gray-600">{img.blocks_count} bloků</div>
                            <div className="text-gray-500 truncate" title={img.filename}>
                              {img.filename}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              

              <div className="mt-4">
                <h4 className="font-semibold text-gray-700 mb-2">
                  🎬 Sekvence efektů pro každý obrázek
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {generatedImages?.images.map((img, index) => (
                    <div key={img.filename} className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                      <h5 className="font-medium text-blue-800 mb-2">
                        Obrázek {index + 1}
                      </h5>
                      <div className="text-sm space-y-1">
                        <div><strong>Soubor:</strong> {img.filename}</div>
                        <div><strong>Sekvence efektů:</strong></div>
                        {kenBurnsSettings[img.filename]?.effectSequence ? (
                          <div className="bg-white border border-blue-300 rounded p-2 mt-2">
                            <div className="text-xs font-semibold text-blue-700 mb-1">
                              🎭 4 efekty za sebou:
                            </div>
                            <div className="space-y-1">
                              {kenBurnsSettings[img.filename].effectNames.map((name, i) => (
                                <div key={i} className="text-xs flex items-center">
                                  <span className="w-6 h-6 bg-blue-100 rounded-full flex items-center justify-center text-blue-700 mr-2 font-bold">
                                    {i + 1}
                                  </span>
                                  {name}
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : (
                          <div className="text-xs text-gray-500 italic">
                            Klikněte na "🚀 Aplikovat na všechny" pro vytvoření sekvence efektů
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Tlačítko pro pokračování na náhled */}
              <div className="flex justify-between items-center mt-6 pt-4 border-t">
                <button
                  onClick={() => setActiveTab('image-selection')}
                  className="bg-gray-500 text-white py-2 px-4 rounded hover:bg-gray-600 transition-colors"
                >
                  ← Zpět na výběr obrázků
                </button>
                
                <button
                  onClick={() => setActiveTab('preview')}
                  disabled={!generatedImages || !kenBurnsSettings || Object.keys(kenBurnsSettings).length === 0}
                  className="bg-blue-500 text-white py-2 px-4 rounded hover:bg-blue-600 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
                >
                  🎨 Pokračovat na náhled Ken Burns →
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Preview Tab */}
        {activeTab === 'preview' && (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-semibold text-gray-700 mb-4">
                🎨 Náhled Ken Burns efektů
              </h3>
              
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-4">
                <div className="flex items-start">
                  <div className="text-yellow-600 mr-2">⚠️</div>
                  <div>
                    <h4 className="font-semibold text-yellow-800 mb-1">Pozor: Náhled je pomalý!</h4>
                    <p className="text-sm text-yellow-700">
                      Náhled používá stejné pomalé Ken Burns efekty jako finální video a může trvat stejně dlouho. 
                      <strong>Doporučujeme přeskočit náhled</strong> a použít rychlé Ken Burns efekty přímo.
                    </p>
                  </div>
                </div>
              </div>
              
              <p className="text-sm text-gray-600 mb-4">
                Zobrazí náhled videa s aplikovanými Ken Burns efekty. Můžete upravit nastavení pro náhled.
              </p>

              <div className="grid grid-cols-3 gap-4 mb-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Délka náhledu (sekundy)
                  </label>
                  <input
                    type="number"
                    value={previewSettings.duration}
                    onChange={(e) => setPreviewSettings(prev => ({ ...prev, duration: parseFloat(e.target.value) }))}
                    className="w-full border border-gray-300 rounded px-3 py-2"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Šířka (px)
                  </label>
                  <input
                    type="number"
                    value={previewSettings.width}
                    onChange={(e) => setPreviewSettings(prev => ({ ...prev, width: parseInt(e.target.value) }))}
                    className="w-full border border-gray-300 rounded px-3 py-2"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Výška (px)
                  </label>
                  <input
                    type="number"
                    value={previewSettings.height}
                    onChange={(e) => setPreviewSettings(prev => ({ ...prev, height: parseInt(e.target.value) }))}
                    className="w-full border border-gray-300 rounded px-3 py-2"
                  />
                </div>
              </div>

              {kenBurnsSettings && Object.keys(kenBurnsSettings).length > 0 && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-6">
                  <h4 className="font-semibold text-green-800 mb-3">
                    ✅ Ken Burns efekty nastaveny
                  </h4>
                  <div className="text-sm space-y-1">
                    <div><strong>Celkem obrázků:</strong> {Object.keys(kenBurnsSettings || {}).length}</div>
                    <div><strong>Použité efekty:</strong></div>
                    <ul className="ml-4 mt-1">
                      {Object.entries(kenBurnsSettings || {}).map(([filename, setting]) => (
                        <li key={filename} className="text-xs text-gray-600">
                          • {filename}: {setting.effectName}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="mt-3 text-xs text-green-700">
                    Chcete-li změnit efekty, vraťte se na záložku "🎭 Ken Burns efekty".
                  </div>
                </div>
              )}

              {/* Navigační tlačítka na začátku Preview tabu */}
              <div className="flex justify-between items-center mb-6 pb-4 border-b">
                <button
                  onClick={() => setActiveTab('kenburns')}
                  className="bg-gray-500 text-white py-2 px-4 rounded hover:bg-gray-600 transition-colors"
                >
                  ← Zpět na Ken Burns efekty
                </button>
                <div className="text-sm text-gray-600">
                  🎨 Krok 4: Náhled Ken Burns efektů
                </div>
              </div>

              {/* VOLBA: Různé typy náhledů vs přeskočit */}
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <button
                    onClick={generateFastPreview}
                    disabled={isGeneratingPreviews || !generatedImages || !kenBurnsSettings || Object.keys(kenBurnsSettings).length === 0}
                    className="w-full bg-blue-500 text-white py-3 px-4 rounded hover:bg-blue-600 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed font-semibold"
                  >
                    {isGeneratingPreviews ? '⚡ Rychlý náhled...' : '⚡ Rychlý náhled'}
                  </button>

              <button
                onClick={generatePreview}
                disabled={isGeneratingPreviews || !generatedImages || !kenBurnsSettings || Object.keys(kenBurnsSettings).length === 0}
                className="w-full bg-purple-500 text-white py-3 px-4 rounded hover:bg-purple-600 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
              >
                    {isGeneratingPreviews ? '🔄 Pomalý náhled...' : '🎨 Pomalý náhled'}
              </button>
                </div>
                
                <div className="text-xs text-gray-600 bg-blue-50 border border-blue-200 rounded p-2">
                  <strong>⚡ Rychlý náhled:</strong> Prvních 5 obrázků, 2s na obrázek, 720p, rychlé efekty<br/>
                  <strong>🎨 Pomalý náhled:</strong> Všechny obrázky, 4s na obrázek, 1280p, kvalitní efekty
                </div>
                
                <div className="text-center text-gray-500 text-sm">NEBO</div>
                
                <button
                  onClick={() => setActiveTab('video')}
                  disabled={isGeneratingPreviews || !generatedImages || !kenBurnsSettings || Object.keys(kenBurnsSettings).length === 0}
                  className="w-full bg-green-500 text-white py-3 px-4 rounded hover:bg-green-600 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed font-semibold"
                >
                  🚀 Přeskočit náhled → rovnou k video generování
                </button>
                
                <div className="text-xs text-gray-600 bg-yellow-50 border border-yellow-200 rounded p-2">
                  💡 <strong>Tip:</strong> Náhled často trvá stejně dlouho jako finální video. 
                  Doporučujeme přeskočit a použít rychlé Ken Burns efekty!
                </div>
              </div>

              {isGeneratingPreviews && (
                <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
                  <div className="flex items-center">
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-purple-600 mr-2"></div>
                    <span className="text-purple-700">Generuji náhled Ken Burns efektů... Toto může trvat několik minut.</span>
                  </div>
                </div>
              )}

              {previews && (
                <div className="mt-6">
                  {previews.previews ? (
                    <>
                  <h4 className="font-semibold text-gray-700 mb-2">
                    🎨 Náhledy Ken Burns efektů ({previews.total_previews} náhledů)
                  </h4>
                  <div className="text-sm text-gray-600 mb-4">
                    Délka náhledů: {previews.preview_duration}s • Rozlišení: {previews.resolution}
                  </div>
                  
                  <div className="space-y-6">
                    {previews.previews.map((imagePreview, idx) => (
                      <div key={idx} className="border border-gray-200 rounded-lg p-4">
                        <h5 className="font-medium text-gray-800 mb-3">
                          🖼️ {imagePreview.image_filename}
                        </h5>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                          {imagePreview.previews.map((preview, previewIdx) => (
                            <div key={previewIdx} className="bg-gray-50 rounded-lg p-3">
                              <div className="text-xs font-medium text-gray-700 mb-2">
                                {preview.effect_display_name}
                              </div>
                              <div className="aspect-video bg-gray-200 rounded overflow-hidden mb-2">
                                <video 
                                  className="w-full h-full object-cover"
                                  controls
                                  muted
                                  loop
                                  preload="metadata"
                                >
                                  <source src={`http://localhost:50000${preview.download_url}`} type="video/mp4" />
                                  Váš prohlížeč nepodporuje HTML5 video.
                                </video>
                              </div>
                              <div className="text-xs text-gray-500 text-center">
                                {preview.duration}s • {formatFileSize(preview.file_size)}
                              </div>
                              <div className="mt-2">
                                <a 
                                  href={`http://localhost:50000${preview.download_url}`}
                                  download={preview.filename}
                                  className="block w-full text-center bg-blue-500 text-white text-xs py-1 px-2 rounded hover:bg-blue-600 transition-colors"
                                >
                                  📥 Stáhnout
                                </a>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                  
                  <div className="mt-4 text-center">
                    <button
                      onClick={() => setActiveTab('video')}
                      className="bg-green-500 text-white py-2 px-6 rounded hover:bg-green-600 transition-colors"
                    >
                      ✅ Pokračovat na sestavení videa
                    </button>
                  </div>
                    </>
                  ) : (
                    <div className="bg-gray-50 rounded-lg p-6">
                      <h4 className="font-semibold text-gray-700 mb-2">
                        🎨 Náhled Ken Burns efektu
                      </h4>
                      <div className="text-sm text-gray-600 mb-4">
                        Náhled byl úspěšně vygenerován a je připraven ke stažení.
                      </div>
                      
                      <div className="bg-white rounded-lg p-4 border border-gray-200">
                        <div className="aspect-video bg-gray-200 rounded overflow-hidden mb-4">
                          <video 
                            className="w-full h-full object-cover"
                            controls
                            muted
                            loop
                            preload="metadata"
                          >
                            <source src={`http://localhost:50000${previews.download_url}`} type="video/mp4" />
                            Váš prohlížeč nepodporuje HTML5 video.
                          </video>
                        </div>
                        <div className="text-sm text-gray-600 text-center mb-3">
                          Velikost: {formatFileSize(previews.file_size)}
                        </div>
                        <div className="text-center">
                          <a 
                            href={`http://localhost:50000${previews.download_url}`}
                            download={previews.preview_file}
                            className="inline-block bg-blue-500 text-white py-2 px-4 rounded hover:bg-blue-600 transition-colors"
                          >
                            📥 Stáhnout náhled
                          </a>
                        </div>
                      </div>
                      
                      {/* NOVÉ: Rychlé video přímo z Ken Burns záložky */}
                      <div className="mt-4 space-y-3">
                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                          <h4 className="font-semibold text-blue-800 mb-2">
                            ⚡ RYCHLÉ ŘEŠENÍ: Video s audio
                          </h4>
                          <p className="text-sm text-blue-700 mb-3">
                            Přeskočit Ken Burns efekty a vytvořit video přímo s MP3 soubory. <strong>Rychlé a praktické!</strong>
                          </p>
                          <button
                            onClick={generateVideoWithAudio}
                            disabled={isGeneratingVideo || !generatedImages}
                            className="w-full bg-blue-500 text-white py-3 px-4 rounded hover:bg-blue-600 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed font-semibold"
                          >
                                                         {isGeneratingVideo ? (
                               <div className="flex items-center justify-center">
                                 <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                                 ⚡ Sestavuji rychlé video s audio... (2-15 min)
                               </div>
                             ) : '🎵 Sestavit rychlé video s audio HNED'}
                          </button>
                        </div>
                        
                                                 <div className="space-y-2">
                        <button
                          onClick={() => setActiveTab('video')}
                             className="w-full bg-green-500 text-white py-3 px-6 rounded hover:bg-green-600 transition-colors font-semibold"
                        >
                             ⚡ Pokračovat k video generování (přeskočit náhled)
                        </button>
                           <div className="text-xs text-center text-gray-600">
                             💡 Náhled často trvá stejně dlouho jako finální video
                           </div>
                         </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Video Tab */}
        {activeTab === 'video' && (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-semibold text-gray-700 mb-4">
                🎬 Nastavení videa
              </h3>
              
              <div className="grid grid-cols-3 gap-4 mb-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Šířka (px)
                  </label>
                  <input
                    type="number"
                    value={videoSettings.width}
                    onChange={(e) => setVideoSettings(prev => ({ ...prev, width: parseInt(e.target.value) }))}
                    className="w-full border border-gray-300 rounded px-3 py-2"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Výška (px)
                  </label>
                  <input
                    type="number"
                    value={videoSettings.height}
                    onChange={(e) => setVideoSettings(prev => ({ ...prev, height: parseInt(e.target.value) }))}
                    className="w-full border border-gray-300 rounded px-3 py-2"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    FPS
                  </label>
                  <input
                    type="number"
                    value={videoSettings.fps}
                    onChange={(e) => setVideoSettings(prev => ({ ...prev, fps: parseInt(e.target.value) }))}
                    min="24"
                    max="60"
                    className="w-full border border-gray-300 rounded px-3 py-2"
                  />
                </div>
              </div>

              {/* Ken Burns nastavení shrnutí */}
              {kenBurnsSettings && Object.keys(kenBurnsSettings).length > 0 && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-6">
                  <h4 className="font-semibold text-green-800 mb-3">
                    ✅ Ken Burns efekty nastaveny
                  </h4>
                  <div className="text-sm space-y-1">
                    <div><strong>Celkem obrázků:</strong> {Object.keys(kenBurnsSettings || {}).length}</div>
                    <div><strong>Použité efekty:</strong></div>
                    <ul className="ml-4 mt-1">
                      {Object.entries(kenBurnsSettings || {}).map(([filename, setting]) => (
                        <li key={filename} className="text-xs text-gray-600">
                          • {filename}: {setting.effectName}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="mt-3 text-xs text-green-700">
                    Chcete-li změnit efekty, vraťte se na záložku "🎭 Ken Burns efekty".
                  </div>
                </div>
              )}

              {generatedImages && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                  <h4 className="font-semibold text-green-800 mb-2">
                    ✅ Obrázky připraveny
                  </h4>
                  <div className="text-sm space-y-1">
                    <div><strong>Projekt:</strong> {generatedImages.project_name}</div>
                    <div><strong>Celkem obrázků:</strong> {generatedImages.total_images}</div>
                    <div><strong>Audio bloků:</strong> {generatedImages.total_blocks}</div>
                    <div><strong>Skupin:</strong> {generatedImages.grouped_blocks?.length || 'N/A'}</div>
                  </div>
                  
                  {/* Náhledy obrázků */}
                  <div className="mt-4">
                    <strong className="text-sm">📸 Náhledy obrázků:</strong>
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 mt-2">
                      {generatedImages.images.map((img, index) => (
                        <div key={index} className="bg-white rounded border p-2 shadow-sm">
                          <div className="aspect-video bg-gray-100 rounded mb-2 overflow-hidden">
                            <img 
                              src={`/api/images/${img.filename}`}
                              alt={`Obrázek ${img.group_number || index + 1}`}
                              className="w-full h-full object-cover hover:scale-105 transition-transform cursor-pointer"
                              onError={(e) => {
                                e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIwIiBoZWlnaHQ9IjE4MCIgdmlld0JveD0iMCAwIDMyMCAxODAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIzMjAiIGhlaWdodD0iMTgwIiBmaWxsPSIjZjNmNGY2Ii8+Cjx0ZXh0IHg9IjE2MCIgeT0iOTAiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxNCIgZmlsbD0iIzY2NjY2NiIgdGV4dC1hbmNob3I9Im1pZGRsZSI+T2Jyw6F6ZWsgc2UgbmVuYcWNdGw8L3RleHQ+Cjwvc3ZnPg==';
                              }}
                            />
                          </div>
                          <div className="text-xs">
                            <div className="font-medium text-gray-800">#{img.group_number || index + 1}</div>
                            <div className="text-gray-600">{img.blocks_count} bloků</div>
                            <div className="text-gray-500 truncate" title={img.filename}>
                              {img.filename}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* 1. NEJRYCHLEJŠÍ: Video bez efektů */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
                <h4 className="font-semibold text-blue-800 mb-2">
                  🚀 NEJRYCHLEJŠÍ: Video s audio (bez efektů)
                </h4>
                <p className="text-sm text-blue-700 mb-3">
                  Statické obrázky s integrovaným audio z MP3 souborů. 
                  <strong>2-15 minut - ideální pro rychlé testování!</strong>
                </p>
                <button
                  onClick={generateVideoWithAudio}
                  disabled={isGeneratingVideo || !generatedImages}
                  className="w-full bg-blue-500 text-white py-3 px-4 rounded hover:bg-blue-600 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed font-semibold"
                >
                  {generatingVideoType === 'simple' ? '🚀 Sestavuji nejrychlejší video...' : '🚀 Nejrychlejší video s audio'}
                </button>
              </div>

              {/* 2. KOMPROMIS: Rychlé Ken Burns efekty */}
              <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
                <h4 className="font-semibold text-green-800 mb-2">
                  ⚡ KOMPROMIS: Rychlé Ken Burns efekty + audio
                </h4>
                                 <p className="text-sm text-green-700 mb-3">
                   Rychlé animace (zoom, pan) s audio z MP3. 
                   <strong>5-30 minut - bez zbytečného náhledu!</strong>
                 </p>
                <button
                  onClick={generateFastKenBurnsVideoWithAudio}
                  disabled={isGeneratingVideo || !generatedImages}
                  className="w-full bg-green-500 text-white py-3 px-4 rounded hover:bg-green-600 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed font-semibold"
                >
                  {generatingVideoType === 'fast-kenburns' ? '⚡ Sestavuji rychlé Ken Burns...' : '⚡ Rychlé Ken Burns efekty + audio'}
                </button>
              </div>

              {/* 3. NEJKRÁSNĚJŠÍ: Pokročilé Ken Burns efekty */}
              <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
                <h4 className="font-semibold text-orange-800 mb-2">
                  🎭 NEJKRÁSNĚJŠÍ: Pokročilé Ken Burns efekty + audio
                </h4>
                <p className="text-sm text-orange-700 mb-3">
                  Nejkvalitnější animované efekty s integrovaným audio z MP3. 
                  <strong>⚠️ POMALÉ - může trvat hodiny!</strong>
                </p>
              <button
                onClick={generateVideo}
                disabled={isGeneratingVideo || !generatedImages}
                  className="w-full bg-orange-500 text-white py-3 px-4 rounded hover:bg-orange-600 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
              >
                  {generatingVideoType === 'kenburns' ? (
                    <div className="flex items-center justify-center">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                      🎭 Sestavuji nejkrásnější video... (hodiny)
                    </div>
                  ) : '🎭 Nejkrásnější Ken Burns efekty + audio'}
              </button>
              </div>

              {isGeneratingVideo && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                  <div className="flex items-center">
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-green-600 mr-2"></div>
                    <span className="text-green-700">Sestavuji video s Ken Burns efekty... Toto může trvat několik minut.</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Results Tab */}
        {activeTab === 'results' && (
          <div className="space-y-6">
            <h3 className="text-lg font-semibold text-gray-700 mb-4">
              📹 Výsledek
            </h3>

            {generatedVideo ? (
              <div className="bg-green-50 border border-green-200 rounded-lg p-6">
                <h4 className="font-semibold text-green-800 mb-4">
                  🎉 Video úspěšně vygenerováno!
                </h4>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="bg-white rounded border p-4">
                    <h5 className="font-medium text-gray-800 mb-3">📊 Informace o videu</h5>
                    <div className="space-y-2 text-sm">
                      <div><strong>Název souboru:</strong> {generatedVideo.filename}</div>
                      <div><strong>Délka:</strong> {generatedVideo.duration?.toFixed(1)} sekund</div>
                      <div><strong>Rozlišení:</strong> {generatedVideo.resolution}</div>
                      <div><strong>FPS:</strong> {generatedVideo.fps}</div>
                      <div><strong>Velikost:</strong> {formatFileSize(generatedVideo.file_size_mb * 1024 * 1024)}</div>
                    </div>
                  </div>

                  <div className="bg-white rounded border p-4">
                    <h5 className="font-medium text-gray-800 mb-3">🎬 Statistiky</h5>
                    <div className="space-y-2 text-sm">
                      <div><strong>Audio souborů:</strong> {generatedVideo.audio_files_used}</div>
                      <div><strong>Obrázků použito:</strong> {generatedVideo.images_used}</div>
                      <div><strong>Projekt:</strong> {generatedVideo.project_name}</div>
                    </div>
                  </div>
                </div>

                <div className="mt-6 flex justify-center">
                  <button
                    onClick={downloadVideo}
                    className="bg-blue-500 text-white py-3 px-6 rounded hover:bg-blue-600 transition-colors"
                  >
                    📥 Stáhnout video
                  </button>
                </div>
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500">
                <div className="text-4xl mb-2">🎬</div>
                <p>Ještě nebylo vygenerováno žádné video</p>
                <p className="text-sm">Projděte kroky 1 a 2 pro vygenerování videa</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default VideoGenerationSimple; 