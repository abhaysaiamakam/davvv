/**
 * Standard API Error Response
 */

export interface ApiErrorResponse {
  detail: string;
  status_code: number;
  error_code: string;
  timestamp: string;
}

