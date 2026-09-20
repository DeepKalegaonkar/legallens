import { Component, input } from '@angular/core';
import { RiskSeverity } from '../../core/models/document.model';

@Component({
  selector: 'app-risk-badge',
  standalone: true,
  template: `<span class="risk-badge" [class]="severity()">{{ severity() }}</span>`,
  styleUrl: './risk-badge.component.css',
})
export class RiskBadgeComponent {
  readonly severity = input.required<RiskSeverity>();
}
