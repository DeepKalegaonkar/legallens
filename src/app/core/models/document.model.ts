export type DocumentStatus = 'uploaded' | 'processing' | 'completed' | 'failed';
export type RiskSeverity = 'low' | 'medium' | 'high' | 'critical';

export interface RiskFinding {
  id: number;
  risk_type: string;
  severity: RiskSeverity;
  confidence: number;
  explanation: string;
  // 'model' is a statistical prediction; 'rule' is a fixed pattern match.
  source: 'model' | 'rule';
}

export interface Clause {
  id: number;
  order_index: number;
  text: string;
  clause_type: string;
  confidence: number;
  risks: RiskFinding[];
}

export interface RiskSummary {
  low: number;
  medium: number;
  high: number;
  critical: number;
}

export interface DocumentSummary {
  id: number;
  filename: string;
  status: DocumentStatus;
  uploaded_at: string;
}

export interface DocumentListItem extends DocumentSummary {
  clause_count: number;
  preview: string;
  // Findings from the named risk categories, and clauses only the general model flagged.
  key_findings: RiskSummary;
  other_flags: number;
}

export interface DocumentDetail extends DocumentSummary {
  clauses: Clause[];
  risk_summary: RiskSummary;
}
