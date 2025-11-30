import { useState } from 'react';
import type { Item } from '../types';

interface DrillDownModalProps {
  item: Item;
  onClose: () => void;
  onAsk: (question: string) => Promise<string>;
}

export function DrillDownModal({ item, onClose, onAsk }: DrillDownModalProps) {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleAsk = async () => {
    if (!question.trim()) return;

    setLoading(true);
    try {
      const result = await onAsk(question);
      setAnswer(result);
    } catch (error) {
      setAnswer('Error: Failed to get answer');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg max-w-3xl w-full max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-start justify-between">
          <div className="flex-1">
            <h2 className="text-xl font-bold text-gray-900 mb-1">{item.title}</h2>
            <p className="text-sm text-gray-500">
              {item.source} • Score: {item.significance_score.toFixed(2)}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-2xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="px-6 py-4">
          <div className="mb-4">
            <h3 className="font-semibold text-gray-900 mb-2">Summary</h3>
            <p className="text-gray-700">{item.summary}</p>
          </div>

          <div className="mb-4">
            <h3 className="font-semibold text-gray-900 mb-2">Significance</h3>
            <p className="text-gray-700">{item.significance}</p>
          </div>

          {item.source_url && (
            <div className="mb-6">
              <a
                href={item.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary-600 hover:text-primary-700 text-sm font-medium"
              >
                View source →
              </a>
            </div>
          )}

          <div className="border-t border-gray-200 pt-4">
            <h3 className="font-semibold text-gray-900 mb-3">Ask a question about this item</h3>

            <div className="flex gap-2 mb-4">
              <input
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleAsk()}
                placeholder="What are the implications of this finding?"
                className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                disabled={loading}
              />
              <button
                onClick={handleAsk}
                disabled={loading || !question.trim()}
                className="px-6 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:bg-gray-300 disabled:cursor-not-allowed font-medium"
              >
                {loading ? 'Asking...' : 'Ask'}
              </button>
            </div>

            {answer && (
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                <h4 className="font-semibold text-gray-900 mb-2">Answer</h4>
                <div className="text-gray-700 whitespace-pre-wrap">{answer}</div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
