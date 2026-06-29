import { apiGet, apiPost } from "@/lib/api/client";

export interface UserProfile {
  id: number;
  phone_number: string;
  email: string;
  full_name: string;
  is_staff: boolean;
}

export type OtpPurpose = "registration" | "password_reset";

export interface RegisterInput {
  phone_number: string;
  code: string;
  password: string;
  full_name?: string;
  email?: string;
}

export interface ResetPasswordInput {
  phone_number: string;
  code: string;
  new_password: string;
}

export interface DetailResponse {
  detail: string;
}

export function login(
  phone_number: string,
  password: string,
): Promise<UserProfile> {
  return apiPost<UserProfile>("/auth/login/", { phone_number, password });
}

export function logout(): Promise<void> {
  return apiPost<void>("/auth/logout/");
}

export function refresh(): Promise<void> {
  return apiPost<void>("/auth/refresh/");
}

export function fetchCurrentUser(): Promise<UserProfile> {
  return apiGet<UserProfile>("/auth/me/");
}

export function requestOtp(
  phone_number: string,
  purpose: OtpPurpose,
): Promise<DetailResponse> {
  return apiPost<DetailResponse>("/auth/otp/request/", { phone_number, purpose });
}

export function register(input: RegisterInput): Promise<UserProfile> {
  return apiPost<UserProfile>("/auth/register/", input);
}

export function resetPassword(
  input: ResetPasswordInput,
): Promise<DetailResponse> {
  return apiPost<DetailResponse>("/auth/password-reset/", input);
}
