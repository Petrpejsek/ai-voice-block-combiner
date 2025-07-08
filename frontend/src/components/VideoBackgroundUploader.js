import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';

const VideoBackgroundUploader = ({ onVideoBackgroundSelected }) => {
  const [videoBackgrounds, setVideoBackgrounds] = useState([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [dragActive, setDragActive] = useState(false);
  const [selectedVideoBackground, setSelectedVideoBackground] = useState(null);
  const fileInputRef = useRef(null);

  // Načte dostupné video pozadí při načtení komponenty
  useEffect(() => {
    loadVideoBackgrounds();
  }, []);

  const loadVideoBackgrounds = async () => {
    try {
      const response = await axios.get('/api/list-video-backgrounds');
      setVideoBackgrounds(response.data.video_backgrounds || []);
    } catch (error) {
      console.error('Chyba při načítání video pozadí:', error);
    }
  };

  const handleFileSelect = (files) => {
    if (files && files.length > 0) {
      uploadVideoBackground(files[0]);
    }
  };

  const uploadVideoBackground = async (file) => {
    if (!file) return;

    // Kontrola typu souboru
    const allowedTypes = ['video/mp4', 'video/quicktime'];
    if (!allowedTypes.includes(file.type)) {
      setUploadError('Nepovolený typ souboru. Povolené: MP4, MOV');
      return;
    }

    // Kontrola velikosti (max 100MB)
    if (file.size > 100 * 1024 * 1024) {
      setUploadError('Soubor je příliš velký. Maximum je 100MB');
      return;
    }

    setIsUploading(true);
    setUploadError('');

    const formData = new FormData();
    formData.append('video_background_file', file);

    try {
      const response = await axios.post('/api/upload-video-background', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      if (response.data.success) {
        // Znovu načte seznam video pozadí
        await loadVideoBackgrounds();
        
        // AUTOMATICKY VYBERE nově nahráno video
        const newVideoBackground = {
          filename: response.data.filename,
          size: response.data.size,
          modified: Date.now() / 1000,
          url: `/api/video-backgrounds/${response.data.filename}`
        };
        
        selectVideoBackground(newVideoBackground);
        setUploadError('');
      }
    } catch (error) {
      const errorMsg = error.response?.data?.error || 'Chyba při nahrávání videa';
      setUploadError(errorMsg);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    const files = e.dataTransfer.files;
    handleFileSelect(files);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
  };

  const handleClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e) => {
    handleFileSelect(e.target.files);
  };

  const selectVideoBackground = (videoBackground) => {
    console.log('VideoBackgroundUploader vybírá video pozadí:', videoBackground);
    setSelectedVideoBackground(videoBackground);
    if (onVideoBackgroundSelected) {
              console.log('Volám onVideoBackgroundSelected callback');
      onVideoBackgroundSelected(videoBackground);
    }
  };

  const removeVideoBackground = (videoBackground) => {
    setSelectedVideoBackground(null);
    if (onVideoBackgroundSelected) {
      onVideoBackgroundSelected(null);
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatDate = (timestamp) => {
    return new Date(timestamp * 1000).toLocaleDateString('cs-CZ', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
      <h2 className="text-xl font-bold text-gray-900 mb-4">
        Správa video pozadí
      </h2>

      {/* Upload area */}
      <div className="mb-6">
        <div
          className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors cursor-pointer
            ${dragActive 
              ? 'border-purple-500 bg-purple-50' 
              : 'border-gray-300 hover:border-gray-400'
            }
            ${isUploading ? 'opacity-50 cursor-not-allowed' : ''}
          `}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={!isUploading ? handleClick : undefined}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="video/mp4,video/quicktime"
            onChange={handleFileChange}
            className="hidden"
            disabled={isUploading}
          />
          
          {isUploading ? (
            <div className="flex items-center justify-center">
              <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-purple-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Nahrávám video...
            </div>
          ) : (
            <>
              <svg className="mx-auto h-12 w-12 text-gray-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              <div className="text-sm text-gray-600">
                <p className="font-medium">Klikněte pro výběr nebo přetáhněte video</p>
                <p className="text-xs text-gray-500 mt-1">MP4, MOV až 100MB</p>
                <p className="text-xs text-purple-600 mt-1">Video bude automaticky loopováno podle délky audia</p>
              </div>
            </>
          )}
        </div>

        {/* Error message */}
        {uploadError && (
          <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-md">
            <p className="text-sm text-red-600">{uploadError}</p>
          </div>
        )}
      </div>

      {/* Video gallery */}
      {videoBackgrounds.length > 0 && (
        <div className="mb-4">
          <h3 className="text-lg font-medium text-gray-900 mb-3">Dostupná video pozadí:</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {videoBackgrounds.map((video, index) => (
              <div
                key={video.filename}
                className={`relative border-2 rounded-lg overflow-hidden cursor-pointer transition-all
                  ${selectedVideoBackground?.filename === video.filename
                    ? 'border-purple-500 ring-2 ring-purple-500 ring-opacity-50'
                    : 'border-gray-200 hover:border-gray-300'
                  }
                `}
                onClick={() => selectVideoBackground(video)}
              >
                {/* Video preview */}
                <div className="aspect-video bg-gray-100 flex items-center justify-center">
                  <video
                    src={video.url}
                    className="w-full h-full object-cover"
                    muted
                    loop
                    autoPlay
                    playsInline
                    onError={(e) => {
                      // Fallback při chybě načítání videa
                      e.target.style.display = 'none';
                      e.target.nextSibling.style.display = 'flex';
                    }}
                  />
                  {/* Fallback při chybě */}
                  <div className="w-full h-full bg-gray-200 items-center justify-center hidden">
                    <svg className="w-12 h-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                  </div>
                </div>

                {/* Video info */}
                <div className="p-3 bg-white">
                  <div className="flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate" title={video.filename}>
                        {video.filename}
                      </p>
                      <div className="mt-1 flex items-center text-xs text-gray-500">
                        <span>{formatFileSize(video.size)}</span>
                        <span className="mx-1">•</span>
                        <span>{formatDate(video.modified)}</span>
                      </div>
                    </div>
                    
                    {selectedVideoBackground?.filename === video.filename && (
                      <div className="ml-2 flex-shrink-0">
                        <div className="w-6 h-6 bg-purple-500 rounded-full flex items-center justify-center">
                          <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Selected overlay */}
                {selectedVideoBackground?.filename === video.filename && (
                  <div className="absolute inset-0 bg-purple-500 bg-opacity-20 flex items-center justify-center">
                    <div className="bg-purple-500 text-white px-3 py-1 rounded-full text-sm font-medium">
                      Vybráno
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Selected video info */}
      {selectedVideoBackground && (
        <div className="mt-4 p-4 bg-purple-50 border border-purple-200 rounded-lg">
          <div className="flex items-start justify-between">
            <div>
              <h4 className="text-sm font-medium text-purple-900">Vybrané video pozadí:</h4>
              <p className="text-sm text-purple-700 mt-1">{selectedVideoBackground.filename}</p>
              <p className="text-xs text-purple-600 mt-1">
                {formatFileSize(selectedVideoBackground.size)} • {formatDate(selectedVideoBackground.modified)}
              </p>
            </div>
            <button
              onClick={() => removeVideoBackground(selectedVideoBackground)}
              className="ml-4 px-3 py-1 text-xs bg-white text-purple-700 border border-purple-300 rounded hover:bg-purple-50 transition-colors"
            >
              Odebrat
            </button>
          </div>
        </div>
      )}

      {videoBackgrounds.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          <svg className="mx-auto h-12 w-12 text-gray-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          <p className="text-sm">Zatím nejsou nahrána žádná video pozadí</p>
          <p className="text-xs text-gray-400 mt-1">Nahrajte první video pomocí formuláře výše</p>
        </div>
      )}
    </div>
  );
};

export default VideoBackgroundUploader; 