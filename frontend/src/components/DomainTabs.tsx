import { formatDistanceToNow } from 'date-fns';
import type { DomainSummary } from '../types';

interface DomainTabsProps {
  domains: DomainSummary[];
  activeDomainId: string | null;
  onSelectDomain: (id: string) => void;
}

const getStalenessColor = (stalenessHours: number | null): string => {
  if (!stalenessHours) return 'bg-gray-400';
  if (stalenessHours < 24) return 'bg-green-500';
  if (stalenessHours < 48) return 'bg-yellow-500';
  return 'bg-red-500';
};

export function DomainTabs({ domains, activeDomainId, onSelectDomain }: DomainTabsProps) {
  return (
    <div className="border-b border-gray-200 bg-white">
      <div className="flex space-x-1 px-4">
        {domains.map((domain) => {
          const isActive = domain.id === activeDomainId;
          const stalenessColor = getStalenessColor(domain.staleness_hours);

          return (
            <button
              key={domain.id}
              onClick={() => onSelectDomain(domain.id)}
              className={`
                relative px-4 py-3 font-medium text-sm transition-colors
                border-b-2 flex items-center gap-2
                ${isActive
                  ? 'border-primary-600 text-primary-700 bg-primary-50'
                  : 'border-transparent text-gray-600 hover:text-gray-900 hover:bg-gray-50'
                }
              `}
            >
              <span className={`w-2 h-2 rounded-full ${stalenessColor}`} />
              <span>{domain.name}</span>
              <span className="text-xs text-gray-400">({domain.item_count})</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
