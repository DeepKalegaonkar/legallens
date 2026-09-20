import { Component, input } from '@angular/core';
import { DocumentStatus } from '../../core/models/document.model';

@Component({
  selector: 'app-status-badge',
  standalone: true,
  template: `<span class="status-badge" [class]="status()">{{ status() }}</span>`,
  styleUrl: './status-badge.component.css',
})
export class StatusBadgeComponent {
  readonly status = input.required<DocumentStatus>();
}
