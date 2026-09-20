export interface LoginResponse {
  access_token: string | null;
  token_type: string;
  mfa_required: boolean;
  mfa_token: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface TwoFactorSetup {
  secret: string;
  otpauth_uri: string;
  qr_data_uri: string;
}

export interface TwoFactorEnabled {
  recovery_codes: string[];
}
