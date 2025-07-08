import React, { useState, useEffect } from 'react';

const AssistantManager = ({ onRefreshNeeded }) => {
  const [assistants, setAssistants] = useState([]);
  const [hiddenAssistants, setHiddenAssistants] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [selectedAssistants, setSelectedAssistants] = useState([]);
  const [showInstructions, setShowInstructions] = useState({});
  const [filterText, setFilterText] = useState('');
  const [showHidden, setShowHidden] = useState(false);
  const [hiddenCount, setHiddenCount] = useState(0);

  // Načti API klíč z localStorage při načtení komponenty
  useEffect(() => {
    const savedApiKey = localStorage.getItem('openai_api_key');
    if (savedApiKey) {
      setApiKey(savedApiKey);
    }
  }, []);

  // Automaticky načti asistenty když je API klíč k dispozici
  useEffect(() => {
    if (apiKey) {
      loadAssistants();
    }
  }, [apiKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadAssistants = async () => {
    if (!apiKey) {
      setError('Zadejte prosím OpenAI API klíč');
      return;
    }

    setLoading(true);
    setError('');
    setSuccess('');

    try {
      const response = await fetch('/api/list-assistants', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          openai_api_key: apiKey
        }),
      });

      const data = await response.json();

      if (response.ok) {
        setAssistants(data.assistants || []);
        setHiddenCount(data.hidden_count || 0);
        setSuccess(`✅ Načteno ${data.total || 0} asistentů (${data.hidden_count || 0} skrytých)`);
        
        // Uložit API klíč pro příští použití
        localStorage.setItem('openai_api_key', apiKey);
      } else {
        setError(data.error || 'Chyba při načítání asistentů');
      }
    } catch (err) {
      setError('Chyba spojení se serverem');
    } finally {
      setLoading(false);
    }
  };

  const loadHiddenAssistants = async () => {
    if (!apiKey) {
      setError('Zadejte prosím OpenAI API klíč');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await fetch('/api/list-hidden-assistants', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          openai_api_key: apiKey
        }),
      });

      const data = await response.json();

      if (response.ok) {
        setHiddenAssistants(data.hidden_assistants || []);
        setSuccess(`✅ Načteno ${data.hidden_count || 0} skrytých asistentů`);
      } else {
        setError(data.error || 'Chyba při načítání skrytých asistentů');
      }
    } catch (err) {
      setError('Chyba spojení se serverem');
    } finally {
      setLoading(false);
    }
  };

  const hideAssistant = async (assistantId) => {
    if (!window.confirm(`Opravdu chcete skrýt asistenta ${assistantId} ze seznamu?\n\n⚠️ Asistent bude pouze skrytý v tomto systému, ale zůstane v OpenAI.`)) {
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await fetch('/api/hide-assistant', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          assistant_id: assistantId
        }),
      });

      const data = await response.json();

      if (response.ok) {
        setSuccess(data.message);
        setHiddenCount(data.hidden_count);
        // Odstraň z viditelného seznamu
        setAssistants(prev => prev.filter(a => a.id !== assistantId));
        setSelectedAssistants(prev => prev.filter(id => id !== assistantId));
        
        // Informuj rodičovskou komponentu o změně
        if (onRefreshNeeded) {
          onRefreshNeeded();
        }
      } else {
        setError(data.error || 'Chyba při skrývání asistenta');
      }
    } catch (err) {
      setError('Chyba spojení se serverem');
    } finally {
      setLoading(false);
    }
  };

  const showAssistant = async (assistantId) => {
    setLoading(true);
    setError('');

    try {
      const response = await fetch('/api/show-assistant', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          assistant_id: assistantId
        }),
      });

      const data = await response.json();

      if (response.ok) {
        setSuccess(data.message);
        setHiddenCount(data.hidden_count);
        // Odstraň ze seznamu skrytých
        setHiddenAssistants(prev => prev.filter(a => a.id !== assistantId));
        // Znovu načti viditelné asistenty
        loadAssistants();
        
        // Informuj rodičovskou komponentu o změně
        if (onRefreshNeeded) {
          onRefreshNeeded();
        }
      } else {
        setError(data.error || 'Chyba při zobrazování asistenta');
      }
    } catch (err) {
      setError('Chyba spojení se serverem');
    } finally {
      setLoading(false);
    }
  };

  const hideMultipleAssistants = async () => {
    if (selectedAssistants.length === 0) {
      setError('Vyberte prosím asistenty ke skrytí');
      return;
    }

    if (!window.confirm(`Opravdu chcete skrýt ${selectedAssistants.length} asistentů ze seznamu?\n\n⚠️ Asistenti budou pouze skrytí v tomto systému, ale zůstanou v OpenAI.`)) {
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await fetch('/api/hide-multiple-assistants', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          assistant_ids: selectedAssistants
        }),
      });

      const data = await response.json();

      if (response.ok) {
        setSuccess(data.message);
        setHiddenCount(data.hidden_count);
        // Odstraň z viditelného seznamu
        setAssistants(prev => prev.filter(a => !selectedAssistants.includes(a.id)));
        setSelectedAssistants([]);
        
        // Informuj rodičovskou komponentu o změně
        if (onRefreshNeeded) {
          onRefreshNeeded();
        }
      } else {
        setError(data.error || 'Chyba při skrývání asistentů');
      }
    } catch (err) {
      setError('Chyba spojení se serverem');
    } finally {
      setLoading(false);
    }
  };

  const clearHiddenAssistants = async () => {
    if (!window.confirm(`Opravdu chcete zobrazit všechny skryté asistenty zpět?`)) {
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await fetch('/api/clear-hidden-assistants', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({}),
      });

      const data = await response.json();

      if (response.ok) {
        setSuccess(data.message);
        setHiddenCount(0);
        setHiddenAssistants([]);
        setShowHidden(false);
        // Znovu načti viditelné asistenty
        loadAssistants();
        
        // Informuj rodičovskou komponentu o změně
        if (onRefreshNeeded) {
          onRefreshNeeded();
        }
      } else {
        setError(data.error || 'Chyba při zobrazování asistentů');
      }
    } catch (err) {
      setError('Chyba spojení se serverem');
    } finally {
      setLoading(false);
    }
  };

  const toggleInstructions = (assistantId) => {
    setShowInstructions(prev => ({
      ...prev,
      [assistantId]: !prev[assistantId]
    }));
  };

  const toggleAssistantSelection = (assistantId) => {
    setSelectedAssistants(prev => 
      prev.includes(assistantId)
        ? prev.filter(id => id !== assistantId)
        : [...prev, assistantId]
    );
  };

  const toggleSelectAll = () => {
    const currentList = showHidden ? hiddenAssistants : assistants;
    const filteredList = currentList.filter(assistant =>
      assistant.name?.toLowerCase().includes(filterText.toLowerCase()) ||
      assistant.id.toLowerCase().includes(filterText.toLowerCase())
    );

    if (selectedAssistants.length === filteredList.length) {
      setSelectedAssistants([]);
    } else {
      setSelectedAssistants(filteredList.map(a => a.id));
    }
  };

  const currentAssistants = showHidden ? hiddenAssistants : assistants;
  const filteredAssistants = currentAssistants.filter(assistant =>
    assistant.name?.toLowerCase().includes(filterText.toLowerCase()) ||
    assistant.id.toLowerCase().includes(filterText.toLowerCase())
  );

  return (
    <div className="p-6 bg-white rounded-lg shadow-sm">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-2xl">🤖</span>
        <h2 className="text-xl font-semibold text-gray-800">Správa OpenAI Asistentů</h2>
        {hiddenCount > 0 && (
          <span className="px-2 py-1 bg-yellow-100 text-yellow-800 rounded-full text-sm">
            {hiddenCount} skrytých
          </span>
        )}
      </div>

      {/* API klíč input */}
      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          OpenAI API klíč:
        </label>
        <div className="flex gap-2">
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-..."
            className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            onClick={loadAssistants}
            disabled={loading || !apiKey}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? 'Načítám...' : 'Načíst asistenty'}
          </button>
        </div>
      </div>

      {/* Chybové a úspěšné zprávy */}
      {error && (
        <div className="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded">
          {error}
        </div>
      )}

      {success && (
        <div className="mb-4 p-3 bg-green-100 border border-green-400 text-green-700 rounded">
          {success}
        </div>
      )}

      {assistants.length > 0 || hiddenAssistants.length > 0 ? (
        <div>
          {/* Ovládací panel */}
          <div className="mb-4 flex flex-wrap gap-2 items-center justify-between">
            <div className="flex gap-2 items-center">
              <button
                onClick={() => {
                  setShowHidden(false);
                  setSelectedAssistants([]);
                }}
                className={`px-3 py-1 rounded ${!showHidden ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-700'}`}
              >
                Viditelní ({assistants.length})
              </button>
              <button
                onClick={() => {
                  setShowHidden(true);
                  setSelectedAssistants([]);
                  if (hiddenAssistants.length === 0) {
                    loadHiddenAssistants();
                  }
                }}
                className={`px-3 py-1 rounded ${showHidden ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-700'}`}
              >
                Skrytí ({hiddenCount})
              </button>
            </div>

            <div className="flex gap-2 items-center">
              <input
                type="text"
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
                placeholder="Filtrovat podle názvu nebo ID..."
                className="px-3 py-1 border border-gray-300 rounded-md text-sm"
              />
            </div>
          </div>

          {/* Hromadné akce */}
          {filteredAssistants.length > 0 && (
            <div className="mb-4 flex gap-2 items-center">
              <button
                onClick={toggleSelectAll}
                className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm"
              >
                {selectedAssistants.length === filteredAssistants.length ? 'Zrušit výběr' : 'Vybrat vše'}
              </button>
              
              {selectedAssistants.length > 0 && (
                <>
                  <span className="text-sm text-gray-600">
                    Vybráno: {selectedAssistants.length}
                  </span>
                  {!showHidden ? (
                    <button
                      onClick={hideMultipleAssistants}
                      disabled={loading}
                      className="px-3 py-1 bg-yellow-600 text-white rounded text-sm hover:bg-yellow-700 disabled:opacity-50"
                    >
                      Skrýt vybrané
                    </button>
                  ) : (
                    <button
                      onClick={() => {
                        selectedAssistants.forEach(id => showAssistant(id));
                        setSelectedAssistants([]);
                      }}
                      disabled={loading}
                      className="px-3 py-1 bg-green-600 text-white rounded text-sm hover:bg-green-700 disabled:opacity-50"
                    >
                      Zobrazit vybrané
                    </button>
                  )}
                </>
              )}

              {showHidden && hiddenAssistants.length > 0 && (
                <button
                  onClick={clearHiddenAssistants}
                  disabled={loading}
                  className="px-3 py-1 bg-green-600 text-white rounded text-sm hover:bg-green-700 disabled:opacity-50"
                >
                  Zobrazit všechny skryté
                </button>
              )}
            </div>
          )}

          {/* Seznam asistentů */}
          {filteredAssistants.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              {showHidden ? 'Žádní skrytí asistenti nenalezeni' : 'Žádní asistenti nenalezeni'}
            </div>
          ) : (
            <div className="space-y-3">
              {filteredAssistants.map((assistant) => (
                <div key={assistant.id} className="border border-gray-200 rounded-lg p-4">
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3 flex-1">
                      <input
                        type="checkbox"
                        checked={selectedAssistants.includes(assistant.id)}
                        onChange={() => toggleAssistantSelection(assistant.id)}
                        className="mt-1"
                      />
                      
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <h3 className="font-medium text-gray-800">
                            {assistant.name || 'Bez názvu'}
                          </h3>
                          <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded">
                            {assistant.model}
                          </span>
                        </div>
                        
                        <p className="text-sm text-gray-600 mb-2">
                          ID: <code className="bg-gray-100 px-1 rounded">{assistant.id}</code>
                        </p>
                        
                        {assistant.description && (
                          <p className="text-sm text-gray-600 mb-2">
                            {assistant.description}
                          </p>
                        )}
                        
                        {assistant.instructions && (
                          <div className="mb-2">
                            <button
                              onClick={() => toggleInstructions(assistant.id)}
                              className="text-sm text-blue-600 hover:text-blue-800"
                            >
                              {showInstructions[assistant.id] ? 'Skrýt instrukce' : 'Zobrazit instrukce'}
                            </button>
                            {showInstructions[assistant.id] && (
                              <div className="mt-2 p-2 bg-gray-50 rounded text-sm">
                                {assistant.instructions}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                    
                    <div className="flex gap-2">
                      {!showHidden ? (
                        <button
                          onClick={() => hideAssistant(assistant.id)}
                          disabled={loading}
                          className="px-3 py-1 bg-yellow-600 text-white rounded text-sm hover:bg-yellow-700 disabled:opacity-50"
                          title="Skrýt asistenta ze seznamu (nezmaže z OpenAI)"
                        >
                          Skrýt
                        </button>
                      ) : (
                        <button
                          onClick={() => showAssistant(assistant.id)}
                          disabled={loading}
                          className="px-3 py-1 bg-green-600 text-white rounded text-sm hover:bg-green-700 disabled:opacity-50"
                          title="Zobrazit asistenta zpět v seznamu"
                        >
                          Zobrazit
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="text-center py-8 text-gray-500">
          {apiKey ? 'Žádní asistenti nenalezeni' : 'Zadejte OpenAI API klíč pro načtení asistentů'}
        </div>
      )}
    </div>
  );
};

export default AssistantManager; 