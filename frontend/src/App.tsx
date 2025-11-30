import { useEffect } from 'react';
import { useDashboardStore } from './stores/dashboard';
import { DomainTabs } from './components/DomainTabs';
import { DomainView } from './components/DomainView';

export default function App() {
  const {
    domains,
    activeDomainId,
    activeDomainDetail,
    loading,
    error,
    fetchDomains,
    fetchStats,
    setActiveDomain,
    refreshDomain,
    askQuestion,
  } = useDashboardStore();

  useEffect(() => {
    // Initial data fetch
    fetchDomains();
    fetchStats();
  }, [fetchDomains, fetchStats]);

  const handleRefresh = () => {
    if (activeDomainId) {
      refreshDomain(activeDomainId, false);
    }
  };

  const handleAskQuestion = async (itemId: string | null, question: string) => {
    return await askQuestion(activeDomainId, itemId, question);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="px-6 py-4">
          <h1 className="text-2xl font-bold text-gray-900">Research Dashboard</h1>
          <p className="text-sm text-gray-600">
            Local-first research intelligence powered by LLM agents
          </p>
        </div>
      </header>

      {/* Error Banner */}
      {error && (
        <div className="bg-red-50 border-l-4 border-red-500 p-4">
          <p className="text-red-800">{error}</p>
        </div>
      )}

      {/* Domain Tabs */}
      {domains.length > 0 && (
        <DomainTabs
          domains={domains}
          activeDomainId={activeDomainId}
          onSelectDomain={setActiveDomain}
        />
      )}

      {/* Main Content */}
      <main>
        <DomainView
          detail={activeDomainDetail}
          loading={loading.domainDetail}
          onRefresh={handleRefresh}
          onAskQuestion={handleAskQuestion}
        />
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-gray-200 mt-12">
        <div className="px-6 py-4 text-center text-sm text-gray-600">
          Research Dashboard v0.1.0 • Built with FastAPI, SmolAgents, and React
        </div>
      </footer>
    </div>
  );
}
