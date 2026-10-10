"""End-to-end check of a deployed Knowledge Service (run on the CVM).

    python3 e2e_check.py https://<service-domain>

Mints a 10-minute eCan session token for a synthetic test account (the same
HS256 secret the CN app's tokens use, read from llm_proxy's config, never
printed), then exercises the real chain: sign-in check, tenant + store +
product + rule creation (database writes in the service's schema),
embeddings through llm_proxy, and scoped search. Uses only the standard
library. Meant for the -test twin.
"""
import base64
import hashlib
import hmac
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

ENV_ID = "sccb0-d0gc5398xf028be6a"
TEST_SUB = "ks-e2e-test@ecan.test"


def secret() -> str:
    raw = subprocess.run(
        ["tcb", "api", "scf", "GetFunction", "-e", ENV_ID, "--json", "--body",
         json.dumps({"FunctionName": "llm_proxy", "Namespace": ENV_ID})],
        capture_output=True, text=True, check=True).stdout
    d = json.loads(raw[raw.index("{"):]).get("data", {})
    v = {x["Key"]: x["Value"] for x in (d.get("Environment") or {}).get("Variables", [])}
    return v["ECAN_JWT_SECRET"]


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def mint(sec: str) -> str:
    now = int(time.time())
    head = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = b64(json.dumps({"sub": TEST_SUB, "iat": now, "exp": now + 600}).encode())
    sig = b64(hmac.new(sec.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest())
    return f"{head}.{body}.{sig}"


def call(base, method, path, token=None, body=None):
    req = urllib.request.Request(base + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}"), round((time.time() - t0) * 1000)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), round((time.time() - t0) * 1000)


def main():
    base = sys.argv[1].rstrip("/")
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")

    s, b, ms = call(base, "GET", "/v1/health")
    check("health", s == 200 and b.get("plane") == "public", f"{b} {ms}ms")
    s, _, _ = call(base, "GET", "/v1/me", token="not-a-token")
    check("bad token rejected", s == 401)

    tok = mint(secret())
    s, me, ms = call(base, "GET", "/v1/me", tok)
    check("session token accepted", s == 200 and me["principal"]["user_id"] == TEST_SUB, f"{ms}ms")

    tenants = me.get("tenants") or []
    if tenants:
        tid = tenants[0]["id"]
    else:
        s, t, ms = call(base, "POST", "/v1/tenants", tok, {"name": "KS e2e test"})
        check("create tenant (DB write)", s == 200, f"{ms}ms {t if s != 200 else ''}")
        tid = t.get("id")
    s, st, _ = call(base, "POST", f"/v1/tenants/{tid}/stores", tok, {"name": "e2e 测试店", "platform": "tmall"})
    check("create store", s == 200)
    s, p, ms = call(base, "POST", f"/v1/tenants/{tid}/products", tok, {
        "code": "E2E-1", "title": "男士纯棉圆领短袖T恤", "attributes": {"材质": "100%棉", "产地": "广东"},
        "faq": [{"q": "会缩水吗", "a": "首次洗涤可能轻微缩水约1-2%"}],
        "listings": [{"store_id": st.get("id"), "platform_item_id": "990000001"}]})
    check("save product (embeddings via llm_proxy)", s == 200, f"{ms}ms {p if s != 200 else ''}")
    s, _, ms = call(base, "POST", f"/v1/tenants/{tid}/policies", tok,
                    {"topic": "returns", "text": "支持七天无理由退货，吊牌完好。"})
    check("save policy", s == 200, f"{ms}ms")
    s, r, ms = call(base, "POST", f"/v1/tenants/{tid}/search", tok,
                    {"query": "这件是什么材质", "platform_item_id": "990000001"})
    check("search: product fact", s == 200 and any(f["value"] == "100%棉" for f in r.get("facts", [])),
          f"{ms}ms tier={r.get('tier')}")
    s, r, ms = call(base, "POST", f"/v1/tenants/{tid}/search", tok,
                    {"query": "洗完会变小吗", "platform_item_id": "990000001"})
    check("search: paraphrased FAQ", s == 200 and any("1-2%" in f["answer"] for f in r.get("faq", [])),
          f"{ms}ms faq={[(f['question'], f['score']) for f in r.get('faq', [])]}")
    s, r, _ = call(base, "POST", f"/v1/tenants/{tid}/search", tok, {"query": "可以退货吗", "store": st.get("id")})
    check("search: store rule", s == 200 and r.get("policies"), "")
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
