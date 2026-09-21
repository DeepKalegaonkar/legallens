import { Clause, RiskFinding, RiskSeverity } from '../../core/models/document.model';
import {
  GENERAL_RISK_TYPE,
  buildFindings,
  buildStrip,
  clauseExcerpt,
  clauseLabel,
  confidenceLabel,
  countBySeverity,
  splitFindings,
  typeLabel,
} from './report.utils';

let nextId = 1;

function risk(riskType: string, severity: RiskSeverity, confidence: number): RiskFinding {
  return { id: nextId++, risk_type: riskType, severity, confidence, explanation: 'why', source: 'model' };
}

function clause(text: string, risks: RiskFinding[] = [], confidence = 0.8): Clause {
  const id = nextId++;
  return { id, order_index: id, text, clause_type: 'termination_clause', confidence, risks };
}

describe('report utils', () => {
  it('labels clauses from their numbering', () => {
    expect(clauseLabel(clause('6(c) The Lessor shall not let'))).toBe('Clause 6(c)');
    expect(clauseLabel(clause('13. Notices go here'))).toBe('Clause 13');
    expect(clauseLabel(clause('SERVICES AGREEMENT preamble'))).toMatch(/^Paragraph \d+$/);
  });

  it('strips the numbering from the excerpt', () => {
    expect(clauseExcerpt(clause('6(c) The Lessor shall not let'))).toBe('The Lessor shall not let');
  });

  it('keeps named risks as key findings, most severe and confident first', () => {
    const clauses = [
      clause('1. a', [risk('audit_rights', 'low', 0.9)]),
      clause('2. b', [risk('non_compete', 'medium', 0.6)]),
      clause('3. c', [risk('uncapped_liability', 'high', 0.5)]),
      clause('4. d', [risk('liquidated_damages', 'high', 0.8)]),
      clause('5. e', [risk(GENERAL_RISK_TYPE, 'high', 0.99)]),
    ];

    const { key, other } = splitFindings(buildFindings(clauses));

    expect(key.map((f) => f.risk.risk_type)).toEqual([
      'liquidated_damages',
      'uncapped_liability',
      'non_compete',
      'audit_rights',
    ]);
    expect(other.map((f) => f.risk.risk_type)).toEqual([GENERAL_RISK_TYPE]);
  });

  it('counts findings by severity', () => {
    const findings = buildFindings([
      clause('1. a', [risk('x', 'high', 0.9)]),
      clause('2. b', [risk('y', 'high', 0.9)]),
      clause('3. c', [risk('z', 'low', 0.9)]),
    ]);

    expect(countBySeverity(findings)).toEqual({ critical: 0, high: 2, medium: 0, low: 1 });
  });

  it('marks each clause in the risk strip as key, other, or unflagged', () => {
    const strip = buildStrip([
      clause('1. a', [risk('non_compete', 'medium', 0.9)]),
      clause('2. b', [risk(GENERAL_RISK_TYPE, 'high', 0.9)]),
      clause('3. c'),
    ]);

    expect(strip.map((s) => s.tier)).toEqual(['key', 'other', 'none']);
    expect(strip.map((s) => s.severity)).toEqual(['medium', 'high', null]);
  });

  it('shows a percentage for model findings and "Rule match" for rule findings', () => {
    expect(confidenceLabel(risk('exclusivity', 'medium', 0.784))).toBe('78% confidence');
    expect(confidenceLabel({ ...risk('auto_renewal', 'medium', 0.9), source: 'rule' })).toBe('Rule match');
  });

  it('treats rule findings like any other named risk category', () => {
    const ruleFinding: RiskFinding = { ...risk('indemnification', 'high', 0.9), source: 'rule' };
    const { key, other } = splitFindings(buildFindings([clause('9(a) The provider shall indemnify', [ruleFinding])]));

    expect(key).toHaveLength(1);
    expect(other).toHaveLength(0);
  });

  it('does not present a low-confidence clause type as fact', () => {
    expect(typeLabel(clause('1. a', [], 0.06))).toBe('');
    expect(typeLabel(clause('1. a', [], 0.74))).toBe('termination clause · 74%');
  });
});
