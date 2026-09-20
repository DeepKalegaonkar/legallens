import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';
import { API_BASE_URL } from '../api-config';
import { LoginResponse, TokenResponse, TwoFactorEnabled, TwoFactorSetup } from '../models/auth.model';
import { User } from '../models/user.model';

const TOKEN_KEY = 'clause_platform_token';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly tokenSignal = signal<string | null>(this.readStoredToken());
  // Proof of a correct password, held in memory only while the user enters their 2FA code.
  private readonly pendingMfaToken = signal<string | null>(null);

  readonly isAuthenticated = computed(() => this.tokenSignal() !== null);
  readonly awaitingSecondFactor = computed(() => this.pendingMfaToken() !== null);

  get token(): string | null {
    return this.tokenSignal();
  }

  register(email: string, password: string): Observable<User> {
    return this.http.post<User>(`${API_BASE_URL}/auth/register`, { email, password });
  }

  login(email: string, password: string): Observable<LoginResponse> {
    const body = new URLSearchParams();
    body.set('username', email);
    body.set('password', password);

    return this.http
      .post<LoginResponse>(`${API_BASE_URL}/auth/login`, body.toString(), {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })
      .pipe(
        tap((response) => {
          if (response.access_token) {
            this.setToken(response.access_token);
          } else {
            this.pendingMfaToken.set(response.mfa_token);
          }
        }),
      );
  }

  verifyTwoFactor(code: string): Observable<TokenResponse> {
    return this.http
      .post<TokenResponse>(`${API_BASE_URL}/auth/login/2fa`, { mfa_token: this.pendingMfaToken(), code })
      .pipe(
        tap((response) => {
          this.pendingMfaToken.set(null);
          this.setToken(response.access_token);
        }),
      );
  }

  cancelSecondFactor(): void {
    this.pendingMfaToken.set(null);
  }

  me(): Observable<User> {
    return this.http.get<User>(`${API_BASE_URL}/auth/me`);
  }

  setupTwoFactor(): Observable<TwoFactorSetup> {
    return this.http.post<TwoFactorSetup>(`${API_BASE_URL}/auth/2fa/setup`, {});
  }

  enableTwoFactor(code: string): Observable<TwoFactorEnabled> {
    return this.http.post<TwoFactorEnabled>(`${API_BASE_URL}/auth/2fa/enable`, { code });
  }

  disableTwoFactor(code: string): Observable<void> {
    return this.http.post<void>(`${API_BASE_URL}/auth/2fa/disable`, { code });
  }

  logout(): void {
    this.setToken(null);
  }

  private readStoredToken(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  }

  private setToken(token: string | null): void {
    this.tokenSignal.set(token);
    try {
      if (token) {
        localStorage.setItem(TOKEN_KEY, token);
      } else {
        localStorage.removeItem(TOKEN_KEY);
      }
    } catch {
      // Ignore storage errors (e.g. private browsing mode).
    }
  }
}
