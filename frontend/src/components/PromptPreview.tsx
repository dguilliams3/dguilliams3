import { useState } from 'react';
import type { PromptPreviewResponse } from '../types';

interface PromptPreviewProps {
  domainId: string;
  phase: 'discovery' | 'synthesis';
  onClose: () => void;
}

export function PromptPreview({ domainId, phase, onClose }: PromptPreviewProps) {
  const [preview, setPreview] = useState<PromptPreviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useState(() => {
    fetchPreview();
  });

  const fetchPreview = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/domains/${domainId}/preview-prompt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain_id: domainId, phase }),
      });

      if (response.ok) {
        const data = await response.json();
        setPreview(data);
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to load prompt preview');
      }
    } catch (err) {
      setError('Failed to load prompt preview');
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = () => {
    if (preview) {
      navigator.clipboard.writeText(preview.prompt);
      alert('Prompt copied to clipboard!');
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-gray-900">
              Prompt Preview: {phase === 'discovery' ? 'Discovery' : 'Synthesis'}
            </h2>
            {preview && (
              <p className="text-sm text-gray-600 mt-1">
                Model: {preview.model} • Max Steps: {preview.max_steps}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-2xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="px-6 py-4">
          {loading && (
            <div className="flex items-center justify-center py-12">
              <div className="text-gray-600">Loading prompt...</div>
            </div>
          )}

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <p className="text-red-800">{error}</p>
              {phase === 'synthesis' && (
                <p className="text-red-600 text-sm mt-2">
                  Tip: Run discovery first to generate items for synthesis preview.
                </p>
              )}
            </div>
          )}

          {preview && !loading && (
            <>
              <div className="mb-4 flex justify-between items-center">
                <p className="text-sm text-gray-600">
                  This is the exact prompt that will be sent to the agent.
                </p>
                <button
                  onClick={copyToClipboard}
                  className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 text-sm font-medium"
                >
                  📋 Copy to Clipboard
                </button>
              </div>

              <div className="bg-gray-50 border border-gray-300 rounded-lg p-4">
                <pre className="text-sm text-gray-800 whitespace-pre-wrap font-mono">
                  {preview.prompt}
                </pre>
              </div>

              <div className="mt-4 bg-blue-50 border border-blue-200 rounded-lg p-4">
                <h4 className="font-semibold text-blue-900 text-sm mb-2">💡 What happens next?</h4>
                <ul className="text-sm text-blue-800 space-y-1">
                  <li>
                    • The agent receives this prompt with {preview.max_steps} max tool calls
                  </li>
                  <li>
                    • It uses the <code className="bg-blue-100 px-1 rounded">web_search</code> and{' '}
                    <code className="bg-blue-100 px-1 rounded">fetch_url</code> tools
                  </li>
                  <li>
                    • It returns structured JSON via the <code className="bg-blue-100 px-1 rounded">final_answer</code> tool
                  </li>
                  <li>
                    • Results are stored in the database and displayed in the UI
                  </li>
                </ul>
              </div>
            </>
          )}
        </div>

        <div className="sticky bottom-0 bg-gray-50 border-t border-gray-200 px-6 py-4 flex justify-end">
          <button
            onClick={onClose}
            className="px-6 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 font-medium"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
