from ai_providers import GeminiProvider,OpenAIStyleProvider,ProviderError
from urllib.error import HTTPError
from io import BytesIO
import pytest


def test_openrouter_models_include_provider_pricing(monkeypatch):
    seen={}
    def request(url,**kwargs):
        seen["url"]=url;seen.update(kwargs)
        return {"data":[{"id":"free/test","name":"Test Free","pricing":{"prompt":"0","completion":"0"}},{"id":"paid/test","pricing":{"prompt":"0.1","completion":"0.2"}}]}
    monkeypatch.setattr("ai_providers._request",request)
    result=OpenAIStyleProvider("https://openrouter.ai/api/v1","secret","openrouter").models()
    assert seen["url"].endswith("/models/user?output_modalities=text")
    assert seen["api_key"]=="secret"
    assert result==[{"id":"free/test","name":"Test Free","pricing":{"prompt":"0","completion":"0"},"free":True},{"id":"paid/test","name":"paid/test","pricing":{"prompt":"0.1","completion":"0.2"},"free":False}]


def test_gemini_uses_native_list_and_generate_content_apis(monkeypatch):
    calls=[]
    def request(url,**kwargs):
        calls.append((url,kwargs))
        if url.endswith("/models"):return {"models":[{"name":"models/gemini-2.5-flash","displayName":"Gemini Flash","supportedGenerationMethods":["generateContent"]},{"name":"models/embedding","supportedGenerationMethods":["embedContent"]}]}
        return {"candidates":[{"content":{"parts":[{"text":"OK"}]}}]}
    monkeypatch.setattr("ai_providers._request",request)
    adapter=GeminiProvider("https://generativelanguage.googleapis.com/v1beta","secret")
    assert adapter.models()==[{"id":"gemini-2.5-flash","name":"Gemini Flash"}]
    assert adapter.test("gemini-2.5-flash")["model_available"] is True
    assert calls[0][1]["headers"]=={"x-goog-api-key":"secret"}
    assert calls[1][0].endswith("/models/gemini-2.5-flash:generateContent")
    assert calls[1][1]["payload"]["generationConfig"]["maxOutputTokens"]==8


def test_groq_completion_uses_selected_model_and_token_limit(monkeypatch):
    seen={}
    def request(url,**kwargs):
        seen["url"]=url;seen.update(kwargs)
        return {"choices":[{"message":{"content":"ok"}}]}
    monkeypatch.setattr("ai_providers._request",request)
    assert OpenAIStyleProvider("https://api.groq.com/openai/v1","secret","groq").complete("model-x","system","question",77)=="ok"
    assert seen["url"].endswith("/chat/completions")
    assert seen["payload"]["model"]=="model-x"
    assert seen["payload"]["max_completion_tokens"]==77

def test_groq_model_listing_uses_official_authenticated_models_endpoint(monkeypatch):
    seen={}
    def request(url,**kwargs):
        seen.update(url=url,**kwargs)
        return {"data":[{"id":"llama-3.3-70b-versatile","name":"Llama 3.3"}]}
    monkeypatch.setattr("ai_providers._request",request)
    result=OpenAIStyleProvider("https://api.groq.com/openai/v1","groq-secret","groq").models()
    assert seen["url"]=="https://api.groq.com/openai/v1/models"
    assert seen["api_key"]=="groq-secret"
    assert result==[{"id":"llama-3.3-70b-versatile","name":"Llama 3.3"}]


def test_custom_provider_uses_configured_listing_chat_paths_and_auth(monkeypatch):
    calls=[]
    def request(url,**kwargs):
        calls.append((url,kwargs))
        if url.endswith("/catalog"):return {"models":[{"id":"org/model-v2"}]}
        return {"choices":[{"message":{"content":"ok"}}]}
    monkeypatch.setattr("ai_providers._request",request)
    adapter=OpenAIStyleProvider("https://api.example.com/v1","custom-secret","custom","/catalog","/respond","X-API-Key","")
    assert adapter.models()==[{"id":"org/model-v2","name":"org/model-v2"}]
    assert adapter.complete("org/model-v2","system","question")=="ok"
    assert calls[0][0]=="https://api.example.com/v1/catalog"
    assert calls[0][1]["headers"]=={"X-API-Key":"custom-secret"}
    assert calls[1][0]=="https://api.example.com/v1/respond"
    assert calls[1][1]["headers"]=={"X-API-Key":"custom-secret"}


def test_custom_provider_rejects_absolute_or_traversal_endpoint_paths():
    for path in ("https://example.com/models","//evil.example/models","/v1/../admin"):
        with pytest.raises(ProviderError):
            OpenAIStyleProvider("https://api.example.com/v1","secret","custom",path)


def test_cloud_urls_require_https_and_public_ip():
    for url in ("http://api.example.com/v1","https://127.0.0.1/v1"):
        try:OpenAIStyleProvider(url,"secret","custom")
        except ProviderError:pass
        else:raise AssertionError("unsafe cloud URL was accepted")


def test_rate_limit_errors_do_not_echo_response_or_key(monkeypatch):
    def rate_limited(*args,**kwargs):raise HTTPError(args[0],429,"quota exceeded secret-value",{},BytesIO(b"secret-value"))
    monkeypatch.setattr("ai_providers.urllib.request.urlopen",rate_limited)
    with pytest.raises(ProviderError) as error:OpenAIStyleProvider("https://api.openai.com/v1","secret-value","openai").models()
    assert error.value.status==429
    assert "secret-value" not in str(error.value)
