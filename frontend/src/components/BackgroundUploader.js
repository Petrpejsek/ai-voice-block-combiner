import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';

const BackgroundUploader = ({ onBackgroundSelected }) => {
  const [backgrounds, setBackgrounds] = useState([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [dragActive, setDragActive] = useState(false);
  const [selectedBackground, setSelectedBackground] = useState(null);
  const fileInputRef = useRef(null);

  // Načte dostupné pozadí při načtení komponenty
  useEffect(() => {
    loadBackgrounds();
  }, []);

  const loadBackgrounds = async () => {
    try {
      const response = await axios.get('/api/list-backgrounds');
      setBackgrounds(response.data.backgrounds || []);
    } catch (error) {
      console.error('Chyba při načítání pozadí:', error);
    }
  };

  const handleFileSelect = (files) => {
    if (files && files.length > 0) {
      uploadBackground(files[0]);
    }
  };

  const uploadBackground = async (file) => {
    if (!file) return;

    // Kontrola typu souboru
    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png'];
    if (!allowedTypes.includes(file.type)) {
      setUploadError('Nepovolený typ souboru. Povolené: JPG, PNG');
      return;
    }

    // Kontrola velikosti (max 10MB)
    if (file.size > 10 * 1024 * 1024) {
      setUploadError('Soubor je příliš velký. Maximum je 10MB');
      return;
    }

    setIsUploading(true);
    setUploadError('');

    const formData = new FormData();
    formData.append('background_file', file);

    try {
      const response = await axios.post('/api/upload-background', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      if (response.data.success) {
        // Znovu načte seznam pozadí
        await loadBackgrounds();
        
        // AUTOMATICKY VYBERE nově nahraný obrázek
        const newBackground = {
          filename: response.data.filename,
          size: response.data.size,
          modified: Date.now() / 1000,
          url: `/api/backgrounds/${response.data.filename}`
        };
        
        selectBackground(newBackground);
        setUploadError('');
      }
    } catch (error) {
      const errorMsg = error.response?.data?.error || 'Chyba při nahrávání obrázku';
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

  const selectBackground = (background) => {
    console.log('BackgroundUploader vybírá pozadí:', background);
    setSelectedBackground(background);
    if (onBackgroundSelected) {
      console.log('Volám onBackgroundSelected callback');
      onBackgroundSelected(background);
    }
  };

  const removeBackground = (background) => {
    setSelectedBackground(null);
    if (onBackgroundSelected) {
      onBackgroundSelected(null);
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
        Správa obrázků pozadí
      </h2>

      {/* Upload area */}
      <div className="mb-6">
        <div
          className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors cursor-pointer
            ${dragActive 
              ? 'border-blue-500 bg-blue-50' 
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
            accept="image/jpeg,image/jpg,image/png"
            onChange={handleFileChange}
            className="hidden"
            disabled={isUploading}
          />
          
          {isUploading ? (
            <div className="flex items-center justify-center">
              <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-blue-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Nahrávám obrázek...
            </div>
          ) : (
            <>
              <svg className="mx-auto h-12 w-12 text-gray-400 mb-4" stroke="currentColor" fill="none" viewBox="0 0 48 48">
                <path d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <div className="text-sm text-gray-600">
                <p className="font-medium">Klikněte pro výběr nebo přetáhněte obrázek</p>
                <p className="text-xs text-gray-500 mt-1">PNG, JPG až 10MB</p>
              </div>
            </>
          )}
        </div>

        {/* Error message */}
        {uploadError && (
          <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-md">
            <p className="text-sm text-red-600">CHYBA: {uploadError}</p>
          </div>
        )}
      </div>

      {/* Selected background */}
      {selectedBackground && (
        <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg">
          <div className="flex items-center justify-between">
            <div>
                          <h3 className="text-sm font-medium text-green-800">
              Vybrané pozadí
            </h3>
              <p className="text-sm text-green-700">{selectedBackground.filename}</p>
            </div>
            <button
              onClick={removeBackground}
              className="text-red-500 hover:text-red-700 text-sm"
            >
              Odebrat
            </button>
          </div>
        </div>
      )}

      {/* Background gallery */}
      {backgrounds.length > 0 && (
        <div>
          <h3 className="text-lg font-medium text-gray-900 mb-3">
            Nahrané pozadí ({backgrounds.length})
          </h3>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {backgrounds.map((background, index) => (
              <div
                key={index}
                className={`relative bg-gray-50 rounded-lg overflow-hidden border-2 transition-colors cursor-pointer
                  ${selectedBackground?.filename === background.filename
                    ? 'border-green-500 bg-green-50'
                    : 'border-gray-200 hover:border-gray-300'
                  }
                `}
                onClick={() => selectBackground(background)}
              >
                {/* Image preview */}
                <div className="aspect-w-16 aspect-h-9 bg-gray-100">
                  <img
                    src={background.url}
                    alt={background.filename}
                    className="w-full h-32 object-cover"
                    loading="lazy"
                  />
                </div>
                
                {/* Image info */}
                <div className="p-3">
                  <h4 className="text-sm font-medium text-gray-900 truncate" title={background.filename}>
                    {background.filename}
                  </h4>
                  <div className="flex justify-between items-center mt-1">
                    <span className="text-xs text-gray-500">
                      {formatFileSize(background.size)}
                    </span>
                    <span className="text-xs text-gray-500">
                      {formatDate(background.modified)}
                    </span>
                  </div>
                </div>

                {/* Selected indicator */}
                {selectedBackground?.filename === background.filename && (
                  <div className="absolute top-2 right-2 w-6 h-6 bg-green-500 rounded-full flex items-center justify-center">
                    <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {backgrounds.length === 0 && !isUploading && (
        <div className="text-center py-8">
          <svg className="mx-auto h-12 w-12 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          <h3 className="text-sm font-medium text-gray-900 mb-1">Žádné pozadí</h3>
          <p className="text-sm text-gray-500">Nahrajte první obrázek pozadí pro vaše videa</p>
        </div>
      )}
    </div>
  );
};

export default BackgroundUploader; 