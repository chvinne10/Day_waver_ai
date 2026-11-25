"""Per-user provider adapters for supported hosted model APIs."""
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
import ipaddress, json, re, socket, urllib.request


@dataclass
class ProviderError(Exception):
    message: str
    status: int = 503
    def __str__(self): return self.message


PROVIDER_BASES={
    "openrouter":"https://openrouter.ai/api/v1",
    "groq":"https://api.groq.com/openai/v1",
    "gemini":"https://generativelanguage.googleapis.com/v1beta",
    "xai":"https://api.x.ai/v1",
    "openai":"https://api.openai.com/v1",
    "cerebras":"https://api.cerebras.ai/v1",
    "together":"https://api.together.xyz/v1",
    "custom":"https://api.openai.com/v1",
    "openai_compatible":"https://api.openai.com/v1", # existing saved configurations
}
CLOUD_PROVIDERS=set(PROVIDER_BASES)-{"openai_compatible"}


def normalize_base_url(url: str, *, cloud: bool) -> str:
    url=(url or "").strip().rstrip("/")
    parsed=urlparse(url)
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProviderError("Enter a valid provider base URL.",422)
    if cloud and parsed.scheme!="https":raise ProviderError("Cloud provider URLs must use HTTPS.",422)
    if not cloud and parsed.scheme not in ("http","https"):raise ProviderError("Provider URL must use HTTP or HTTPS.",422)
    if cloud:
        try:
            address=ipaddress.ip_address(parsed.hostname)
            if not address.is_global:raise ProviderError("Cloud provider URL must use a public hostname.",422)
        except ValueError:pass
    return url


def _request(url, *, payload=None, api_key=None, headers=None, timeout=12):
    data=None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers={"Accept":"application/json"}
    if data is not None:request_headers["Content-Type"]="application/json"
    if api_key:request_headers["Authorization"]="Bearer "+api_key
    request_headers.update(headers or {})
    request=urllib.request.Request(url,data=data,headers=request_headers)
    try:
        with urllib.request.urlopen(request,timeout=timeout) as response:return json.loads(response.read())
    except HTTPError as e:
        if e.code in (401,403):raise ProviderError("The provider rejected this API key or denied access to the requested model.",e.code)
        if e.code==404:raise ProviderError("The selected model or provider endpoint was not found.",404)
        if e.code==429:raise ProviderError("The provider rate limit or quota was reached. Wait or choose another model.",429)
        if e.code>=500:raise ProviderError("The AI provider is temporarily unavailable.",503)
        raise ProviderError(f"The AI provider returned HTTP {e.code}.",502)
    except (URLError,TimeoutError,socket.timeout):raise ProviderError("Could not connect to the AI provider. Check its URL and availability.",503)
    except (json.JSONDecodeError,UnicodeDecodeError):raise ProviderError("The AI provider returned an invalid response.",502)


class OpenAIStyleProvider:
    """OpenAI-compatible chat API used by OpenAI, Groq, xAI, OpenRouter and custom URLs."""
    def __init__(self,base_url,api_key,provider="custom",model_list_path="/models",chat_completion_path="/chat/completions",auth_header="Authorization",auth_scheme="Bearer"):
        self.base_url=normalize_base_url(base_url,cloud=True);self.api_key=api_key;self.provider=provider
        self.model_list_path=_relative_endpoint(model_list_path,"model listing")
        self.chat_completion_path=_relative_endpoint(chat_completion_path,"chat completion")
        if not auth_header or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+",auth_header) or auth_header.lower() in {"host","content-length","connection"}:
            raise ProviderError("Enter a valid authentication header name.",422)
        self.auth_header=auth_header;self.auth_scheme=auth_scheme.strip()
        if self.auth_scheme and not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+",self.auth_scheme):
            raise ProviderError("Enter a valid authentication scheme.",422)
        if not api_key:raise ProviderError("Save an API key for the selected cloud provider first.",400)
    def _headers(self):
        if self.provider!="custom" and self.auth_header=="Authorization" and self.auth_scheme=="Bearer":return None
        return {self.auth_header:(self.auth_scheme+" " if self.auth_scheme else "")+self.api_key}
    def models(self):
        endpoint="/models/user?output_modalities=text" if self.provider=="openrouter" and self.model_list_path=="/models" else self.model_list_path
        kwargs={"headers":self._headers()} if self._headers() is not None else {"api_key":self.api_key}
        payload=_request(self.base_url+endpoint,timeout=18,**kwargs)
        models=[]
        entries=payload.get("data",payload.get("models",[])) if isinstance(payload,dict) else []
        for model in entries if isinstance(entries,list) else []:
            if not isinstance(model,dict):continue
            if not isinstance(model.get("id"),str):continue
            entry={"id":model["id"],"name":model.get("name") or model["id"]}
            pricing=model.get("pricing")
            if isinstance(pricing,dict):
                entry["pricing"]={k:pricing[k] for k in ("prompt","completion") if k in pricing}
                entry["free"]=all(str(pricing.get(k,""))=="0" for k in ("prompt","completion"))
            models.append(entry)
        return models
    def complete(self,model,system,user,max_tokens=350):
        token_field="max_completion_tokens" if self.provider=="groq" else "max_tokens"
        payload={"model":model,"messages":[{"role":"system","content":system},{"role":"user","content":user}],token_field:max_tokens,"stream":False}
        kwargs={"headers":self._headers()} if self._headers() is not None else {"api_key":self.api_key}
        data=_request(self.base_url+self.chat_completion_path,payload=payload,timeout=75,**kwargs)
        choices=data.get("choices") or [];content=choices[0].get("message",{}).get("content") if choices else None
        if not isinstance(content,str):raise ProviderError("The AI provider returned an invalid completion.",502)
        return content
    def test(self,model):
        self.complete(model,"Reply with OK.","Connection test.",8)
        return {"available":True,"model_available":True,"message":"Provider and selected model connection succeeded."}


def _relative_endpoint(value,label):
    from urllib.parse import urlparse
    value=(value or "").strip()
    parsed=urlparse(value)
    if not value.startswith("/") or value.startswith("//") or parsed.scheme or parsed.fragment or ".." in parsed.path.split("/"):
        raise ProviderError(f"Enter a valid relative {label} endpoint path.",422)
    return value


class GeminiProvider:
    """Google Gemini native generateContent and models.list API."""
    def __init__(self,base_url,api_key):
        self.base_url=normalize_base_url(base_url,cloud=True);self.api_key=api_key
        if not api_key:raise ProviderError("Save a Gemini API key first.",400)
    @property
    def headers(self):return {"x-goog-api-key":self.api_key}
    def models(self):
        payload=_request(self.base_url+"/models",headers=self.headers,timeout=18)
        models=[]
        for model in payload.get("models",[]):
            if "generateContent" not in model.get("supportedGenerationMethods",[]):continue
            ident=model.get("name","").removeprefix("models/")
            if ident:models.append({"id":ident,"name":model.get("displayName") or ident})
        return models
    def complete(self,model,system,user,max_tokens=350):
        model=model.removeprefix("models/")
        payload={"systemInstruction":{"parts":[{"text":system}]},"contents":[{"role":"user","parts":[{"text":user}]}],"generationConfig":{"maxOutputTokens":max_tokens}}
        data=_request(self.base_url+"/models/"+model+":generateContent",headers=self.headers,payload=payload,timeout=75)
        parts=((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        content="".join(p.get("text","") for p in parts if isinstance(p.get("text"),str))
        if not content:raise ProviderError("Gemini returned no text. Check the selected model and its access.",502)
        return content
    def test(self,model):
        self.complete(model,"Reply with OK.","Connection test.",8)
        return {"available":True,"model_available":True,"message":"Gemini and selected model connection succeeded."}
