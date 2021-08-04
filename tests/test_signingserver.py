import os
import pytest
import shutil
import logging
import datetime
import base64

from fastapi.testclient import TestClient

os.environ["CONFIG"] = os.path.join(os.path.dirname(__file__), "test_config.yaml")
from signingserver.main import app

import signingserver.crypto as crypto

logger = logging.getLogger("signer")
logger.setLevel(logging.DEBUG)

out_dir = os.path.join(os.path.dirname(__file__), "test-out")

cert_pem = None
auth_token = None
signed_req = None
keep_data = False


def load_file(filename):
    with open(os.path.join(out_dir, filename)) as fh:
        return fh.read()


def teardown_module():
    if not keep_data and os.path.exists(out_dir):
        shutil.rmtree(out_dir)


def test_invalid_domain(port):
    if os.path.exists(out_dir):
        pytest.skip("reusing existing cert, skip invalid domain check")

    os.environ["DOMAIN_OVERRIDE"] = "example.com"
    os.environ["PORT_OVERRIDE"] = port
    with pytest.raises(Exception):
        with TestClient(app) as client:
            pass


def test_inited(domain, port, keep):
    os.environ["DOMAIN_OVERRIDE"] = domain
    os.environ["PORT_OVERRIDE"] = port
    with TestClient(app) as client:
        res = sorted(os.listdir(out_dir))
        assert res == [
            "auth-token.txt",
            "cert.pem",
            "long-private-key.pem",
            "long-public-key.pem",
            "private-key.pem",
            "public-key.pem",
        ]

        global cert_pem
        cert_pem = load_file("cert.pem")

        global auth_token
        auth_token = load_file("auth-token.txt")

        if keep:
            global keep_data
            keep_data = True


def test_reload_same_cert(domain):
    with TestClient(app) as client:
        assert cert_pem == load_file("cert.pem")
        assert auth_token == load_file("auth-token.txt")


def test_sign_invalid_token(domain):
    with TestClient(app) as client:
        resp = client.post("/sign/some-data")
        assert resp.status_code == 403

        resp = client.post(
            "/sign/some-data",
            headers={
                "Authorization": "bearer " + base64.b64encode(b"abc").decode("ascii")
            },
        )
        assert resp.status_code == 403


def test_sign_valid_token(domain):
    global signed_req
    with TestClient(app) as client:
        resp = client.post(
            "/sign/some-data", headers={"Authorization": "bearer " + auth_token}
        )
        assert resp.status_code == 200
        signed_req = resp.json()


def test_verify_invalid_missing(domain):
    with TestClient(app) as client:
        req = signed_req.copy()
        req.pop("timeSignature", "")
        resp = client.post("/verify", json=req)
        assert resp.status_code == 422


def test_verify_invalid_hash(domain):
    with TestClient(app) as client:
        req = signed_req.copy()
        req["hash"] = "other data"
        resp = client.post("/verify", json=req)
        assert resp.status_code == 400


def test_verify_invalid_wrong_key(domain):
    private_key = crypto.create_ecdsa_private_key()
    public_key = private_key.public_key()
    with TestClient(app) as client:
        req = signed_req.copy()
        req["longPublicKey"] = crypto.get_public_key_pem(public_key)
        resp = client.post("/verify", json=req)
        assert resp.status_code == 400


def test_verify_wrong_cert(domain):
    with TestClient(app) as client:
        req = signed_req.copy()
        req["timestampCert"] = req["domainCert"]
        resp = client.post("/verify", json=req)
        assert resp.status_code == 400


def test_verify_invalid_bad_date(domain):
    with TestClient(app) as client:
        # date to early
        req = signed_req.copy()
        req["date"] = (
            datetime.datetime.utcnow() - datetime.timedelta(days=1)
        ).isoformat()
        resp = client.post("/verify", json=req)
        assert resp.status_code == 400

        # date to late
        req = signed_req.copy()
        req["date"] = (
            datetime.datetime.utcnow() + datetime.timedelta(days=1)
        ).isoformat()
        resp = client.post("/verify", json=req)
        assert resp.status_code == 400


def test_verify_valid(domain):
    with TestClient(app) as client:
        resp = client.post("/verify", json=signed_req)
        assert resp.status_code == 200
        assert resp.json() == {"domain": domain}