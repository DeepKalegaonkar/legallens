import { Clause, RiskFinding, RiskSeverity } from '../../core/models/document.model';

// Risk type emitted when only the broad severity model flagged a clause, i.e.
// it didn't match one of the specific risk categories.
export const GENERAL_RISK_TYPE = 'general_risk_language';

export const SEVERITY_ORDER: RiskSeverity[] = ['critical', 'high', 'medium', 'low'];

const SEVERITY_RANK: Record<RiskSeverity, number> = { critical: 0, high: 1, medium: 2, low: 3 };

// Below this the clause-type guess is too unreliable to show as a fact.
export const TYPE_CONFIDENCE_FLOOR = 0.3;

const NUMBERING = /^\s*(\d{1,2}(?:\.\d{1,2})*(?:\([a-z]+\))?)\.?\s+/;

export interface Finding {
  clause: Clause;
  label: string;
  excerpt: string;
  risk: RiskFinding;
  general: boolean;
}

export type StripTier = 'key' | 'other' | 'none';

export interface StripSegment {
  id: number;
  title: string;
  severity: RiskSeverity | null;
  tier: StripTier;
}

export function clauseLabel(clause: Clause): string {
  const match = NUMBERING.exec(clause.text);
  return match ? `Clause ${match[1]}` : `Paragraph ${clause.order_index + 1}`;
}

export function clauseExcerpt(clause: Clause): string {
  return clause.text.replace(NUMBERING, '');
}

export function humanize(slug: string): string {
  return slug.replaceAll('_', ' ');
}

export function riskTitle(riskType: string): string {
  return riskType === GENERAL_RISK_TYPE ? 'Potentially risky language' : humanize(riskType);
}

// A rule either matches or it doesn't, so it has no probability to show.
export function confidenceLabel(risk: RiskFinding): string {
  return risk.source === 'rule' ? 'Rule match' : `${Math.round(risk.confidence * 100)}% confidence`;
}

export function buildFindings(clauses: Clause[]): Finding[] {
  return clauses.flatMap((clause) =>
    clause.risks.map((risk) => ({
      clause,
      label: clauseLabel(clause),
      excerpt: clauseExcerpt(clause),
      risk,
      general: risk.risk_type === GENERAL_RISK_TYPE,
    })),
  );
}

// Most severe first; within a severity, named risk categories before the
// general model's flags; then most confident first.
export function compareFindings(a: Finding, b: Finding): number {
  return (
    SEVERITY_RANK[a.risk.severity] - SEVERITY_RANK[b.risk.severity] ||
    Number(a.general) - Number(b.general) ||
    b.risk.confidence - a.risk.confidence
  );
}

export function splitFindings(findings: Finding[]): { key: Finding[]; other: Finding[] } {
  const sorted = [...findings].sort(compareFindings);
  return { key: sorted.filter((f) => !f.general), other: sorted.filter((f) => f.general) };
}

export function countBySeverity(findings: Finding[]): Record<RiskSeverity, number> {
  const counts: Record<RiskSeverity, number> = { critical: 0, high: 0, medium: 0, low: 0 };
  for (const finding of findings) {
    counts[finding.risk.severity]++;
  }
  return counts;
}

export function topSeverity(risks: RiskFinding[]): RiskSeverity | null {
  return risks.reduce<RiskSeverity | null>(
    (best, risk) => (best === null || SEVERITY_RANK[risk.severity] < SEVERITY_RANK[best] ? risk.severity : best),
    null,
  );
}

export function buildStrip(clauses: Clause[]): StripSegment[] {
  return clauses.map((clause) => {
    const named = clause.risks.filter((risk) => risk.risk_type !== GENERAL_RISK_TYPE);
    const tier: StripTier = named.length ? 'key' : clause.risks.length ? 'other' : 'none';
    const severity = topSeverity(tier === 'key' ? named : clause.risks);
    const suffix = severity ? ` — ${severity} risk` : '';
    return { id: clause.id, title: `${clauseLabel(clause)}${suffix}`, severity, tier };
  });
}

export function isTypeUncertain(clause: Clause): boolean {
  return clause.confidence < TYPE_CONFIDENCE_FLOOR;
}

// Empty when the model isn't confident enough for the guess to be worth showing.
export function typeLabel(clause: Clause): string {
  return isTypeUncertain(clause) ? '' : `${humanize(clause.clause_type)} · ${Math.round(clause.confidence * 100)}%`;
}
