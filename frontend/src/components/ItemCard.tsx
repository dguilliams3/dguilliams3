import { formatDistanceToNow } from 'date-fns';
import type { Item } from '../types';

interface ItemCardProps {
  item: Item;
  onDrillDown: (item: Item) => void;
}

const getSignificanceBadge = (score: number): { color: string; label: string } => {
  if (score >= 0.9) return { color: 'bg-purple-100 text-purple-800', label: 'Critical' };
  if (score >= 0.7) return { color: 'bg-red-100 text-red-800', label: 'Major' };
  if (score >= 0.5) return { color: 'bg-orange-100 text-orange-800', label: 'Notable' };
  return { color: 'bg-blue-100 text-blue-800', label: 'Minor' };
};

export function ItemCard({ item, onDrillDown }: ItemCardProps) {
  const badge = getSignificanceBadge(item.significance_score);
  const discoveredAgo = formatDistanceToNow(new Date(item.discovered_at), { addSuffix: true });

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="font-semibold text-gray-900 text-sm flex-1">
          {item.source_url ? (
            <a
              href={item.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-primary-600"
            >
              {item.title}
            </a>
          ) : (
            item.title
          )}
        </h3>
        <span className={`px-2 py-1 text-xs rounded-full font-medium whitespace-nowrap ${badge.color}`}>
          {badge.label}
        </span>
      </div>

      <p className="text-sm text-gray-600 mb-3 line-clamp-3">{item.summary}</p>

      <div className="flex items-center justify-between text-xs text-gray-500">
        <div className="flex items-center gap-2">
          <span className="font-medium">{item.source}</span>
          <span>•</span>
          <span>{discoveredAgo}</span>
        </div>
        <button
          onClick={() => onDrillDown(item)}
          className="text-primary-600 hover:text-primary-700 font-medium"
        >
          Ask question →
        </button>
      </div>

      <div className="mt-3 pt-3 border-t border-gray-100">
        <p className="text-xs text-gray-600 italic line-clamp-2">{item.significance}</p>
      </div>
    </div>
  );
}
