"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchCurrentUser,
  logout as apiLogout,
  type UserProfile,
} from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { clearSignedIn, hasSignedInHint } from "@/lib/auth/session-hint";

export const CURRENT_USER_KEY = ["current-user"] as const;

/**
 * The signed-in user, or `null` when unauthenticated.
 *
 * The probe only runs when a session hint is present, so a never-signed-in guest
 * makes no request (and produces no console 401). A 401 despite the hint means a
 * stale/expired session: we treat it as logged-out and clear the hint so the next
 * page load does not probe again.
 */
export function useCurrentUser() {
  return useQuery<UserProfile | null>({
    queryKey: CURRENT_USER_KEY,
    enabled: hasSignedInHint(),
    queryFn: async () => {
      try {
        return await fetchCurrentUser();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          clearSignedIn();
          return null;
        }
        throw error;
      }
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: apiLogout,
    onSuccess: () => {
      clearSignedIn();
      queryClient.setQueryData(CURRENT_USER_KEY, null);
    },
  });
}
