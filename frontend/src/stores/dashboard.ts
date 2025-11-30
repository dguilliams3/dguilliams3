import { create } from 'zustand';
import type { DomainSummary, DomainDetail, Item, DashboardStats } from '../types';

interface DashboardState {
  // Data
  domains: DomainSummary[];
  activeDomainId: string | null;
  activeDomainDetail: DomainDetail | null;
  stats: DashboardStats | null;

  // Loading states
  loading: {
    domains: boolean;
    domainDetail: boolean;
    stats: boolean;
  };

  // Error states
  error: string | null;

  // Actions
  setActiveDomain: (id: string) => void;
  fetchDomains: () => Promise<void>;
  fetchDomainDetail: (domainId: string) => Promise<void>;
  fetchStats: () => Promise<void>;
  refreshDomain: (domainId: string, force?: boolean) => Promise<void>;
  askQuestion: (domainId: string | null, itemId: string | null, question: string) => Promise<string>;
  searchItems: (query: string, domainId?: string | null) => Promise<Item[]>;
}

const API_BASE = '/api';

export const useDashboardStore = create<DashboardState>((set, get) => ({
  // Initial state
  domains: [],
  activeDomainId: null,
  activeDomainDetail: null,
  stats: null,
  loading: {
    domains: false,
    domainDetail: false,
    stats: false,
  },
  error: null,

  // Actions
  setActiveDomain: (id: string) => {
    set({ activeDomainId: id });
    get().fetchDomainDetail(id);
  },

  fetchDomains: async () => {
    set({ loading: { ...get().loading, domains: true }, error: null });
    try {
      const response = await fetch(`${API_BASE}/domains`);
      if (!response.ok) throw new Error('Failed to fetch domains');
      const domains = await response.json();
      set({ domains, loading: { ...get().loading, domains: false } });

      // Auto-select first domain if none selected
      if (!get().activeDomainId && domains.length > 0) {
        get().setActiveDomain(domains[0].id);
      }
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Unknown error',
        loading: { ...get().loading, domains: false }
      });
    }
  },

  fetchDomainDetail: async (domainId: string) => {
    set({ loading: { ...get().loading, domainDetail: true }, error: null });
    try {
      const response = await fetch(`${API_BASE}/domains/${domainId}`);
      if (!response.ok) throw new Error('Failed to fetch domain detail');
      const detail = await response.json();
      set({
        activeDomainDetail: detail,
        loading: { ...get().loading, domainDetail: false }
      });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Unknown error',
        loading: { ...get().loading, domainDetail: false }
      });
    }
  },

  fetchStats: async () => {
    set({ loading: { ...get().loading, stats: true }, error: null });
    try {
      const response = await fetch(`${API_BASE}/stats`);
      if (!response.ok) throw new Error('Failed to fetch stats');
      const stats = await response.json();
      set({ stats, loading: { ...get().loading, stats: false } });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Unknown error',
        loading: { ...get().loading, stats: false }
      });
    }
  },

  refreshDomain: async (domainId: string, force = false) => {
    try {
      const response = await fetch(`${API_BASE}/domains/${domainId}/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force }),
      });
      if (!response.ok) throw new Error('Failed to refresh domain');

      // Refresh domain list and detail after a short delay
      setTimeout(() => {
        get().fetchDomains();
        if (get().activeDomainId === domainId) {
          get().fetchDomainDetail(domainId);
        }
      }, 2000);
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Unknown error' });
    }
  },

  askQuestion: async (domainId: string | null, itemId: string | null, question: string) => {
    try {
      const response = await fetch(`${API_BASE}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain_id: domainId, item_id: itemId, question }),
      });
      if (!response.ok) throw new Error('Failed to ask question');
      const data = await response.json();
      return data.answer;
    } catch (error) {
      throw error;
    }
  },

  searchItems: async (query: string, domainId: string | null = null) => {
    try {
      const url = new URL(`${API_BASE}/search`, window.location.origin);
      url.searchParams.set('q', query);
      if (domainId) url.searchParams.set('domain_id', domainId);

      const response = await fetch(url.toString());
      if (!response.ok) throw new Error('Failed to search items');
      return await response.json();
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Unknown error' });
      return [];
    }
  },
}));
