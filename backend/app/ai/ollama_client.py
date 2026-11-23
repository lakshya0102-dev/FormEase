"""Central FormEase AI provider client (OpenRouter by default, optional local Ollama).

All hosted free-model calls share one bounded queue and retry policy. Provider
credentials and endpoints stay on the backend; the browser never calls them.
"""
from typing import Dict, Any, List, Optional
import asyncio
import httpx
import json
import re
import time
import random
from email.utils import parsedate_to_datetime
from ..core.config import settings

class OllamaClient:
    def __init__(self, base_url: str = None, model: str = None):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.provider = settings.AI_PROVIDER.strip().lower()
        self.openrouter_url = settings.OPENROUTER_API_BASE_URL.rstrip("/")
        self.openrouter_model = settings.OPENROUTER_MODEL
        self.last_used_model = self.openrouter_model
        self.model = self.openrouter_model if self.provider == "openrouter" else (model or settings.OLLAMA_MODEL)
        self.timeout = settings.OLLAMA_TIMEOUT_SECONDS
        self.max_retries = settings.OLLAMA_MAX_RETRIES
        # Every OpenRouter caller (analysis, chat, refinement) shares this queue.
        self._request_slots = asyncio.Semaphore(
            1 if self.provider == "openrouter" and self.openrouter_model.endswith(":free")
            else max(1, settings.AI_QUEUE_CONCURRENCY)
        )
        self._pacer_lock = asyncio.Lock()
        self._last_request_started = 0.0
        self._quota_blocked_until = 0.0

    async def check_health(self) -> Dict[str, Any]:
        """
        Reports hosted-provider configuration without claiming a live connection;
        checks model installation only for the optional local Ollama provider.
        """
        if self.provider == "openrouter":
            if time.monotonic() < self._quota_blocked_until:
                return {
                    "connected": False,
                    "configured": bool(self.openrouter_model and settings.OPENROUTER_API_KEY),
                    "live_connection_verified": False,
                    "status": "quota_cooldown",
                    "model_installed": False,
                    "target_model": self.openrouter_model,
                    "detail": "OpenRouter's free daily quota was recently exhausted. Retry later."
                }
            fallback_models = [m.strip() for m in settings.OPENROUTER_FREE_FALLBACK_MODELS.split(",") if m.strip()]
            free_models_only = all(m == "openrouter/free" or m.endswith(":free") for m in [self.openrouter_model, *fallback_models])
            configured = bool(settings.OPENROUTER_API_KEY and self.openrouter_model
                              and "placeholder" not in settings.OPENROUTER_API_KEY.lower()
                              and "your-" not in settings.OPENROUTER_API_KEY.lower()
                              and "placeholder" not in self.openrouter_model.lower()
                              and "your-" not in self.openrouter_model.lower()
                              and free_models_only)
            if not settings.OPENROUTER_API_KEY or not self.openrouter_model:
                detail = "Set OPENROUTER_API_KEY and OPENROUTER_MODEL on the backend."
            elif not free_models_only:
                detail = "OpenRouter configuration contains a non-free model; only :free model IDs are permitted."
            else:
                detail = "OpenRouter is configured; no live inference check is performed by this status endpoint."
            return {
                "connected": configured,
                "configured": configured,
                "live_connection_verified": False,
                "status": "configured" if configured else "configuration_error",
                "model_installed": False,
                "target_model": self.last_used_model if configured else self.openrouter_model,
                "detail": f"{detail} Last successful model: {self.last_used_model}" if configured else detail
            }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                if res.status_code != 200:
                    return {
                        "connected": False,
                        "configured": False,
                        "live_connection_verified": False,
                        "status": "connection_error",
                        "model_installed": False,
                        "detail": f"Ollama HTTP returned status code {res.status_code}"
                    }
                
                data = res.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                
                # Check for exact or prefix match (e.g. 'llama3.2' matching 'llama3.2:latest')
                base_target = self.model.split(":")[0]
                installed = any(m == self.model or m.startswith(f"{base_target}:") for m in models)

                return {
                    "connected": True,
                    "configured": True,
                    "live_connection_verified": True,
                    "status": "connected" if installed else "model_missing",
                    "model_installed": installed,
                    "target_model": self.model,
                    "available_models": models,
                    "detail": "Ready for inference" if installed else f"Model '{self.model}' not found in Ollama. Run: ollama pull {self.model}"
                }
        except httpx.ConnectError:
            return {
                "connected": False,
                "configured": True,
                "live_connection_verified": False,
                "status": "disconnected",
                "model_installed": False,
                "detail": f"Cannot connect to Ollama at {self.base_url}. Ensure Ollama is running (`ollama serve`)."
            }
        except Exception as e:
            return {
                "connected": False,
                "configured": True,
                "live_connection_verified": False,
                "status": "error",
                "model_installed": False,
                "detail": f"Ollama connection error: {str(e)}"
            }

    async def generate(self, prompt: str, system_prompt: str = None, json_mode: bool = False) -> str:
        """
        Sends a prompt to the selected backend provider with bounded retries.
        """
        if self.provider == "openrouter":
            if time.monotonic() < self._quota_blocked_until:
                raise RuntimeError("OpenRouter free daily quota was recently exhausted. Retry later.")
            if (not settings.OPENROUTER_API_KEY or not self.openrouter_model
                    or "placeholder" in settings.OPENROUTER_API_KEY.lower()
                    or "your-" in settings.OPENROUTER_API_KEY.lower()
                    or "placeholder" in self.openrouter_model.lower()
                    or "your-" in self.openrouter_model.lower()):
                raise RuntimeError("OpenRouter is selected but OPENROUTER_API_KEY or OPENROUTER_MODEL is not configured.")
            configured_models = [self.openrouter_model] + [
                model.strip() for model in settings.OPENROUTER_FREE_FALLBACK_MODELS.split(",") if model.strip()
            ]
            if any(model != "openrouter/free" and not model.endswith(":free") for model in configured_models):
                raise RuntimeError("OpenRouter is configured to use a non-free model. Only :free model IDs are allowed.")
            models = list(dict.fromkeys(configured_models))
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            payload = {"model": self.openrouter_model, "messages": messages, "temperature": 0.2}
            last_error = "OpenRouter request failed."
            max_attempts = max(1, settings.AI_MAX_RETRIES)
            for model_index, model_id in enumerate(models):
                payload["model"] = model_id
                for attempt in range(1, max_attempts + 1):
                    try:
                        async with self._request_slots:
                            async with self._pacer_lock:
                                interval = max(0.0, settings.AI_REQUEST_INTERVAL_SECONDS)
                                delay = self._last_request_started + interval - time.monotonic()
                                if delay > 0:
                                    await asyncio.sleep(delay)
                                self._last_request_started = time.monotonic()
                            async with httpx.AsyncClient(timeout=settings.OPENROUTER_TIMEOUT_SECONDS) as client:
                                resp = await client.post(
                                    f"{self.openrouter_url}/chat/completions",
                                    json=payload,
                                    headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                                )
                        if resp.status_code == 200:
                            choices = resp.json().get("choices", [])
                            content = choices[0].get("message", {}).get("content") if choices else None
                            if isinstance(content, str) and content.strip():
                                self.last_used_model = model_id
                                return content.strip()
                            raise RuntimeError("OpenRouter returned an empty model response.")
                        if resp.status_code == 401:
                            raise RuntimeError("OpenRouter rejected the backend API key. Check OPENROUTER_API_KEY.")
                        if resp.status_code == 402:
                            raise RuntimeError("OpenRouter requires account billing or credits for this request.")
                        if resp.status_code == 429:
                            provider_error = resp.text.lower()
                            if any(term in provider_error for term in ("per day", "daily quota", "daily limit", "limit exceeded")):
                                self._quota_blocked_until = time.monotonic() + 3600
                                raise RuntimeError("OpenRouter free daily quota is exhausted. Retry after the quota resets.")
                            last_error = "OpenRouter is temporarily rate limited."
                            if attempt < max_attempts:
                                retry_after = resp.headers.get("Retry-After", "")
                                try:
                                    backoff = max(0.0, float(retry_after)) if retry_after else min(2 ** attempt, 30.0)
                                except ValueError:
                                    try:
                                        retry_at = parsedate_to_datetime(retry_after).timestamp()
                                        backoff = max(0.0, retry_at - time.time())
                                    except (TypeError, ValueError, OverflowError):
                                        backoff = min(2 ** attempt, 30.0)
                                await asyncio.sleep(backoff + random.uniform(0, min(1.0, backoff * 0.2)))
                                continue
                            break
                        if resp.status_code in (400, 403, 404):
                            last_error = f"OpenRouter rejected free model {model_id} (HTTP {resp.status_code})."
                            break
                        last_error = f"OpenRouter returned HTTP {resp.status_code}."
                    except RuntimeError:
                        raise
                    except httpx.TimeoutException:
                        last_error = "OpenRouter request timed out."
                    except httpx.RequestError:
                        last_error = "Could not connect to OpenRouter. Check backend network access."
                    if attempt < max_attempts:
                        await asyncio.sleep(min(2 ** attempt, 30.0) + random.uniform(0, 0.25))
                # Try only explicitly configured free models after bounded failure.
                if model_index < len(models) - 1:
                    continue
            raise RuntimeError(last_error)

        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2, # Low temperature for factual precision
                "top_p": 0.9,
                "num_ctx": 4096
            }
        }
        if system_prompt:
            payload["system"] = system_prompt
        if json_mode:
            payload["format"] = "json"

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        return data.get("response", "").strip()
                    else:
                        last_error = f"Ollama status {resp.status_code}: {resp.text}"
            except httpx.RequestError as e:
                last_error = f"Attempt {attempt} connection failed: {str(e)}"
            except Exception as e:
                last_error = f"Attempt {attempt} error: {str(e)}"

        raise RuntimeError(f"Ollama inference failed after {self.max_retries} attempts: {last_error}")

    async def generate_json(self, prompt: str, system_prompt: str = None) -> Any:
        """
        Generates and extracts clean JSON object or array from the model response.
        """
        raw_response = await self.generate(prompt, system_prompt=system_prompt, json_mode=True)
        # Clean potential markdown wrapping (e.g. ```json ... ```)
        cleaned = re.sub(r'^```(?:json)?\s*', '', raw_response.strip())
        cleaned = re.sub(r'\s*```$', '', cleaned.strip())

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Fallback regex extraction of first json array or object
            match = re.search(r'(\{.*\}|\[.*\])', raw_response, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            # Final fallback
            return {"raw_text": raw_response, "json_parse_warning": True}

    async def benchmark_model(self, candidate_model: str, sample_text: str) -> Dict[str, Any]:
        """
        Benchmarks candidate model for latency, throughput, and output consistency.
        """
        start = time.time()
        test_prompt = f"Summarize in two sentences:\n{sample_text[:500]}"
        old_model = self.model
        self.model = candidate_model
        try:
            response = await self.generate(test_prompt)
            duration = time.time() - start
            return {
                "model": candidate_model,
                "status": "success",
                "duration_seconds": round(duration, 3),
                "char_length": len(response),
                "response_sample": response[:120]
            }
        except Exception as e:
            return {
                "model": candidate_model,
                "status": "failed",
                "error": str(e)
            }
        finally:
            self.model = old_model

ollama_client = OllamaClient()
