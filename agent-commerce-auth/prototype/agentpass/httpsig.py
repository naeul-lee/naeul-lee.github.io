"""AgentPass profile of RFC 9421 HTTP Message Signatures (simplified, single signature label `ap`)."""
from __future__ import annotations

import base64
import hashlib
import re
import secrets
from dataclasses import dataclass, field

from .crypto import KeyPair, VerificationError, verify_raw

LABEL = "ap"
TAG = "agentpass"
MAX_VALIDITY = 300
CLOCK_SKEW = 60


@dataclass
class HttpRequest:
    method: str
    authority: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    def header(self, name: str) -> str | None:
        return self.headers.get(name.lower())


def content_digest(body: bytes) -> str:
    return f"sha-256=:{base64.b64encode(hashlib.sha256(body).digest()).decode()}:"


def _component_value(req: HttpRequest, name: str) -> str:
    if name == "@method":
        return req.method.upper()
    if name == "@authority":
        return req.authority.lower()
    if name == "@path":
        return req.path
    value = req.header(name)
    if value is None:
        raise VerificationError("missing_signed_header", name)
    return value


def _signature_params(components: list[str], created: int, expires: int, keyid: str, nonce: str) -> str:
    comps = " ".join(f'"{c}"' for c in components)
    return f'({comps});created={created};expires={expires};keyid="{keyid}";nonce="{nonce}";alg="ed25519";tag="{TAG}"'


def signature_base(req: HttpRequest, components: list[str], params: str) -> bytes:
    lines = [f'"{c}": {_component_value(req, c)}' for c in components]
    lines.append(f'"@signature-params": {params}')
    return "\n".join(lines).encode()


def sign_request(req: HttpRequest, key: KeyPair, signature_agent: str, now: int) -> HttpRequest:
    """Mutates and returns `req` with Content-Digest, Signature-Agent, Signature-Input and Signature."""
    req.headers = {k.lower(): v for k, v in req.headers.items()}
    req.headers["signature-agent"] = f'"{signature_agent}"'
    components = ["@method", "@authority", "@path", "signature-agent"]
    if req.body:
        req.headers["content-digest"] = content_digest(req.body)
        components.append("content-digest")
    if "agentpass-transaction" in req.headers:
        components.append("agentpass-transaction")
    params = _signature_params(components, now, now + MAX_VALIDITY, key.jkt, secrets.token_urlsafe(16))
    sig = key.sign(signature_base(req, components, params))
    req.headers["signature-input"] = f"{LABEL}={params}"
    req.headers["signature"] = f"{LABEL}=:{base64.b64encode(sig).decode()}:"
    return req


_INPUT_RE = re.compile(r'^ap=\((?P<comps>[^)]*)\)(?P<rest>.*)$')
_PARAM_RE = re.compile(r';(\w+)=("[^"]*"|\d+)')


@dataclass
class VerifiedSignature:
    keyid: str
    agent_url: str
    nonce: str
    expires: int


def verify_request(req: HttpRequest, resolve_jwk, now: int, require_body_digest: bool = True) -> VerifiedSignature:
    """Verify the `ap` signature. `resolve_jwk(agent_url, keyid)` returns the instance JWK or raises."""
    sig_input = req.header("signature-input")
    sig_header = req.header("signature")
    agent_header = req.header("signature-agent")
    if not (sig_input and sig_header and agent_header):
        raise VerificationError("missing_signature")
    m = _INPUT_RE.match(sig_input)
    if not m:
        raise VerificationError("malformed_signature_input")
    components = [c.strip('"') for c in m.group("comps").split()]
    params = {k: v.strip('"') if v.startswith('"') else int(v) for k, v in _PARAM_RE.findall(m.group("rest"))}

    for required in ("@method", "@authority", "@path", "signature-agent"):
        if required not in components:
            raise VerificationError("insufficient_coverage", required)
    if req.body and require_body_digest:
        if "content-digest" not in components:
            raise VerificationError("insufficient_coverage", "content-digest")
        if req.header("content-digest") != content_digest(req.body):
            raise VerificationError("digest_mismatch")
    if req.header("agentpass-transaction") and "agentpass-transaction" not in components:
        raise VerificationError("insufficient_coverage", "agentpass-transaction")
    if params.get("tag") != TAG:
        raise VerificationError("wrong_tag")

    created, expires = int(params["created"]), int(params["expires"])
    if expires - created > MAX_VALIDITY or now < created - CLOCK_SKEW or now > expires + CLOCK_SKEW:
        raise VerificationError("signature_expired")

    agent_url = agent_header.strip('"')
    jwk = resolve_jwk(agent_url, params["keyid"])
    raw_params = sig_input[len(LABEL) + 1:]
    sig = base64.b64decode(sig_header[len(LABEL) + 2:-1])
    verify_raw(jwk, signature_base(req, components, raw_params), sig)
    return VerifiedSignature(params["keyid"], agent_url, params["nonce"], expires)
