"""
Supabase client provider and database accessor for FormEase.
Handles connection to Supabase PostgreSQL and Private Supabase Storage.
Ensures concurrency-safe, request-scoped client initialization with the authenticated user's JWT.
"""
from typing import Optional
from fastapi import HTTPException, Depends, status
from backend.app.core.config import settings
from backend.app.core.security import get_current_user

_mock_client_override = None
_service_role_client = None

def get_authenticated_supabase_client(token: str):
    """
    Creates a request-scoped Supabase client attached with the authenticated user's verified JWT.
    Guarantees concurrency safety so concurrent requests on different threads/tasks
    do not overwrite each other's credentials.
    """
    global _mock_client_override
    if _mock_client_override is not None:
        return _mock_client_override

    if (
        not settings.SUPABASE_URL
        or not settings.SUPABASE_ANON_KEY
        or "placeholder" in settings.SUPABASE_URL
        or "placeholder" in settings.SUPABASE_ANON_KEY
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase database is not configured. Please configure SUPABASE_URL and SUPABASE_ANON_KEY in your environment."
        )

    try:
        from supabase import create_client, ClientOptions
        options = ClientOptions(headers={"Authorization": f"Bearer {token}"})
        return create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_ANON_KEY,
            options=options
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to initialize scoped Supabase client: {str(e)}"
        )

def get_user_db(current_user: dict = Depends(get_current_user)):
    """
    FastAPI dependency that returns a request-scoped Supabase client
    authenticated with the current user's verified JWT.
    Ensures auth.uid() in PostgreSQL RLS evaluates to the authenticated user's ID.
    """
    token = current_user.get("token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials."
        )
    return get_authenticated_supabase_client(token)

def get_supabase_client():
    """
    Returns unauthenticated public Supabase client using Anon Key.
    Used only for public non-user-scoped operations if any.
    """
    global _mock_client_override
    if _mock_client_override is not None:
        return _mock_client_override

    if (
        not settings.SUPABASE_URL
        or not settings.SUPABASE_ANON_KEY
        or "placeholder" in settings.SUPABASE_URL
        or "placeholder" in settings.SUPABASE_ANON_KEY
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase database is not configured. Please configure SUPABASE_URL and SUPABASE_ANON_KEY in your environment."
        )

    try:
        from supabase import create_client
        return create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_ANON_KEY
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to initialize Supabase client: {str(e)}"
        )

def get_supabase_admin_client():
    """
    Returns elevated Supabase client with Service Role Key for backend workers.
    Must never be exposed to the client or frontend.
    """
    global _service_role_client
    if _service_role_client is not None:
        return _service_role_client

    if (
        not settings.SUPABASE_URL
        or not settings.SUPABASE_SERVICE_ROLE_KEY
        or "placeholder" in settings.SUPABASE_URL
        or "placeholder" in settings.SUPABASE_SERVICE_ROLE_KEY
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase Admin credentials are not configured."
        )

    try:
        from supabase import create_client
        _service_role_client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY
        )
        return _service_role_client
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to initialize Supabase Admin client: {str(e)}"
        )

def set_test_supabase_client(client):
    """
    Test helper for injecting mock Supabase client during automated tests.
    """
    global _mock_client_override
    _mock_client_override = client
