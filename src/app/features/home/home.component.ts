import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { RiskBadgeComponent } from '../../shared/risk-badge/risk-badge.component';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [RouterLink, RiskBadgeComponent],
  templateUrl: './home.component.html',
  styleUrl: './home.component.css',
})
export class HomeComponent {
  private readonly auth = inject(AuthService);

  readonly isAuthenticated = this.auth.isAuthenticated;

  // Cursor position over the illustration, normalized to -1..1 from its center.
  readonly mouseX = signal(0);
  readonly mouseY = signal(0);

  onIllustrationMove(event: MouseEvent): void {
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    this.mouseX.set(((event.clientX - rect.left) / rect.width) * 2 - 1);
    this.mouseY.set(((event.clientY - rect.top) / rect.height) * 2 - 1);
  }

  onIllustrationLeave(): void {
    this.mouseX.set(0);
    this.mouseY.set(0);
  }
}
