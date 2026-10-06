"""Prépare des secrets privés et une autorité locale, sans modifier Windows."""
import argparse
from datetime import datetime, timedelta, timezone
import getpass
import ipaddress
import json
from pathlib import Path
import secrets
import sys
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.security import hash_password


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", default="192.168.50.1")
    args = parser.parse_args()
    address = ipaddress.ip_address(args.ip)
    directory = ROOT / "secrets"
    if (directory/"app.json").exists():
        print("Configuration déjà présente : aucun secret remplacé.")
        return
    directory.mkdir(exist_ok=True)
    (directory/"tls").mkdir(exist_ok=True)
    password = secrets.token_urlsafe(18)
    broker, device, health, postgres, vision = [secrets.token_urlsafe(32) for _ in range(5)]
    config = {"password_hash": hash_password(password), "vision_token": vision, "mqtt_password": broker,
        "origins": ["https://localhost", "https://127.0.0.1", f"https://{address}", "http://127.0.0.1:8000", "http://localhost:8000", "http://127.0.0.1:5173", "http://localhost:5173"],
        "simulation": True, "secure_cookies": True}
    now = datetime.now(timezone.utc)
    ca_key, server_key = [rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2)]
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SENTINEL-X Local Workshop CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False, data_encipherment=False,
            key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True).sign(ca_key, hashes.SHA256()))
    server = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SENTINEL-X")]))
        .issuer_name(ca_name).public_key(server_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=180))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.DNSName("mosquitto"), x509.IPAddress(ipaddress.ip_address("127.0.0.1")), x509.IPAddress(address)]), critical=False)
        .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False).sign(ca_key, hashes.SHA256()))
    for path, value in [("ca.crt", ca.public_bytes(serialization.Encoding.PEM)), ("tls/ca.crt", ca.public_bytes(serialization.Encoding.PEM)),
        ("tls/server.crt", server.public_bytes(serialization.Encoding.PEM)),
        ("ca.key", ca_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())),
        ("tls/server.key", server_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())),
        ("broker-public.pem", server_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))]:
        (directory/path).write_bytes(value)
    (directory/"mqtt-passwords.txt").write_text(f"backend:{broker}\nsentinel-x-01:{device}\nhealth:{health}\n", encoding="utf-8")
    (directory/"compose.env").write_text(f"POSTGRES_PASSWORD={postgres}\nMQTT_HEALTH_PASSWORD={health}\n", encoding="utf-8")
    (directory/"operator.txt").write_text(f"Identifiant : operateur\nMot de passe : {password}\n", encoding="utf-8")
    (directory/"device.json").write_text(json.dumps({"mqtt_user":"sentinel-x-01","mqtt_password":device,"broker_ip":str(address),"port":8883}, indent=2), encoding="utf-8")
    (directory/"app.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    print("Configuration et certificats générés. Identifiants : secrets/operator.txt (privé).")
    print("Installer secrets/ca.crt sur les postes de démonstration ; ne jamais distribuer ca.key.")


if __name__ == "__main__":
    main()
