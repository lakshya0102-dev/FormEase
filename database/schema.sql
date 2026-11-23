-- FormEase PostgreSQL Database Schema
-- Supabase Compatible with Row Level Security (RLS)

-- 1. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. ENUM TYPES
DO $$ BEGIN
    CREATE TYPE document_status AS ENUM ('pending', 'processing', 'completed', 'failed');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE explanation_level AS ENUM ('simple', 'balanced', 'detailed');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE supported_language AS ENUM ('en', 'hi');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE job_status AS ENUM ('queued', 'running', 'completed', 'failed', 'retrying');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 3. PROFILES TABLE (Linked 1:1 with auth.users)
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    full_name TEXT DEFAULT '',
    preferred_language supported_language DEFAULT 'en',
    preferred_depth explanation_level DEFAULT 'balanced',
    theme TEXT DEFAULT 'light',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. DOCUMENTS TABLE
CREATE TABLE IF NOT EXISTS public.documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL, -- pdf, docx, txt, text
    file_size_bytes BIGINT DEFAULT 0,
    storage_path TEXT,
    page_count INT DEFAULT 1,
    status document_status DEFAULT 'pending',
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. DOCUMENT SECTIONS
CREATE TABLE IF NOT EXISTS public.document_sections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    heading TEXT NOT NULL,
    section_index INT NOT NULL,
    page_number INT DEFAULT 1,
    raw_text TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 6. DOCUMENT CHUNKS
CREATE TABLE IF NOT EXISTS public.document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    section_id UUID REFERENCES public.document_sections(id) ON DELETE SET NULL,
    chunk_index INT NOT NULL,
    page_number INT DEFAULT 1,
    section_title TEXT DEFAULT '',
    content TEXT NOT NULL,
    token_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7. ANALYSES TABLE
CREATE TABLE IF NOT EXISTS public.analyses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    language supported_language DEFAULT 'en',
    depth explanation_level DEFAULT 'balanced',
    overview JSONB DEFAULT '{}'::jsonb,
    summary TEXT DEFAULT '',
    process_flow JSONB DEFAULT '{}'::jsonb,
    key_information JSONB DEFAULT '{}'::jsonb,
    definitions JSONB DEFAULT '[]'::jsonb,
    recommendations JSONB DEFAULT '[]'::jsonb,
    reliability_report JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 8. ANALYSIS COMPONENTS
CREATE TABLE IF NOT EXISTS public.analysis_components (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    analysis_id UUID NOT NULL REFERENCES public.analyses(id) ON DELETE CASCADE,
    component_type TEXT NOT NULL, -- overview, summary, section, process, key_info, definitions, recommendations
    heading TEXT DEFAULT '',
    original_text TEXT,
    simplified_content TEXT NOT NULL,
    source_page_start INT,
    source_page_end INT,
    risk_level TEXT DEFAULT 'low',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 9. ANALYSIS VERSIONS (Preserves history during interactive refinement)
CREATE TABLE IF NOT EXISTS public.analysis_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    component_id UUID NOT NULL REFERENCES public.analysis_components(id) ON DELETE CASCADE,
    instruction TEXT NOT NULL,
    revised_content TEXT NOT NULL,
    version_number INT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 10. CHAT CONVERSATIONS & MESSAGES
CREATE TABLE IF NOT EXISTS public.conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT DEFAULT 'Document Conversation',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    sender TEXT NOT NULL, -- 'user' or 'assistant'
    content TEXT NOT NULL,
    retrieved_chunk_id UUID REFERENCES public.document_chunks(id) ON DELETE SET NULL,
    source_passage TEXT,
    source_page INT,
    similarity_score FLOAT,
    is_weak_match BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 11. ANNOTATIONS
CREATE TABLE IF NOT EXISTS public.annotations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    highlighted_text TEXT,
    note TEXT NOT NULL,
    color TEXT DEFAULT '#fef08a',
    page_number INT DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 12. NOTIFICATIONS
CREATE TABLE IF NOT EXISTS public.notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    document_id UUID REFERENCES public.documents(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    type TEXT DEFAULT 'info', -- 'success', 'error', 'info'
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 13. FEEDBACK TABLE
CREATE TABLE IF NOT EXISTS public.feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    message_id UUID REFERENCES public.messages(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    is_positive BOOLEAN NOT NULL,
    comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 14. PROCESSING JOBS (Lightweight Database-backed Job Queue)
CREATE TABLE IF NOT EXISTS public.processing_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    status job_status DEFAULT 'queued',
    stage TEXT DEFAULT 'queued',
    progress_percentage INT DEFAULT 0,
    retry_count INT DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 15. INDEXES FOR PERFORMANCE
CREATE INDEX IF NOT EXISTS idx_documents_user ON public.documents(user_id, is_deleted);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON public.document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_sections_document ON public.document_sections(document_id);
CREATE INDEX IF NOT EXISTS idx_analyses_document ON public.analyses(document_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON public.messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_annotations_document ON public.annotations(document_id, user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON public.processing_jobs(status);

-- 16. ROW LEVEL SECURITY (RLS) POLICIES
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_sections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.analysis_components ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.analysis_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.annotations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.processing_jobs ENABLE ROW LEVEL SECURITY;

-- Standard user ownership policies
CREATE POLICY "Users access own profile" ON public.profiles FOR ALL USING (auth.uid() = id);
CREATE POLICY "Users access own documents" ON public.documents FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users access own sections" ON public.document_sections FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users access own chunks" ON public.document_chunks FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users access own analyses" ON public.analyses FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users access own components" ON public.analysis_components FOR ALL 
    USING (EXISTS (SELECT 1 FROM public.analyses a WHERE a.id = analysis_id AND a.user_id = auth.uid()));
CREATE POLICY "Users access own versions" ON public.analysis_versions FOR ALL 
    USING (EXISTS (
        SELECT 1 FROM public.analysis_components ac 
        JOIN public.analyses a ON a.id = ac.analysis_id 
        WHERE ac.id = component_id AND a.user_id = auth.uid()
    ));
CREATE POLICY "Users access own conversations" ON public.conversations FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users access own messages" ON public.messages FOR ALL 
    USING (EXISTS (SELECT 1 FROM public.conversations c WHERE c.id = conversation_id AND c.user_id = auth.uid()));
CREATE POLICY "Users access own annotations" ON public.annotations FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users access own notifications" ON public.notifications FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users access own feedback" ON public.feedback FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users access own jobs" ON public.processing_jobs FOR ALL USING (auth.uid() = user_id);

-- 17. TRIGGER: AUTO-CREATE PROFILE ON AUTH.USERS INSERT
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name)
    VALUES (
        new.id, 
        new.email, 
        COALESCE(new.raw_user_meta_data->>'full_name', '')
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 18. STORAGE POLICIES FOR PRIVATE 'documents' BUCKET
-- Ensures bucket is private and users can access strictly their own {user_id}/{document_id}.ext files
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'documents', 
    'documents', 
    false, 
    26214400, -- 25MB limit
    ARRAY['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain']
)
ON CONFLICT (id) DO UPDATE SET public = false;

-- Allow authenticated users to upload files only into their own user_id directory
DROP POLICY IF EXISTS "Users can upload own documents" ON storage.objects;
CREATE POLICY "Users can upload own documents" ON storage.objects
FOR INSERT TO authenticated WITH CHECK (
    bucket_id = 'documents' 
    AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Allow authenticated users to view/download only their own documents
DROP POLICY IF EXISTS "Users can view own documents" ON storage.objects;
CREATE POLICY "Users can view own documents" ON storage.objects
FOR SELECT TO authenticated USING (
    bucket_id = 'documents' 
    AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Allow authenticated users to update only their own documents
DROP POLICY IF EXISTS "Users can update own documents" ON storage.objects;
CREATE POLICY "Users can update own documents" ON storage.objects
FOR UPDATE TO authenticated USING (
    bucket_id = 'documents' 
    AND (storage.foldername(name))[1] = auth.uid()::text
) WITH CHECK (
    bucket_id = 'documents' 
    AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Allow authenticated users to delete only their own documents
DROP POLICY IF EXISTS "Users can delete own documents" ON storage.objects;
CREATE POLICY "Users can delete own documents" ON storage.objects
FOR DELETE TO authenticated USING (
    bucket_id = 'documents' 
    AND (storage.foldername(name))[1] = auth.uid()::text
);


