import { useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import type { DomainDetail, Item } from '../types';
import { ItemCard } from './ItemCard';
import { DrillDownModal } from './DrillDownModal';

interface DomainViewProps {
  detail: DomainDetail | null;
  loading: boolean;
  onRefresh: () => void;
  onAskQuestion: (itemId: string | null, question: string) => Promise<string>;
}

export function DomainView({ detail, loading, onRefresh, onAskQuestion }: DomainViewProps) {
  const [selectedItem, setSelectedItem] = useState<Item | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = async () => {
    setRefreshing(true);
    await onRefresh();
    setTimeout(() => setRefreshing(false), 2000);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading...</div>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Select a domain to view details</div>
      </div>
    );
  }

  const lastUpdate = detail.domain.last_updated_at
    ? formatDistanceToNow(new Date(detail.domain.last_updated_at), { addSuffix: true })
    : 'Never';

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">{detail.domain.name}</h1>
          <p className="text-gray-600">{detail.domain.description}</p>
          <p className="text-sm text-gray-500 mt-1">Last updated: {lastUpdate}</p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className={`px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:bg-gray-300 font-medium ${
            refreshing ? 'animate-pulse' : ''
          }`}
        >
          {refreshing ? 'Refreshing...' : 'Refresh Now'}
        </button>
      </div>

      {/* Latest Update Summary */}
      {detail.latest_update && (
        <div className="mb-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
          <h2 className="font-semibold text-gray-900 mb-2">Latest Domain Update</h2>
          <div className="text-sm text-gray-700 whitespace-pre-wrap mb-3">
            {detail.latest_update.summary}
          </div>
          {detail.latest_update.open_questions.length > 0 && (
            <div>
              <h3 className="font-semibold text-gray-900 text-sm mb-1">Open Questions</h3>
              <ul className="list-disc list-inside text-sm text-gray-600">
                {detail.latest_update.open_questions.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Items Grid */}
      <div>
        <h2 className="font-semibold text-gray-900 mb-3">
          Recent Discoveries ({detail.recent_items.length})
        </h2>
        {detail.recent_items.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            No items discovered yet. Click "Refresh Now" to start discovery.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {detail.recent_items.map((item) => (
              <ItemCard key={item.id} item={item} onDrillDown={setSelectedItem} />
            ))}
          </div>
        )}
      </div>

      {/* Drill-down Modal */}
      {selectedItem && (
        <DrillDownModal
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
          onAsk={(question) => onAskQuestion(selectedItem.id, question)}
        />
      )}
    </div>
  );
}
