"""
API Endpoint Integration Tests for FormEase — Supabase Integration & RLS Authorization.
Tests:
- Unauthenticated requests return 401 Unauthorized
- Missing bearer tokens rejected
- Health & AI status endpoints
- Document upload and retrieval with authenticated test user
- Valid document status values ('pending', 'processing', 'completed', 'failed')
- Feedback submission authorized only for user's own messages
- Rejection of feedback targeting another user's message (404/denied)
"""
import unittest
from unittest.mock import MagicMock
import sys
import os
import uuid
import time
from types import SimpleNamespace
from jose import jwt
from fastapi.testclient import TestClient
from fastapi import HTTPException, Request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.main import app
from backend.app.core.config import settings
from backend.app.core.database import set_test_supabase_client

TEST_SECRET = "test-supa-secret-at-least-32-bytes-long-for-hs256!"

def create_valid_token(user_id: str) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": f"user_{user_id[:8]}@formease.local",
        "aud": "authenticated",
        "role": "authenticated",
        "iat": now,
        "exp": now + 3600
    }
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")

class TestAPIEndpoints(unittest.TestCase):
    def setUp(self):
        self.original_secret = settings.SUPABASE_JWT_SECRET
        settings.SUPABASE_JWT_SECRET = TEST_SECRET
        self.client = TestClient(app)
        self.user_a_id = str(uuid.uuid4())
        self.user_b_id = str(uuid.uuid4())
        self.token_a = create_valid_token(self.user_a_id)
        self.token_b = create_valid_token(self.user_b_id)
        self.auth_headers_a = {"Authorization": f"Bearer {self.token_a}"}
        self.auth_headers_b = {"Authorization": f"Bearer {self.token_b}"}

    def tearDown(self):
        settings.SUPABASE_JWT_SECRET = self.original_secret
        set_test_supabase_client(None)

    def test_health_endpoint(self):
        res = self.client.get("/api/v1/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["project"], "FormEase")

    def test_openrouter_status_reports_configuration_not_live_connectivity(self):
        from backend.app.ai.ollama_client import OllamaClient
        from backend.app.core.config import settings
        import asyncio

        original = (
            settings.AI_PROVIDER,
            settings.OPENROUTER_API_KEY,
            settings.OPENROUTER_MODEL,
            settings.OPENROUTER_FREE_FALLBACK_MODELS,
        )
        try:
            settings.AI_PROVIDER = "openrouter"
            settings.OPENROUTER_API_KEY = "test-only-key"
            settings.OPENROUTER_MODEL = "unit-test/model:free"
            settings.OPENROUTER_FREE_FALLBACK_MODELS = ""
            client = OllamaClient()
            status = asyncio.run(client.check_health())
            self.assertTrue(status["configured"])
            self.assertFalse(status["live_connection_verified"])
            self.assertFalse(status["model_installed"])
            self.assertIn("no live inference check", status["detail"])
        finally:
            (settings.AI_PROVIDER, settings.OPENROUTER_API_KEY, settings.OPENROUTER_MODEL,
             settings.OPENROUTER_FREE_FALLBACK_MODELS) = original

    def test_global_error_handler_does_not_reflect_exception_text(self):
        from backend.app.main import global_exception_handler
        request = Request({"type": "http", "method": "GET", "path": "/", "headers": [],
                           "query_string": b"", "server": ("test", 80), "client": ("test", 1),
                           "scheme": "http", "http_version": "1.1"})
        import asyncio
        response = asyncio.run(global_exception_handler(request, RuntimeError("secret sentinel")))
        self.assertNotIn(b"secret sentinel", response.body)

    def test_upload_rejects_oversized_body_during_stream_read(self):
        from backend.app.api.v1.documents import upload_document
        class OversizedUpload:
            filename = "oversized.txt"
            content_type = "text/plain"
            def __init__(self):
                self.remaining = b"x" * (1024 * 1024 + 1)
            async def read(self, size):
                result, self.remaining = self.remaining[:size], self.remaining[size:]
                return result

        original_limit = settings.MAX_UPLOAD_SIZE_MB
        settings.MAX_UPLOAD_SIZE_MB = 1
        try:
            import asyncio
            with self.assertRaises(HTTPException) as error:
                asyncio.run(upload_document(OversizedUpload(), {"id": self.user_a_id}, MagicMock()))
            self.assertEqual(error.exception.status_code, 413)
        finally:
            settings.MAX_UPLOAD_SIZE_MB = original_limit

    def test_vercel_upload_respects_platform_request_body_limit(self):
        from backend.app.api.v1.documents import upload_document

        class OversizedUpload:
            filename = "oversized.txt"
            content_type = "text/plain"

            def __init__(self):
                self.remaining = 18 * 1024 * 1024 + 1

            async def read(self, size):
                chunk_size = min(size, self.remaining)
                self.remaining -= chunk_size
                return b"x" * chunk_size

        original_limit = settings.MAX_UPLOAD_SIZE_MB
        settings.MAX_UPLOAD_SIZE_MB = 100
        try:
            import asyncio
            with self.assertRaises(HTTPException) as error:
                asyncio.run(upload_document(OversizedUpload(), {"id": self.user_a_id}, MagicMock()))
            self.assertEqual(error.exception.status_code, 413)
            self.assertEqual(error.exception.detail, "File exceeds the 18 MB upload limit.")
        finally:
            settings.MAX_UPLOAD_SIZE_MB = original_limit

    def test_chat_request_rate_limit_is_per_user_and_returns_retry_after(self):
        import asyncio
        from backend.app.api.v1.chat import _check_chat_rate_limit, _chat_request_times
        from fastapi import HTTPException
        from backend.app.core.config import settings
        user_id = f"rate-test-{uuid.uuid4()}"
        old_limit = settings.AI_USER_CHAT_REQUESTS_PER_MINUTE
        settings.AI_USER_CHAT_REQUESTS_PER_MINUTE = 1
        try:
            asyncio.run(_check_chat_rate_limit(user_id))
            with self.assertRaises(HTTPException) as error:
                asyncio.run(_check_chat_rate_limit(user_id))
            self.assertEqual(error.exception.status_code, 429)
            self.assertIn("Retry-After", error.exception.headers)
        finally:
            settings.AI_USER_CHAT_REQUESTS_PER_MINUTE = old_limit
            _chat_request_times.pop(user_id, None)

    def test_chat_route_sends_retrieved_original_passage_to_ai_and_returns_page_source(self):
        import asyncio
        from unittest.mock import AsyncMock, patch
        from backend.app.api.v1.chat import chat_with_document
        from backend.app.schemas.common import ChatQueryRequest

        document_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        source_text = (
            "The parties agree to the obligations below. The employee performs assigned work, "
            "and the employer pays wages each month. This agreement governs the duties and "
            "responsibilities of both parties."
        )

        class Query:
            def __init__(self, database, table):
                self.database, self.table_name = database, table
                self.write = None
            def select(self, *args): return self
            def eq(self, *args): return self
            def order(self, *args, **kwargs): return self
            def limit(self, *args): return self
            def insert(self, value):
                self.write = value
                return self
            def execute(self):
                if self.write is not None:
                    self.database.writes.setdefault(self.table_name, []).append(self.write)
                return SimpleNamespace(data=self.database.rows.get(self.table_name, []))

        class Database:
            def __init__(self):
                self.rows = {
                    "documents": [{"id": document_id, "title": "Agreement"}],
                    "document_chunks": [{
                        "id": "source-chunk", "document_id": document_id, "user_id": user_id,
                        "chunk_index": 1, "page_number": 3, "section_title": "Terms", "content": source_text
                    }],
                    "analyses": [], "analysis_components": [], "conversations": [], "messages": []
                }
                self.writes = {}
            def table(self, name): return Query(self, name)

        database = Database()
        generate = AsyncMock(return_value="The agreement states work and payment duties. [Sources: Page 3]")
        with patch("backend.app.api.v1.chat.ollama_client.generate", new=generate):
            result = asyncio.run(chat_with_document(
                document_id, ChatQueryRequest(question="What is the main purpose of this document?"),
                {"id": user_id}, database
            ))

        prompt = generate.call_args.args[0]
        self.assertIn(source_text, prompt)
        self.assertIn("Page: 3", prompt)
        self.assertEqual(result["sources"][0]["chunk_id"], "source-chunk")
        self.assertEqual(result["sources"][0]["page_number"], 3)
        self.assertEqual(len(database.writes["messages"]), 2)

        sparse_source = (
            " ".join(["The document contains instructions for completing the required process."] * 30)
            + " The employer is responsible for the annual payment. "
            + " ".join(["Further details and conditions apply to this arrangement."] * 30)
        )
        database.rows["document_chunks"] = [{
            "id": "sparse-source", "document_id": document_id, "user_id": user_id,
            "chunk_index": 1, "page_number": 8, "section_title": "Payment", "content": sparse_source
        }]
        generate.reset_mock()
        generate.return_value = "The employer is responsible for annual payment. [Sources: Page 8]"
        with patch("backend.app.api.v1.chat.ollama_client.generate", new=generate):
            weak_match = asyncio.run(chat_with_document(
                document_id, ChatQueryRequest(question="Which part discusses the employer?"),
                {"id": user_id}, database
            ))
        self.assertTrue(generate.await_count == 1)
        self.assertIn("The employer is responsible for the annual payment", generate.call_args.args[0])
        self.assertTrue(weak_match["sources"][0]["is_weak_match"])
        self.assertEqual(weak_match["sources"][0]["page_number"], 8)

        generate.reset_mock()
        with patch("backend.app.api.v1.chat.ollama_client.generate", new=generate):
            unrelated = asyncio.run(chat_with_document(
                document_id, ChatQueryRequest(question="What temperature should I bake a chocolate cake?"),
                {"id": user_id}, database
            ))
        generate.assert_not_awaited()
        self.assertIn("does not contain", unrelated["answer"])

    def test_unauthenticated_requests_return_401(self):
        res_docs = self.client.get("/api/v1/documents")
        self.assertEqual(res_docs.status_code, 401)

        res_trash = self.client.get("/api/v1/documents/trash")
        self.assertEqual(res_trash.status_code, 401)

        res_content = self.client.get(f"/api/v1/documents/{uuid.uuid4()}/content")
        self.assertEqual(res_content.status_code, 401)

        res_chat = self.client.post(f"/api/v1/documents/{uuid.uuid4()}/chat", json={"question": "What is this?"})
        self.assertEqual(res_chat.status_code, 401)

    def test_invalid_bearer_token_returns_401(self):
        bad_headers = {"Authorization": "Bearer not-a-valid-jwt-token"}
        res = self.client.get("/api/v1/documents", headers=bad_headers)
        self.assertEqual(res.status_code, 401)

    def test_authenticated_document_list_with_mock_db(self):
        mock_db = MagicMock()
        set_test_supabase_client(mock_db)

        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq_user = MagicMock()
        mock_eq_deleted = MagicMock()
        mock_order = MagicMock()

        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_eq_user
        mock_eq_user.eq.return_value = mock_eq_deleted
        mock_eq_deleted.order.return_value = mock_order

        mock_order.execute.return_value = MagicMock(data=[
            {"id": str(uuid.uuid4()), "user_id": self.user_a_id, "title": "Rental Agreement", "status": "pending"}
        ])

        res = self.client.get("/api/v1/documents", headers=self.auth_headers_a)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("documents", data)
        self.assertEqual(len(data["documents"]), 1)
        self.assertEqual(data["documents"][0]["title"], "Rental Agreement")
        self.assertEqual(data["documents"][0]["status"], "pending")

    def test_original_document_content_is_streamed_for_owner(self):
        mock_db = MagicMock()
        set_test_supabase_client(mock_db)
        document_id = str(uuid.uuid4())
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
            "title": "notice.pdf",
            "file_type": "pdf",
            "storage_path": f"{self.user_a_id}/{document_id}.pdf"
        }])
        mock_db.storage.from_.return_value.download.return_value = b"%PDF-test-content"

        response = self.client.get(f"/api/v1/documents/{document_id}/content", headers=self.auth_headers_a)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertEqual(response.content, b"%PDF-test-content")
        mock_db.storage.from_.return_value.download.assert_called_once_with(f"{self.user_a_id}/{document_id}.pdf")

    def test_feedback_authorization_own_message_success(self):
        mock_db = MagicMock()
        set_test_supabase_client(mock_db)

        message_id = str(uuid.uuid4())
        mock_msg_table = MagicMock()
        mock_fb_table = MagicMock()

        def table_router(tname):
            if tname == "messages":
                return mock_msg_table
            return mock_fb_table

        mock_db.table.side_effect = table_router

        # Simulate message verification finding user's message
        select_mock = MagicMock()
        eq_id = MagicMock()
        eq_user = MagicMock()

        mock_msg_table.select.return_value = select_mock
        select_mock.eq.return_value = eq_id
        eq_id.eq.return_value = eq_user
        eq_user.execute.return_value = MagicMock(data=[{"id": message_id}])

        mock_fb_table.insert.return_value.execute.return_value = MagicMock()

        res = self.client.post(
            f"/api/v1/messages/{message_id}/feedback",
            headers=self.auth_headers_a,
            json={"is_positive": True, "comment": "Clear explanation"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "recorded")

    def test_feedback_authorization_rejects_other_user_message(self):
        mock_db = MagicMock()
        set_test_supabase_client(mock_db)

        other_user_msg_id = str(uuid.uuid4())
        mock_msg_table = MagicMock()

        mock_db.table.return_value = mock_msg_table
        select_mock = MagicMock()
        eq_id = MagicMock()
        eq_user = MagicMock()

        mock_msg_table.select.return_value = select_mock
        select_mock.eq.return_value = eq_id
        eq_id.eq.return_value = eq_user
        # Empty set returned because message does not belong to user_a
        eq_user.execute.return_value = MagicMock(data=[])

        res = self.client.post(
            f"/api/v1/messages/{other_user_msg_id}/feedback",
            headers=self.auth_headers_a,
            json={"is_positive": False, "comment": "Unauthorized attempt"}
        )
        self.assertEqual(res.status_code, 404)
        self.assertIn("not belong", res.json()["detail"])

if __name__ == "__main__":
    unittest.main()
