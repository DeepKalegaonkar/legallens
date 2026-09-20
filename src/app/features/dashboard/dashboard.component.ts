import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DocumentService } from '../../core/services/document.service';
import { DocumentListItem, RiskSeverity } from '../../core/models/document.model';
import { StatusBadgeComponent } from '../../shared/status-badge/status-badge.component';
import { SEVERITY_ORDER } from '../document-detail/report.utils';

interface RiskChip {
  severity: RiskSeverity;
  count: number;
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [RouterLink, StatusBadgeComponent, DatePipe],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.css',
})
export class DashboardComponent {
  private readonly documentService = inject(DocumentService);

  readonly documents = signal<DocumentListItem[]>([]);
  readonly loading = signal(true);
  readonly loadError = signal(false);

  constructor() {
    this.documentService.list().subscribe({
      next: (documents) => {
        this.documents.set(documents);
        this.loading.set(false);
      },
      error: () => {
        this.loadError.set(true);
        this.loading.set(false);
      },
    });
  }

  riskChips(document: DocumentListItem): RiskChip[] {
    return SEVERITY_ORDER.map((severity) => ({ severity, count: document.key_findings[severity] })).filter(
      (chip) => chip.count > 0,
    );
  }

  topSeverity(document: DocumentListItem): RiskSeverity | null {
    return this.riskChips(document)[0]?.severity ?? null;
  }
}
