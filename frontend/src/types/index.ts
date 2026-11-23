export type DocumentStatus = 'pending' | 'processing' | 'completed' | 'failed';
export type ExplanationLevel = 'simple' | 'balanced' | 'detailed';
export type SupportedLanguage = 'en' | 'hi';

export interface DocumentItem {
  id: string;
  title: string;
  file_name: string;
  file_type: string;
  file_size_bytes: number;
  page_count: number;
  status: DocumentStatus;
  is_deleted: boolean;
  deleted_at?: string | null;
  created_at: string;
  warnings?: string[];
}

export interface DocumentChunk {
  id?: string;
  chunk_index: number;
  content: string;
  page_number: number;
  section_title: string;
}

export interface SectionAnalysis {
  component_id?: string;
  heading: string;
  page_number: number;
  simplified_explanation: string;
  key_points: string[];
  potential_risks?: string[];
  risk_level?: 'low' | 'medium' | 'high';
}

export interface ProcessStep {
  step_number: number;
  title: string;
  description: string;
  summary?: string;
  brief_explanation?: string;
  key_actions?: string[];
  inputs_outputs?: {
    inputs?: string[];
    outputs?: string[];
  };
  key_components_or_actors?: string[];
  node_type?: 'start' | 'step' | 'decision' | 'end';
  inputs?: string[];
  outputs?: string[];
  condition?: string;
  page_number?: number;
  next_steps?: Array<{ title: string; condition?: string }>;
}

export interface ProcessFlow {
  has_process: boolean;
  process_title: string;
  steps: ProcessStep[];
  start_state?: string;
  end_state?: string;
  mermaid_syntax?: string;
}

export interface ConceptMap {
  central_topic?: string;
  diagram_direction?: 'TB' | 'TD' | 'BT' | 'LR' | 'RL';
  concepts: Array<{
    name: string;
    description: string;
    detailed_explanation?: string;
    key_responsibilities?: string[];
    protocols_hardware_standards?: string[];
    data_unit?: string;
    data_unit_interaction?: string;
    parent?: string;
    page_number?: number;
  }>;
  relationships: Array<{ from: string; to: string; label?: string; page_number?: number }>;
  mermaid_syntax?: string;
}

export interface DocumentAnalysis {
  component_ids?: Record<string, string>;
  language: SupportedLanguage;
  depth: ExplanationLevel;
  overview: {
    document_subject?: string;
    main_purpose?: string;
    target_audience?: string;
  };
  summary: string;
  sections: SectionAnalysis[];
  process_flow: ProcessFlow;
  concept_map?: ConceptMap;
  formulas?: Array<{ formula: string; explanation: string; page_number?: number }>;
  revision_notes?: string[];
  key_information: {
    critical_obligations?: string[];
    deadlines_and_dates?: string[];
    warnings_and_penalties?: string[];
    important_conditions?: string[];
    important_facts?: string[];
  };
  definitions: Array<{
    term: string;
    plain_definition: string;
    context_sentence?: string;
  }>;
  recommendations: Array<{
    category: string;
    recommendation: string;
    source_reference?: string;
  }>;
  reliability_report: {
    warnings: string[];
    coverage_pages: number;
    missing_sections: boolean;
    facts_grounded: boolean;
    is_complete?: boolean;
    total_batches?: number;
    completed_batches?: number[];
    failed_batches?: number[];
    module_batches?: Record<string, number[]>;
    failed_modules?: string[];
    selected_modules?: string[];
  };
}

export interface ChatMessage {
  id: string;
  question: string;
  answer: string;
  source?: {
    content: string;
    page_number: number;
    section_title: string;
    similarity_score: number;
    is_weak_match: boolean;
  };
  sources?: Array<{
    content: string;
    page_number: number;
    section_title: string;
    similarity_score: number;
    is_weak_match: boolean;
  }>;
  created_at: string;
}

export interface Annotation {
  id: string;
  document_id: string;
  highlighted_text?: string;
  note: string;
  color: string;
  page_number: number;
  created_at: string;
}
