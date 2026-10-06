"""Génère firmware/sentinel_x/secrets.h à partir des secrets créés par scripts/setup.py.

Usage (depuis la racine du dépôt, sur le PC qui possède le dossier secrets/) :
    python scripts/firmware_secrets.py --ssid "NOM_DU_WIFI"
Le mot de passe Wi-Fi est demandé sans écho (il n'apparaît pas dans l'historique du terminal).

Sources lues : secrets/device.json (identifiant, mot de passe MQTT, IP du broker)
               secrets/ca.crt      (autorité de certification locale, publique)
Le fichier produit est ignoré par Git (firmware/sentinel_x/.gitignore).
"""
import argparse
import getpass
import ipaddress
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "firmware" / "sentinel_x" / "secrets.h"


def c_string(value: str) -> str:
    """Littéral C sûr (guillemets et antislashs échappés)."""
    if any(ord(c) < 32 for c in value):
        sys.exit("Caractère de contrôle interdit dans une valeur.")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ssid", required=True, help="Nom du Wi-Fi de la table (2,4 GHz)")
    parser.add_argument("--broker-ip", help="IP du PC serveur si elle diffère de celle de secrets/device.json")
    parser.add_argument("--secrets-dir", default=str(ROOT / "secrets"), help="Dossier produit par scripts/setup.py")
    parser.add_argument("--force", action="store_true", help="Remplacer un secrets.h existant")
    args = parser.parse_args()

    secrets_dir = Path(args.secrets_dir)
    device_file, ca_file = secrets_dir / "device.json", secrets_dir / "ca.crt"
    for path in (device_file, ca_file):
        if not path.exists():
            sys.exit(f"Introuvable : {path}. Lancer d'abord scripts/setup.py sur le PC serveur, "
                     "ou indiquer --secrets-dir vers une copie de device.json et ca.crt.")
    if OUTPUT.exists() and not args.force:
        sys.exit(f"{OUTPUT} existe déjà : ajouter --force pour le remplacer.")

    device = json.loads(device_file.read_text(encoding="utf-8"))
    ca = ca_file.read_text(encoding="utf-8").strip()
    if "BEGIN CERTIFICATE" not in ca or ")PEM" in ca:
        sys.exit("secrets/ca.crt ne ressemble pas à un certificat PEM.")
    broker_ip = args.broker_ip or device["broker_ip"]
    ipaddress.IPv4Address(broker_ip)  # refuse une IP invalide
    if device.get("mqtt_user") != "sentinel-x-01":
        sys.exit("device.json : mqtt_user inattendu (attendu : sentinel-x-01, cf. ACL Mosquitto).")

    wifi_password = getpass.getpass(f"Mot de passe du Wi-Fi '{args.ssid}' : ")
    if not 8 <= len(wifi_password) <= 63:
        sys.exit("Un mot de passe WPA2 fait entre 8 et 63 caractères.")

    content = f"""#pragma once
// GÉNÉRÉ par scripts/firmware_secrets.py — NE PAS VERSIONNER (ignoré par Git)
#define WIFI_SSID       {c_string(args.ssid)}
#define WIFI_PASSWORD   {c_string(wifi_password)}
#define MQTT_BROKER_IP  {c_string(broker_ip)}
#define MQTT_PORT       {int(device.get("port", 8883))}
#define MQTT_USER       {c_string(device["mqtt_user"])}
#define MQTT_PASSWORD   {c_string(device["mqtt_password"])}

static const char MQTT_CA_CERT[] = R"PEM(
{ca}
)PEM";
"""
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"Écrit : {OUTPUT.relative_to(ROOT)} (broker {broker_ip}:{device.get('port', 8883)})")
    print("Ce fichier contient des secrets : ne pas le commiter, ne pas l'envoyer sur une messagerie.")


if __name__ == "__main__":
    main()
