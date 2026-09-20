import { Component, Injector, afterNextRender, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { DocumentService } from '../../core/services/document.service';
import { DocumentDetail, RiskSeverity } from '../../core/models/document.model';
import { RiskBadgeComponent } from '../../shared/risk-badge/risk-badge.component';
import { StatusBadgeComponent } from '../../shared/status-badge/status-badge.component';
import {
  Finding,
  SEVERITY_ORDER,
  buildFindings,
  buildStrip,
  clauseExcerpt,
  clauseLabel,
  countBySeverity,
  riskTitle,
  splitFindings,
  topSeverity,
  typeLabel,
} from './report.utils';

type SeverityFilter = 'all' | RiskSeverity;

const HEADLINES: Record<RiskSeverity, string> = {
  critical: 'Critical risk',
  high: 'High risk',
  medium: 'Moderate risk',
  low: 'Low risk',
};

@Component({
  selector: 'app-document-detail',
  standalone: true,
  imports: [RouterLink, RiskBadgeComponent, StatusBadgeComponent],
  templateUrl: './document-detail.component.html',
  styleUrl: './document-detail.component.css',
})
export class DocumentDetailComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly documentService = inject(DocumentService);
  private readonly injector = inject(Injector);

  readonly report = signal<DocumentDetail | null>(null);
  readonly loading = signal(true);
  readonly loadError = signal(false);

  readonly severityFilter = signal<SeverityFilter>('all');
  readonly showOther = signal(false);
  readonly showFullDocument = signal(false);
  readonly onlyFlagged = signal(false);
  readonly expandedFindings = signal<ReadonlySet<number>>(new Set());
  readonly highlightedClauseId = signal<number | null>(null);

  readonly clauseLabel = clauseLabel;
  readonly clauseExcerpt = clauseExcerpt;
  readonly riskTitle = riskTitle;
  readonly typeLabel = typeLabel;
  readonly topSeverity = topSeverity;

  private readonly split = computed(() => splitFindings(buildFindings(this.report()?.clauses ?? [])));

  readonly keyFindings = computed(() => this.split().key);
  readonly otherFindings = computed(() => this.split().other);
  readonly keyCounts = computed(() => countBySeverity(this.keyFindings()));
  readonly otherCounts = computed(() => countBySeverity(this.otherFindings()));
  readonly strip = computed(() => buildStrip(this.report()?.clauses ?? []));

  readonly severityChips = computed(() =>
    SEVERITY_ORDER.filter((severity) => severity !== 'critical' || this.keyCounts().critical > 0),
  );

  readonly visibleKey = computed(() => this.applyFilter(this.keyFindings()));
  readonly visibleOther = computed(() => this.applyFilter(this.otherFindings()));

  readonly overall = computed(() => SEVERITY_ORDER.find((severity) => this.keyCounts()[severity] > 0) ?? null);
  readonly headline = computed(() => {
    const overall = this.overall();
    return overall ? HEADLINES[overall] : 'No specific risks flagged';
  });

  readonly visibleClauses = computed(() => {
    const clauses = this.report()?.clauses ?? [];
    return this.onlyFlagged() ? clauses.filter((clause) => clause.risks.length > 0) : clauses;
  });

  constructor() {
    const id = Number(this.route.snapshot.paramMap.get('id'));
    this.documentService.get(id).subscribe({
      next: (report) => {
        this.report.set(report);
        this.loading.set(false);
      },
      error: () => {
        this.loadError.set(true);
        this.loading.set(false);
      },
    });
  }

  toggleFilter(severity: RiskSeverity): void {
    this.severityFilter.update((current) => (current === severity ? 'all' : severity));
  }

  isExpanded(riskId: number): boolean {
    return this.expandedFindings().has(riskId);
  }

  toggleExpanded(riskId: number): void {
    this.expandedFindings.update((current) => {
      const next = new Set(current);
      if (!next.delete(riskId)) {
        next.add(riskId);
      }
      return next;
    });
  }

  jumpToClause(clauseId: number): void {
    this.showFullDocument.set(true);
    this.onlyFlagged.set(false);
    this.highlightedClauseId.set(clauseId);

    afterNextRender(
      () => document.getElementById(`clause-${clauseId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }),
      { injector: this.injector },
    );
    setTimeout(() => this.highlightedClauseId.set(null), 2400);
  }

  percent(value: number): string {
    return `${Math.round(value * 100)}%`;
  }

  private applyFilter(findings: Finding[]): Finding[] {
    const filter = this.severityFilter();
    return filter === 'all' ? findings : findings.filter((finding) => finding.risk.severity === filter);
  }
}
