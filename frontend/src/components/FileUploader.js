import React, { useState, useRef } from 'react';

const FileUploader = ({ onFilesSelected, acceptedFiles, multiple = true, label, placeholder }) => {
  const [isDragActive, setIsDragActive] = useState(false);
  const fileInputRef = useRef();

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setIsDragActive(true);
    } else if (e.type === 'dragleave') {
      setIsDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);

    const files = [...e.dataTransfer.files];
    if (files && files.length > 0) {
      handleFiles(files);
    }
  };

  const handleFiles = (files) => {
    const validFiles = files.filter(file => {
      if (!acceptedFiles) return true;
      return acceptedFiles.some(type => file.type.includes(type));
    });

    if (validFiles.length > 0) {
      onFilesSelected(multiple ? validFiles : validFiles[0]);
    }
  };

  const onFileInputChange = (e) => {
    const files = [...e.target.files];
    if (files.length > 0) {
      handleFiles(files);
    }
  };

  const openFileDialog = () => {
    fileInputRef.current?.click();
  };

  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-gray-700 mb-2">
          {label}
        </label>
      )}
      
      <div
        className={`
          relative border-2 border-dashed rounded-lg p-6 text-center cursor-pointer
          transition-colors duration-200 ease-in-out
          ${isDragActive 
            ? 'border-primary-500 bg-primary-50' 
            : 'border-gray-300 hover:border-gray-400'
          }
        `}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        onClick={openFileDialog}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple={multiple}
          accept={acceptedFiles ? acceptedFiles.map(type => `.${type}`).join(',') : undefined}
          onChange={onFileInputChange}
          className="hidden"
        />
        
        <div className="space-y-2">
          <svg
            className={`mx-auto h-12 w-12 ${isDragActive ? 'text-primary-500' : 'text-gray-400'}`}
            stroke="currentColor"
            fill="none"
            viewBox="0 0 48 48"
          >
            <path
              d="M28 8H12a4 4 0 00-4 4v20m32-12v10m0 0v8a2 2 0 01-2 2H18a2 2 0 01-2-2v-8m12-12V4a2 2 0 012 2v12"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          
          <div>
            <p className={`text-sm ${isDragActive ? 'text-primary-600' : 'text-gray-600'}`}>
              {placeholder || (
                <>
                  <span className="font-medium">Klikni pro výběr souborů</span>{' '}
                  nebo je přetáhni sem
                </>
              )}
            </p>
            {acceptedFiles && (
              <p className="text-xs text-gray-500 mt-1">
                Podporované formáty: {acceptedFiles.join(', ').toUpperCase()}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default FileUploader; 