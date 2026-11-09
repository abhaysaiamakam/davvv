export interface CodeLensSourceMapping {
  source_file: string;
  source_symbol: string;
  line_start: number;
  line_end: number;
  function_line_start: number;
  function_line_end: number;
  is_excerpt: boolean;
  code_snippet: string;
  language: "python" | "typescript";
}

export interface CodeLensExplanationMetadata {
  explanation_id: string;
  result_type: string;
  operation_type: string;
  title: string;
  description: string;
  source_key: string;
  methodology?: string;
  formula?: string;
  inputs: string;
  outputs: string;
  limitations?: string;
  frontend_renderer?: string;
}
