import os
from pathlib import Path
import uuid
import sqlite3
import atexit

TEST_DB=Path(__file__).with_name(f"auth_test_{uuid.uuid4().hex}.db")
os.environ["DAYWEAVE_DB"]=str(TEST_DB)
os.environ.pop("DATABASE_URL",None)
import sys
sys.path.insert(0,str(Path(__file__).parents[1]))
from fastapi.testclient import TestClient
from main import app,engine,item,connect
from alembic import command
from alembic.config import Config

def _cleanup_test_db():
    engine.dispose()
    TEST_DB.unlink(missing_ok=True)
atexit.register(_cleanup_test_db)

def register(client,name,email):
    return client.post("/api/v1/auth/register",json={"name":name,"email":email,"password":"correct-horse-battery-42"})

def test_private_workspace_sessions_and_csrf():
    with TestClient(app) as alice, TestClient(app) as bob:
        a=register(alice,"Alice","alice@example.test")
        assert a.status_code==200
        csrf=alice.cookies.get("dayweave_csrf")
        task=alice.post("/api/v1/tasks",json={"title":"Private task"},headers={"X-CSRF-Token":csrf})
        assert task.status_code==200
        task_id=task.json()["id"]
        assert alice.get("/api/v1/tasks").json()[0]["title"]=="Private task"
        assert alice.post("/api/v1/tasks",json={"title":"No CSRF"}).status_code==403
        assert register(bob,"Bob","bob@example.test").status_code==200
        assert bob.get("/api/v1/tasks").json()==[]
        assert bob.patch(f"/api/v1/tasks/{task_id}",json={"title":"Stolen"},headers={"X-CSRF-Token":bob.cookies.get("dayweave_csrf")}).status_code==404
        assert alice.post("/api/v1/auth/logout",headers={"X-CSRF-Token":csrf}).status_code==200
        assert alice.get("/api/v1/auth/me").status_code==401

def test_invalid_login_is_generic():
    with TestClient(app) as client:
        assert client.post("/api/v1/auth/login",json={"email":"missing@example.test","password":"incorrect"}).status_code==401

def test_ai_unavailable_is_reported_without_fake_response(monkeypatch):
    monkeypatch.delenv("OLLAMA_URL",raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL",raising=False)
    with TestClient(app) as client:
        assert register(client,"AI Test","ai@example.test").status_code==200
        csrf=client.cookies.get("dayweave_csrf")
        response=client.post("/api/v1/chat",json={"message":"Plan my day"},headers={"X-CSRF-Token":csrf})
        assert response.status_code==400
        assert "Settings" in response.json()["detail"]

def test_ai_settings_encrypt_keys_and_are_user_scoped(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("AI_CREDENTIAL_ENCRYPTION_KEY",Fernet.generate_key().decode())
    with TestClient(app) as alice, TestClient(app) as bob:
        registered=register(alice,"AI Owner","ai-owner@example.test")
        assert registered.status_code==200
        with connect() as c:c.execute("INSERT INTO user_ai_settings(user_id,provider,base_url,model,encrypted_api_key,low_token_usage,max_output_tokens,context_items,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",(registered.json()["id"],"ollama","http://localhost:11434","llama3.2",None,1,350,5,"2026-01-01T00:00:00+00:00"))
        csrf=alice.cookies.get("dayweave_csrf")
        secret="sk-test-never-return-this"
        saved=alice.put("/api/v1/ai/settings",json={"provider":"openai_compatible","base_url":"https://api.openai.com/v1","model":"gpt-4o-mini","api_key":secret,"low_token_usage":True,"max_output_tokens":160,"context_items":3},headers={"X-CSRF-Token":csrf})
        assert saved.status_code==200
        assert secret not in saved.text
        assert saved.json()["has_api_key"] is True
        stored=item("SELECT encrypted_api_key FROM user_cloud_ai_settings WHERE user_id=?",(registered.json()["id"],))["encrypted_api_key"]
        assert secret not in stored
        local=item("SELECT provider,model FROM user_ai_settings WHERE user_id=?",(registered.json()["id"],))
        assert local=={"provider":"ollama","model":"llama3.2"}
        assert saved.json()["low_token_usage"] is True
        assert saved.json()["max_output_tokens"]==160
        assert register(bob,"AI Other","ai-other@example.test").status_code==200
        other=bob.get("/api/v1/ai/settings").json()
        assert other["provider"]=="openrouter"
        assert other["has_api_key"] is False
        persisted=alice.get("/api/v1/ai/settings").json()
        assert persisted["model"]=="gpt-4o-mini"
        assert "api_key" not in persisted
        assert persisted["has_api_key"] is True

def test_fetch_models_uses_transient_key_and_real_provider_adapter(monkeypatch):
    from ai_providers import OpenAIStyleProvider
    seen={}
    def models(self):
        seen.update(provider=self.provider,key=self.api_key)
        return [{"id":"llama-3.3-70b-versatile","name":"Llama 3.3"}]
    monkeypatch.setattr(OpenAIStyleProvider,"models",models)
    with TestClient(app) as client:
        registered=register(client,"Fetch Test","fetch-test@example.test")
        csrf=client.cookies.get("dayweave_csrf")
        secret="gsk-test-never-return-this"
        response=client.post("/api/v1/ai/models",json={"provider":"groq","base_url":"https://api.groq.com/openai/v1","model":"","api_key":secret},headers={"X-CSRF-Token":csrf})
        assert response.status_code==200
        assert response.json()["models"]==[{"id":"llama-3.3-70b-versatile","name":"Llama 3.3"}]
        assert seen=={"provider":"groq","key":secret}

def test_custom_provider_configuration_persists_paths_and_auth_settings(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("AI_CREDENTIAL_ENCRYPTION_KEY",Fernet.generate_key().decode())
    with TestClient(app) as client:
        registered=register(client,"Custom Provider","custom-provider@example.test")
        csrf=client.cookies.get("dayweave_csrf")
        response=client.put("/api/v1/ai/settings",json={"provider":"custom","base_url":"https://models.example.test/api","model":"org/model-v2","api_key":"custom-secret","model_list_path":"/catalog","chat_completion_path":"/respond","auth_header":"X-API-Key","auth_scheme":""},headers={"X-CSRF-Token":csrf})
        assert response.status_code==200
        assert response.json()["model_list_path"]=="/catalog"
        assert response.json()["chat_completion_path"]=="/respond"
        assert response.json()["auth_header"]=="X-API-Key"
        assert response.json()["auth_scheme"]==""
        assert "custom-secret" not in response.text
        persisted=client.get("/api/v1/ai/settings").json()
        assert persisted["model"]=="org/model-v2"
        assert persisted["model_list_path"]=="/catalog"
        assert persisted["chat_completion_path"]=="/respond"
        assert item("SELECT COUNT(*) AS n FROM user_cloud_ai_settings WHERE user_id=?",(registered.json()["id"],))["n"]==1

def test_fetch_models_surfaces_provider_auth_and_quota_errors(monkeypatch):
    from ai_providers import OpenAIStyleProvider,ProviderError
    def unauthorized(self):raise ProviderError("The provider rejected this API key or denied access to the requested model.",401)
    monkeypatch.setattr(OpenAIStyleProvider,"models",unauthorized)
    with TestClient(app) as client:
        register(client,"Bad Key","bad-key@example.test")
        csrf=client.cookies.get("dayweave_csrf")
        response=client.post("/api/v1/ai/models",json={"provider":"groq","base_url":"https://api.groq.com/openai/v1","api_key":"invalid-secret"},headers={"X-CSRF-Token":csrf})
        assert response.status_code==401
        assert "invalid-secret" not in response.text
        assert "rejected" in response.json()["detail"]

def test_test_connection_uses_selected_model_and_transient_key(monkeypatch):
    from ai_providers import OpenAIStyleProvider
    seen={}
    def test(self,model):
        seen.update(provider=self.provider,key=self.api_key,model=model)
        return {"available":True,"model_available":True,"message":"Provider and selected model connection succeeded."}
    monkeypatch.setattr(OpenAIStyleProvider,"test",test)
    with TestClient(app) as client:
        registered=register(client,"Transient Test","transient-test@example.test")
        csrf=client.cookies.get("dayweave_csrf")
        secret="gsk-test-not-persisted"
        response=client.post("/api/v1/ai/test",json={"provider":"groq","base_url":"https://api.groq.com/openai/v1","model":"chosen-model","api_key":secret},headers={"X-CSRF-Token":csrf})
        assert response.status_code==200
        assert response.json()["model_available"] is True
        assert secret not in response.text
        assert seen=={"provider":"groq","key":secret,"model":"chosen-model"}
        assert item("SELECT COUNT(*) AS n FROM user_cloud_ai_settings WHERE user_id=?",(registered.json()["id"],))["n"]==0

def test_missing_encryption_key_blocks_cloud_save_without_persisting_secret(monkeypatch):
    monkeypatch.delenv("AI_CREDENTIAL_ENCRYPTION_KEY",raising=False)
    with TestClient(app) as client:
        registered=register(client,"No Key","no-key@example.test")
        csrf=client.cookies.get("dayweave_csrf")
        secret="sk-never-store-in-plaintext"
        response=client.put("/api/v1/ai/settings",json={"provider":"openai","base_url":"https://api.openai.com/v1","model":"gpt-test","api_key":secret},headers={"X-CSRF-Token":csrf})
        assert response.status_code==503
        assert secret not in response.text
        assert item("SELECT COUNT(*) AS n FROM user_cloud_ai_settings WHERE user_id=?",(registered.json()["id"],))["n"]==0

def test_saved_provider_and_model_drive_chat(monkeypatch):
    from ai_providers import OpenAIStyleProvider
    from cryptography.fernet import Fernet
    monkeypatch.setenv("AI_CREDENTIAL_ENCRYPTION_KEY",Fernet.generate_key().decode())
    calls=[]
    def complete(self,model,system,user_prompt,max_tokens=350):
        calls.append((self.provider,model,max_tokens))
        return "response from selected provider"
    monkeypatch.setattr(OpenAIStyleProvider,"complete",complete)
    with TestClient(app) as client:
        assert register(client,"Provider Test","provider-test@example.test").status_code==200
        csrf=client.cookies.get("dayweave_csrf")
        saved=client.put("/api/v1/ai/settings",json={"provider":"groq","base_url":"https://api.groq.com/openai/v1","model":"test-model","api_key":"not-a-real-key","low_token_usage":True,"max_output_tokens":99,"context_items":3},headers={"X-CSRF-Token":csrf})
        assert saved.status_code==200
        response=client.post("/api/v1/chat",json={"message":"Plan my day"},headers={"X-CSRF-Token":csrf})
        assert response.status_code==200
        assert response.json()["provider"]=="groq"
        assert response.json()["model"]=="test-model"
        assert response.json()["reply"]=="response from selected provider"
        assert calls==[("groq","test-model",99)]

def test_alembic_adds_ownership_without_dropping_existing_rows():
    db=Path(__file__).with_name(f"legacy_{uuid.uuid4().hex}.db")
    try:
        conn=sqlite3.connect(db)
        try:
            conn.execute("CREATE TABLE tasks(id TEXT PRIMARY KEY,title TEXT NOT NULL,description TEXT,status TEXT,priority TEXT,due_date TEXT,category TEXT,source_id TEXT,created_at TEXT NOT NULL)")
            conn.execute("INSERT INTO tasks VALUES('keep-me','Existing task','','Todo','Medium',NULL,'Personal',NULL,'2026-01-01T00:00:00+00:00')")
            conn.commit()
        finally:conn.close()
        cfg=Config(str(Path(__file__).parents[1]/"alembic.ini"))
        cfg.set_main_option("script_location",str(Path(__file__).parents[1]/"migrations"))
        cfg.set_main_option("sqlalchemy.url",f"sqlite:///{db.as_posix()}")
        command.upgrade(cfg,"head")
        conn=sqlite3.connect(db)
        try:
            row=conn.execute("SELECT id,title,user_id FROM tasks").fetchone()
            assert row==("keep-me","Existing task","legacy")
            assert conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_cloud_ai_settings'").fetchone()==("user_cloud_ai_settings",)
        finally:conn.close()
    finally:
        if db.exists():db.unlink()

def test_file_manager_upload_browse_move_download_search_and_delete(monkeypatch):
    import shutil,main
    tmp_path=Path(__file__).with_name(f"file_data_{uuid.uuid4().hex}");tmp_path.mkdir()
    monkeypatch.setattr(main,"FILE_STORAGE_ROOT",tmp_path.resolve())
    with TestClient(app) as alice, TestClient(app) as bob:
        register(alice,"File Owner","file-owner@example.test")
        headers={"X-CSRF-Token":alice.cookies.get("dayweave_csrf")}
        folder=alice.post("/api/v1/folders",json={"name":"Documents"},headers=headers)
        sub=alice.post("/api/v1/folders",json={"name":"Projects","parent_id":folder.json()["id"]},headers=headers)
        assert folder.status_code==200 and sub.status_code==200
        assert alice.patch(f"/api/v1/folders/{folder.json()['id']}",json={"parent_id":sub.json()["id"]},headers=headers).status_code==409
        sub=alice.patch(f"/api/v1/folders/{sub.json()['id']}",json={"name":"Project Files"},headers=headers)
        uploads=alice.post("/api/v1/files/upload",data={"folder_id":sub.json()["id"]},files=[("files",("notes.txt",b"private note","text/plain")),("files",("outline.md",b"# Outline","text/markdown"))],headers=headers)
        assert uploads.status_code==200 and len(uploads.json()["uploaded"])==2
        first=uploads.json()["uploaded"][0]
        contents=alice.get("/api/v1/files",params={"folder_id":sub.json()["id"]}).json()
        assert [f["name"] for f in contents["files"]]==["notes.txt","outline.md"]
        assert [b["name"] for b in contents["breadcrumbs"]]==["Home","Documents","Project Files"]
        renamed=alice.patch(f"/api/v1/files/{first['id']}",json={"name":"renamed.txt"},headers=headers)
        assert renamed.status_code==200 and renamed.json()["name"]=="renamed.txt"
        moved=alice.patch(f"/api/v1/files/{first['id']}",json={"folder_id":folder.json()["id"]},headers=headers)
        assert moved.status_code==200
        assert alice.get("/api/v1/files",params={"q":"renamed"}).json()["files"][0]["id"]==first["id"]
        downloaded=alice.get(f"/api/v1/files/{first['id']}/download")
        assert downloaded.status_code==200 and downloaded.content==b"private note"
        preview=alice.get(f"/api/v1/files/{first['id']}/preview")
        assert preview.status_code==200 and preview.content==b"private note"
        register(bob,"Other File User","other-file-user@example.test")
        assert bob.get("/api/v1/files").json()["files"]==[]
        assert bob.get("/api/v1/folders").json()["folders"]==[]
        assert bob.get(f"/api/v1/files/{first['id']}").status_code==404
        assert bob.get(f"/api/v1/files/{first['id']}/download").status_code==404
        bob_headers={"X-CSRF-Token":bob.cookies.get("dayweave_csrf")}
        assert bob.patch(f"/api/v1/files/{first['id']}",json={"name":"stolen.txt"},headers=bob_headers).status_code==404
        assert bob.delete(f"/api/v1/folders/{folder.json()['id']}",headers=bob_headers).status_code==404
        assert alice.delete(f"/api/v1/files/{first['id']}",headers=headers).status_code==200
        assert alice.get(f"/api/v1/files/{first['id']}/download").status_code==404
        assert alice.patch(f"/api/v1/folders/{sub.json()['id']}",json={"parent_id":None},headers=headers).status_code==200
        assert alice.delete(f"/api/v1/folders/{folder.json()['id']}",headers=headers).status_code==200
        assert alice.delete(f"/api/v1/folders/{sub.json()['id']}",headers=headers).status_code==200
        assert not any(path.is_file() for path in tmp_path.rglob("*"))
    shutil.rmtree(tmp_path,ignore_errors=True)

def test_file_upload_rejects_bad_content_and_requires_authentication():
    with TestClient(app) as client, TestClient(app) as anonymous:
        register(client,"File Validation","file-validation@example.test")
        headers={"X-CSRF-Token":client.cookies.get("dayweave_csrf")}
        invalid=client.post("/api/v1/files/upload",files=[("files",("payload.exe",b"not allowed","application/octet-stream"))],headers=headers)
        assert invalid.status_code==200 and invalid.json()["failed"]
        assert anonymous.get("/api/v1/files").status_code==401
        assert anonymous.get("/api/v1/folders").status_code==401
        assert anonymous.post("/api/v1/folders",json={"name":"Private"}).status_code==401

def test_memory_crud_requires_session_and_is_user_scoped():
    with TestClient(app) as alice, TestClient(app) as bob, TestClient(app) as anonymous:
        register(alice,"Memory Owner","memory-owner@example.test")
        headers={"X-CSRF-Token":alice.cookies.get("dayweave_csrf")}
        created=alice.post("/api/v1/memories",json={"title":"Writing preference","content":"Use concise language","category":"Preference","user_id":"not-the-session-user"},headers=headers)
        assert created.status_code==200
        assert created.json()["user_id"]==alice.get("/api/v1/auth/me").json()["id"]
        ident=created.json()["id"]
        assert alice.get(f"/api/v1/memories/{ident}").json()["content"]=="Use concise language"
        assert alice.get("/api/v1/memories").json()[0]["id"]==ident
        register(bob,"Other User","memory-other@example.test")
        assert bob.get("/api/v1/memories").json()==[]
        bob_headers={"X-CSRF-Token":bob.cookies.get("dayweave_csrf")}
        assert bob.get(f"/api/v1/memories/{ident}").status_code==404
        assert bob.patch(f"/api/v1/memories/{ident}",json={"title":"Stolen","content":"No"},headers=bob_headers).status_code==404
        assert bob.delete(f"/api/v1/memories/{ident}",headers=bob_headers).status_code==404
        assert anonymous.get("/api/v1/memories").status_code==401
        assert anonymous.post("/api/v1/memories",json={"title":"No","content":"session"}).status_code==401
        updated=alice.patch(f"/api/v1/memories/{ident}",json={"title":"Updated preference","content":"Keep it concise","category":"Decision","source":"Setup"},headers=headers)
        assert updated.status_code==200 and updated.json()["updated_at"]
        assert alice.delete(f"/api/v1/memories/{ident}",headers=headers).status_code==200
        assert alice.get(f"/api/v1/memories/{ident}").status_code==404
        assert alice.post("/api/v1/auth/logout",headers=headers).status_code==200
        assert alice.get("/api/v1/memories").status_code==401

def test_unowned_legacy_memories_are_not_claimed_by_first_user():
    with TestClient(app) as client:
        with connect() as c:c.execute("INSERT INTO memories(id,title,content,category,source,created_at,user_id,updated_at) VALUES(?,?,?,?,?,?,?,?)",("legacy-memory","Old","Unknown owner","Preference","","2025-01-01T00:00:00+00:00",None,None))
        register(client,"First Account","first-account@example.test")
        assert client.get("/api/v1/memories").json()==[]
        assert item("SELECT user_id FROM memories WHERE id=?",("legacy-memory",))["user_id"] is None
