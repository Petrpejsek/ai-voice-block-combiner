import React, { useState, useEffect } from 'react';

// Základní mock data pro test
const mockProjects = [];

function App() {
  const [result, setResult] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [showYouTubeModal, setShowYouTubeModal] = useState(false);
  const [selectedYouTubeProject, setSelectedYouTubeProject] = useState(null);
  const [audioFiles, setAudioFiles] = useState([]);

  const handleCombineAudio = () => {
    console.log('Test function');
  };

  const formatDuration = (seconds) => {
    return '00:00';
  };

  const downloadFile = (filename) => {
    console.log('Download:', filename);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="container mx-auto p-4">
        {/* Tlačítko pro zpracování */}
        <div className="text-center">
          <button
            onClick={handleCombineAudio}
            disabled={isProcessing || audioFiles.length === 0}
            className="w-full py-4 px-6 rounded-lg font-medium text-white text-lg bg-primary-600 hover:bg-primary-700 transition-colors"
          >
            {isProcessing ? 'Zpracovávám...' : 'Spojit & Exportovat'}
          </button>
        </div>

        {/* Výsledky */}
        {result && (
          <div className="bg-white rounded-lg shadow-sm p-6">
            <h3>Výsledky</h3>
          </div>
        )}
      </div>

      {/* YouTube modal */}
      {showYouTubeModal && selectedYouTubeProject && (
        <div className="fixed inset-0 bg-black bg-opacity-50">
          <div className="bg-white rounded-lg">
            <p>Test modal</p>
          </div>
        </div>
      )}
    </div>
  );
}

export default App; 