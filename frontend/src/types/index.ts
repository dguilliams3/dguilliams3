export interface Domain {
  id: string;
  name: string;
  description: string | null;
  update_frequency_hours: number;
  last_updated_at: string | null;
  created_at: string;
}

export interface DomainSummary {
  id: string;
  name: string;
  description: string | null;
  last_updated_at: string | null;
  item_count: number;
  staleness_hours: number | null;
}

export interface Item {
  id: string;
  domain_id: string;
  title: string;
  source: string;
  source_url: string | null;
  published_date: string | null;
  discovered_at: string;
  summary: string;
  significance: string;
  significance_score: number;
  raw_content?: string | null;
  embedding_id?: string | null;
}

export interface DomainUpdate {
  id: string;
  domain_id: string;
  created_at: string;
  summary: string;
  item_ids: string[];
  open_questions: string[];
  token_usage: number | null;
}

export interface DomainDetail {
  domain: Domain;
  recent_items: Item[];
  latest_update: DomainUpdate | null;
}

export interface DashboardStats {
  total_domains: number;
  total_items: number;
  total_updates: number;
  total_token_usage: number;
  items_by_domain: Record<string, number>;
  avg_significance_by_domain: Record<string, number>;
}

export interface AskRequest {
  domain_id?: string | null;
  item_id?: string | null;
  question: string;
}

export interface AskResponse {
  answer: string;
  citations: Item[];
  token_usage: number | null;
}
