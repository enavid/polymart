"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchCurrentUser,
  logout as apiLogout,
  type UserProfile,
} from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";

export const CURRENT_USER_KEY = ["current-user"] as const;

/**
 * The signed-in user, or `null` when unauthenticated. A 401 is an expected
 * "logged out" state, not an error — anything else propagates.
 */
export function useCurrentUser() {
  return useQuery<UserProfile | null>({
    queryKey: CURRENT_USER_KEY,
    queryFn: async () => {
      try {
        return await fetchCurrentUser();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
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
      queryClient.setQueryData(CURRENT_USER_KEY, null);
    },
  });
}
