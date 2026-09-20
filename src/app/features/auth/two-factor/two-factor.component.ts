import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-two-factor',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './two-factor.component.html',
  styleUrl: '../auth.css',
})
export class TwoFactorComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  readonly form = this.fb.nonNullable.group({
    code: ['', [Validators.required, Validators.minLength(6)]],
  });

  readonly useRecoveryCode = signal(false);
  readonly submitting = signal(false);
  readonly errorMessage = signal<string | null>(null);

  constructor() {
    // Nothing to verify if the user got here without entering a password first.
    if (!this.auth.awaitingSecondFactor()) {
      this.router.navigate(['/login']);
    }
  }

  toggleRecoveryCode(): void {
    this.useRecoveryCode.update((current) => !current);
    this.form.reset();
    this.errorMessage.set(null);
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.submitting.set(true);
    this.errorMessage.set(null);

    this.auth.verifyTwoFactor(this.form.getRawValue().code).subscribe({
      next: () => this.router.navigate(['/dashboard']),
      error: (err) => {
        this.submitting.set(false);
        this.errorMessage.set(err?.error?.detail ?? 'Could not verify that code. Please try again.');
        // An expired sign-in can't be retried with another code.
        if (err?.status === 401 && !this.auth.awaitingSecondFactor()) {
          this.router.navigate(['/login']);
        }
      },
    });
  }

  cancel(): void {
    this.auth.cancelSecondFactor();
  }
}
