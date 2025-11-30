import { useState, useEffect } from 'react';
import type { AgentConfig } from '../types';

interface AgentSettingsProps {
  domainId: string;
  domainName: string;
  onClose: () => void;
  onPreviewPrompt: (phase: 'discovery' | 'synthesis') => void;
}

const AVAILABLE_MODELS = [
  'claude-3-haiku-20240307',
  'claude-3-5-sonnet-20241022',
  'claude-3-opus-20240229',
];

export function AgentSettings({ domainId, domainName, onClose, onPreviewPrompt }: AgentSettingsProps) {
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchConfig();
  }, [domainId]);

  const fetchConfig = async () => {
    try {
      const response = await fetch(`/api/domains/${domainId}/agent-config`);
      if (response.ok) {
        const data = await response.json();
        setConfig(data);
      }
    } catch (error) {
      console.error('Failed to fetch config:', error);
    } finally {
      setLoading(false);
    }
  };

  const saveConfig = async () => {
    if (!config) return;

    setSaving(true);
    try {
      const response = await fetch(`/api/domains/${domainId}/agent-config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });

      if (response.ok) {
        alert('Configuration saved! Changes will apply on next agent run.');
        onClose();
      }
    } catch (error) {
      alert('Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  if (loading || !config) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
        <div className="bg-white rounded-lg p-6">
          <div className="text-gray-600">Loading configuration...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <h2 className="text-xl font-bold text-gray-900">
            Agent Settings: {domainName}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-2xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="px-6 py-4 space-y-6">
          {/* Discovery Agent Settings */}
          <div className="border border-gray-200 rounded-lg p-4">
            <h3 className="font-semibold text-gray-900 mb-4 flex items-center justify-between">
              Discovery Agent
              <button
                onClick={() => onPreviewPrompt('discovery')}
                className="text-sm text-primary-600 hover:text-primary-700 font-medium"
              >
                Preview Prompt →
              </button>
            </h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Model
                </label>
                <select
                  value={config.discovery_model}
                  onChange={(e) => setConfig({ ...config, discovery_model: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                >
                  {AVAILABLE_MODELS.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  Haiku is fast & cheap, Sonnet is balanced, Opus is highest quality
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Max Steps
                </label>
                <input
                  type="number"
                  min="1"
                  max="30"
                  value={config.discovery_max_steps}
                  onChange={(e) => setConfig({ ...config, discovery_max_steps: parseInt(e.target.value) })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Number of tool calls the agent can make (searches, fetches). Default: 15
                </p>
              </div>
            </div>
          </div>

          {/* Synthesis Agent Settings */}
          <div className="border border-gray-200 rounded-lg p-4">
            <h3 className="font-semibold text-gray-900 mb-4 flex items-center justify-between">
              Synthesis Agent
              <button
                onClick={() => onPreviewPrompt('synthesis')}
                className="text-sm text-primary-600 hover:text-primary-700 font-medium"
              >
                Preview Prompt →
              </button>
            </h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Model
                </label>
                <select
                  value={config.synthesis_model}
                  onChange={(e) => setConfig({ ...config, synthesis_model: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                >
                  {AVAILABLE_MODELS.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  Synthesis benefits from higher quality models (Sonnet recommended)
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Max Steps
                </label>
                <input
                  type="number"
                  min="1"
                  max="10"
                  value={config.synthesis_max_steps}
                  onChange={(e) => setConfig({ ...config, synthesis_max_steps: parseInt(e.target.value) })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Synthesis doesn't use tools, so this is usually low. Default: 3
                </p>
              </div>
            </div>
          </div>

          {/* Info Box */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <h4 className="font-semibold text-blue-900 text-sm mb-2">ℹ️ About Agent Configuration</h4>
            <ul className="text-sm text-blue-800 space-y-1">
              <li>• Changes apply to the next agent run (manual refresh or scheduled update)</li>
              <li>• Use "Preview Prompt" to see exactly what will be sent to the model</li>
              <li>• Higher max_steps = more thorough but slower & more expensive</li>
              <li>• Better models = higher quality but higher cost</li>
            </ul>
          </div>
        </div>

        <div className="sticky bottom-0 bg-gray-50 border-t border-gray-200 px-6 py-4 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 hover:text-gray-900 font-medium"
          >
            Cancel
          </button>
          <button
            onClick={saveConfig}
            disabled={saving}
            className="px-6 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:bg-gray-300 font-medium"
          >
            {saving ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>
      </div>
    </div>
  );
}
