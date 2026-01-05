import React, { useRef, useState, useEffect } from 'react';
import axios from 'axios';
import { toDisplayString } from '../utils/display';

/**
 * MusicLibraryModal - Globální knihovna podkresové hudby
 * 
 * Features:
 * - Upload music files (MP3/WAV)
 * - Tag management (ambient, cinematic, dramatic, etc.)
 * - Mood classification (dark, uplifting, neutral, peaceful)
 * - Active/inactive toggle
 * - Delete tracks
 * - Preview audio
 * - Usage statistics
 */
const MusicLibraryModal = ({ isOpen, onClose, onSelectTrack }) => {
  const fileInputRef = useRef(null);
  const [tracks, setTracks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [isDragOver, setIsDragOver] = useState(false);
  const [selectedTags, setSelectedTags] = useState([]);
  const [selectedMood, setSelectedMood] = useState('neutral');
  const [filterMood, setFilterMood] = useState('all');
  const [filterTag, setFilterTag] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [edit, setEdit] = useState({}); // filename -> { tagsText, mood }

  // Available tags and moods
  const AVAILABLE_TAGS = ['ambient', 'cinematic', 'piano', 'electronic', 'orchestral', 'guitar', 'dramatic', 'minimal'];
  const AVAILABLE_MOODS = [
    { value: 'neutral', label: 'Neutral', emoji: '😐' },
    { value: 'dark', label: 'Dark/Mysterious', emoji: '🌑' },
    { value: 'uplifting', label: 'Uplifting/Hopeful', emoji: '✨' },
    { value: 'dramatic', label: 'Dramatic/Intense', emoji: '⚡' },
    { value: 'peaceful', label: 'Peaceful/Calm', emoji: '🌊' },
  ];

  useEffect(() => {
    if (isOpen) {
      loadTracks();
    }
  }, [isOpen]);

  const loadTracks = async () => {
    setLoading(true);
    setError('');
    setInfo('');
    try {
      const res = await axios.get('/api/music/library', { timeout: 15000 });
      if (!res.data?.success) throw new Error(res.data?.error || 'Nepodařilo se načíst knihovnu');
      setTracks(res.data.tracks || []);
      // initialize edit buffers
      const buf = {};
      (res.data.tracks || []).forEach((t) => {
        if (!t?.filename) return;
        buf[t.filename] = {
          tagsText: Array.isArray(t.tags) ? t.tags.join(', ') : '',
          mood: t.mood || 'neutral',
        };
      });
      setEdit(buf);
    } catch (e) {
      setError(e.message || 'Chyba při načítání knihovny');
    } finally {
      setLoading(false);
    }
  };

  const uploadFiles = async (files) => {
    if (!files || files.length === 0) return;

    setUploading(true);
    setError('');
    setInfo('');
    try {
      const form = new FormData();
      Array.from(files).forEach((f) => form.append('music_files', f));
      
      // Add selected tags and mood
      form.append('tags', JSON.stringify(selectedTags));
      form.append('mood', selectedMood);

      const res = await axios.post('/api/music/library/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120000,
      });
      
      if (!res.data?.success) throw new Error(res.data?.error || 'Upload selhal');
      
      setTracks(res.data.tracks || []);
      const addedCount = Array.isArray(res.data.added) ? res.data.added.length : (Array.isArray(files) ? files.length : 1);
      setInfo(`✅ Nahráno: ${addedCount} souborů. Najdete je dole v seznamu “Tracks”.`);
      setSelectedTags([]);
      setSelectedMood('neutral');
      // refresh edit buffers
      const buf = {};
      (res.data.tracks || []).forEach((t) => {
        if (!t?.filename) return;
        buf[t.filename] = {
          tagsText: Array.isArray(t.tags) ? t.tags.join(', ') : '',
          mood: t.mood || 'neutral',
        };
      });
      setEdit(buf);
    } catch (e) {
      setError(e.message || 'Chyba při uploadu');
    } finally {
      setUploading(false);
    }
  };

  const normalizeDroppedFiles = (fileList) => {
    const list = Array.from(fileList || []);
    const allowed = ['.mp3', '.wav'];
    const valid = list.filter((f) => {
      const name = (f?.name || '').toLowerCase();
      return allowed.some((ext) => name.endsWith(ext));
    });
    return valid;
  };

  const onDropFiles = async (fileList) => {
    const valid = normalizeDroppedFiles(fileList);
    if (!valid.length) {
      setError('Nepovolený typ souboru. Povolené: MP3, WAV');
      return;
    }
    await uploadFiles(valid);
  };

  const updateTrack = async (filename, updates) => {
    try {
      const res = await axios.post('/api/music/library/update', {
        filename,
        ...updates
      }, { timeout: 15000 });
      
      if (!res.data?.success) throw new Error(res.data?.error || 'Update selhal');
      setTracks(res.data.tracks || []);
      setInfo('✅ Uloženo.');
    } catch (e) {
      setError(e.message || 'Chyba při update');
    }
  };

  const deleteTrack = async (filename) => {
    if (!window.confirm(`Opravdu smazat "${filename}"? Tato akce je nevratná.`)) return;

    try {
      const res = await axios.post('/api/music/library/delete', { filename }, { timeout: 15000 });
      if (!res.data?.success) throw new Error(res.data?.error || 'Delete selhal');
      setTracks(res.data.tracks || []);
      setInfo('✅ Smazáno.');
    } catch (e) {
      setError(e.message || 'Chyba při mazání');
    }
  };

  const toggleTag = (tag) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  };

  const formatDuration = (seconds) => {
    const s = Number(seconds);
    if (!Number.isFinite(s) || s < 0) return '—';
    const minutes = Math.floor(s / 60);
    const remainingSeconds = Math.floor(s % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  // Filter tracks
  const filteredTracks = tracks.filter((t) => {
    if (filterMood !== 'all' && t.mood !== filterMood) return false;
    if (filterTag !== 'all' && !(t.tags || []).includes(filterTag)) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      const nameMatch = (t.original_name || t.filename || '').toLowerCase().includes(q);
      const tagMatch = (t.tags || []).some(tag => tag.toLowerCase().includes(q));
      if (!nameMatch && !tagMatch) return false;
    }
    return true;
  });

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg max-w-6xl w-full max-h-[90vh] overflow-hidden shadow-xl flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-gray-200 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-gray-900">🎵 Music Library</h2>
            <p className="text-sm text-gray-600 mt-1">
              Globální knihovna podkresové hudby • {tracks.length} tracks
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={loadTracks}
              disabled={loading}
              className={`px-3 py-1.5 rounded text-sm border ${
                loading
                  ? 'bg-gray-100 border-gray-200 text-gray-400 cursor-not-allowed'
                  : 'bg-white border-gray-300 text-gray-800 hover:bg-gray-50'
              }`}
              title="Načíst znovu"
            >
              ↻ Refresh
            </button>
            <button
              onClick={onClose}
              className="text-gray-500 hover:text-gray-700 text-3xl leading-none"
              aria-label="Close"
            >
              ×
            </button>
          </div>
        </div>

        {/* Scrollable body (fixes "I can't see/edit/delete tracks" on smaller screens) */}
        <div className="flex-1 min-h-0 overflow-y-auto">
          {/* Error / Info */}
          <div className="px-6 pt-4">
            {error && (
              <div className="p-3 bg-red-50 border border-red-200 rounded">
                <div className="text-sm text-red-700">❌ {toDisplayString(error)}</div>
              </div>
            )}
            {info && (
              <div className="p-3 bg-green-50 border border-green-200 rounded">
                <div className="text-sm text-green-800">{info}</div>
              </div>
            )}
          </div>

          {/* Upload Section */}
          <div className="p-6 border-b border-gray-200 bg-gray-50">
            <div
              className={`mb-4 rounded-lg border-2 border-dashed p-4 transition-colors cursor-pointer ${
                isDragOver
                  ? 'border-purple-400 bg-purple-50'
                  : 'border-gray-300 bg-white hover:bg-gray-50'
              }`}
              onClick={() => {
                if (uploading) return;
                fileInputRef.current?.click();
              }}
              onDragEnter={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setIsDragOver(true);
              }}
              onDragOver={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setIsDragOver(true);
              }}
              onDragLeave={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setIsDragOver(false);
              }}
              onDrop={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setIsDragOver(false);
                if (uploading) return;
                const files = e.dataTransfer?.files;
                if (files && files.length) onDropFiles(files);
              }}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  if (uploading) return;
                  fileInputRef.current?.click();
                }
              }}
              aria-label="Nahrát hudbu: klikněte nebo přetáhněte soubory"
              title="Klikněte nebo přetáhněte MP3/WAV soubory"
            >
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Nahrát novou hudbu (MP3/WAV)
              </label>
              <div className="text-sm text-gray-700">
                {uploading ? (
                  <span>Nahrávám…</span>
                ) : (
                  <span>
                    Přetáhněte soubory sem, nebo klikněte a vyberte je z disku.
                  </span>
                )}
              </div>
              <div className="mt-3">
                <button
                  type="button"
                  disabled={uploading}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (uploading) return;
                    fileInputRef.current?.click();
                  }}
                  className={`px-4 py-2 rounded-md text-sm font-medium border transition-colors ${
                    uploading
                      ? 'bg-gray-100 border-gray-200 text-gray-400 cursor-not-allowed'
                      : 'bg-purple-600 border-purple-600 text-white hover:bg-purple-700'
                  }`}
                >
                  Zvolit soubory
                </button>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".mp3,.wav"
                disabled={uploading}
                onChange={(e) => {
                  const files = Array.from(e.target.files || []);
                  if (files.length) onDropFiles(files);
                  e.target.value = '';
                }}
                className="hidden"
              />
              <div className="text-xs text-gray-600 mt-2">
                Po uploadu se soubory objeví níže v seznamu <span className="font-medium">Tracks</span>. Tady upravíte <span className="font-medium">mood/tags</span>, můžete je <span className="font-medium">deaktivovat</span> nebo <span className="font-medium">smazat</span>.
              </div>
            </div>

            {/* Tags Selection */}
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Tags (vyberte před uploadem)
              </label>
              <div className="flex flex-wrap gap-2">
                {AVAILABLE_TAGS.map((tag) => (
                  <button
                    key={tag}
                    onClick={() => toggleTag(tag)}
                    className={`px-3 py-1 rounded-full text-sm border transition-colors ${
                      selectedTags.includes(tag)
                        ? 'bg-purple-100 border-purple-300 text-purple-800'
                        : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
                    }`}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>

            {/* Mood Selection */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Nálada (vyberte před uploadem)
              </label>
              <div className="flex flex-wrap gap-2">
                {AVAILABLE_MOODS.map((m) => (
                  <button
                    key={m.value}
                    onClick={() => setSelectedMood(m.value)}
                    className={`px-3 py-1 rounded-full text-sm border transition-colors ${
                      selectedMood === m.value
                        ? 'bg-blue-100 border-blue-300 text-blue-800'
                        : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
                    }`}
                  >
                    {m.emoji} {m.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Filters */}
          <div className="p-6 border-b border-gray-200">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Filtr: Nálada</label>
                <select
                  value={filterMood}
                  onChange={(e) => setFilterMood(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                >
                  <option value="all">Všechny</option>
                  {AVAILABLE_MOODS.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.emoji} {m.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Filtr: Tag</label>
                <select
                  value={filterTag}
                  onChange={(e) => setFilterTag(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                >
                  <option value="all">Všechny</option>
                  {AVAILABLE_TAGS.map((tag) => (
                    <option key={tag} value={tag}>
                      {tag}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Hledat</label>
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Název, tag..."
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                />
              </div>
            </div>
          </div>

          {/* Tracks List */}
          <div className="p-6">
            <div className="flex items-center justify-between mb-3">
              <div className="text-sm font-semibold text-gray-900">Tracks</div>
              <div className="text-xs text-gray-600">
                Zobrazeno: {filteredTracks.length} z {tracks.length}
              </div>
            </div>
          {loading ? (
            <div className="text-center text-gray-600 py-8">Načítám...</div>
          ) : filteredTracks.length === 0 ? (
            <div className="text-center text-gray-600 py-8">
              {tracks.length === 0 ? 'Zatím žádná hudba v knihovně.' : 'Žádné výsledky pro vybraný filtr.'}
            </div>
          ) : (
            <div className="space-y-3">
              {filteredTracks.map((track) => {
                const moodData = AVAILABLE_MOODS.find(m => m.value === track.mood) || AVAILABLE_MOODS[0];
                const eb = edit[track.filename] || { tagsText: '', mood: track.mood || 'neutral' };
                
                return (
                  <div key={track.filename} className="p-4 border border-gray-200 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors">
                    <div className="flex items-start justify-between gap-4">
                      {/* Track Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-medium text-gray-900 truncate">
                            {track.original_name || track.filename}
                          </span>
                          <span className="text-xs text-gray-500">
                            ({formatDuration(track.duration_sec)} • {track.size_mb}MB)
                          </span>
                        </div>

                        {/* Tags & Mood */}
                        <div className="flex flex-wrap gap-1.5 mb-2">
                          <span className="px-2 py-0.5 bg-blue-100 text-blue-800 rounded-full text-xs">
                            {moodData.emoji} {moodData.label}
                          </span>
                          {(track.tags || []).map((tag) => (
                            <span key={tag} className="px-2 py-0.5 bg-purple-100 text-purple-800 rounded-full text-xs">
                              {tag}
                            </span>
                          ))}
                          {track.usage_count > 0 && (
                            <span className="px-2 py-0.5 bg-green-100 text-green-800 rounded-full text-xs">
                              Použito {track.usage_count}×
                            </span>
                          )}
                        </div>

                        {/* Audio Player */}
                        <audio
                          controls
                          className="w-full h-8 mt-2"
                          preload="metadata"
                          style={{ height: '32px' }}
                        >
                          <source src={`/api/music/library/download/${track.filename}`} type="audio/mpeg" />
                          Váš prohlížeč nepodporuje přehrávání audia.
                        </audio>

                        {/* Manage metadata */}
                        <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-2">
                          <div>
                            <div className="text-xs text-gray-600 mb-1">Mood</div>
                            <select
                              value={eb.mood || 'neutral'}
                              onChange={(e) => {
                                const mood = e.target.value;
                                setEdit((p) => ({ ...p, [track.filename]: { ...(p[track.filename] || {}), mood } }));
                                updateTrack(track.filename, { mood });
                              }}
                              className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
                            >
                              {AVAILABLE_MOODS.map((m) => (
                                <option key={m.value} value={m.value}>
                                  {m.label}
                                </option>
                              ))}
                            </select>
                          </div>
                          <div className="md:col-span-2">
                            <div className="text-xs text-gray-600 mb-1">Tags (oddělte čárkou)</div>
                            <input
                              value={eb.tagsText || ''}
                              onChange={(e) => {
                                const tagsText = e.target.value;
                                setEdit((p) => ({ ...p, [track.filename]: { ...(p[track.filename] || {}), tagsText } }));
                              }}
                              onBlur={() => {
                                const tags = (eb.tagsText || '')
                                  .split(',')
                                  .map((t) => t.trim().toLowerCase())
                                  .filter(Boolean);
                                updateTrack(track.filename, { tags });
                              }}
                              placeholder="ambient, cinematic, piano"
                              className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
                            />
                            <div className="text-[11px] text-gray-500 mt-1">
                              Tip: použijte konzistentní tagy (např. <span className="font-mono">ambient</span>, <span className="font-mono">cinematic</span>, <span className="font-mono">dramatic</span>).
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex flex-col gap-2">
                        <label className="flex items-center gap-2 text-sm text-gray-700">
                          <input
                            type="checkbox"
                            checked={!!track.active}
                            onChange={(e) => updateTrack(track.filename, { active: e.target.checked })}
                          />
                          Aktivní
                        </label>

                        {onSelectTrack && (
                          <button
                            onClick={() => {
                              onSelectTrack(track);
                              onClose();
                            }}
                            className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 transition-colors"
                          >
                            Vybrat
                          </button>
                        )}

                        <button
                          onClick={() => deleteTrack(track.filename)}
                          className="px-3 py-1 bg-red-600 text-white text-sm rounded hover:bg-red-700 transition-colors"
                        >
                          🗑️ Smazat
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          </div>
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-gray-200 bg-gray-50">
          <div className="flex items-center justify-between">
            <div className="text-sm text-gray-600">
              Zobrazeno: {filteredTracks.length} z {tracks.length} tracks
            </div>
            <button
              onClick={onClose}
              className="px-6 py-2 bg-gray-900 text-white rounded-lg hover:bg-black transition-colors"
            >
              Zavřít
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MusicLibraryModal;

