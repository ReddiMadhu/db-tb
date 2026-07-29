"use client";

import { useQuery, useMutation, useQueryClient, UseQueryOptions, UseMutationOptions } from "@tanstack/react-query";
import { useToast } from "@/components/ui/ToastProvider";

export interface ApiResponse<T = any> {
  success: boolean;
  message?: string;
  data?: T;
  warnings?: string[];
  errors?: string[];
  requestId?: string;
}

// Redact sensitive header values or credentials in responses/logs
export function maskSensitiveData<T>(data: T): T {
  if (!data) return data;
  const str = JSON.stringify(data);
  const masked = str
    .replace(/(dapi-[a-zA-Z0-9_-]{10,})/g, "dapi-••••••••••••")
    .replace(/("token"|"password"|"api_key"|"authorization"|"key")\s*:\s*"[^"]+"/gi, '$1:"••••••••"');
  try {
    return JSON.parse(masked);
  } catch {
    return data;
  }
}

export function useApiQuery<T>(
  queryKey: string[],
  fetcher: () => Promise<T>,
  options?: Omit<UseQueryOptions<T, Error, T, string[]>, "queryKey" | "queryFn">
) {
  return useQuery<T, Error, T, string[]>({
    queryKey,
    queryFn: async () => {
      const result = await fetcher();
      return maskSensitiveData(result);
    },
    retry: 2,
    staleTime: 1000 * 30, // 30 seconds cache
    ...options,
  });
}

export function useApiMutation<TData = any, TVariables = void, TContext = unknown>(
  mutationFn: (variables: TVariables) => Promise<TData>,
  options?: UseMutationOptions<TData, Error, TVariables, TContext>
) {
  const queryClient = useQueryClient();

  return useMutation<TData, Error, TVariables, TContext>({
    mutationFn: async (vars: TVariables) => {
      const res = await mutationFn(vars);
      return maskSensitiveData(res);
    },
    onSettled: () => {
      queryClient.invalidateQueries();
    },
    ...options,
  });
}
