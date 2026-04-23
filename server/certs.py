"""Self-signed TLS certificate management.

Generates a long-lived cert for this Mac's Bonjour hostname + LAN IP
so the phone can connect over HTTPS. HTTPS is required to use the
device-orientation sensor API on iOS 13+, which in turn is what the
"tilt to move the cursor" feature relies on.

The cert is saved to ``./certs/`` and reused on subsequent starts as
long as the hostname/IP SANs still match. If the network changes
(new Wi-Fi → new LAN IP), we regenerate automatically so the cert
stays valid for the current network.

Why self-signed and not a real CA? This only needs to be trusted by
you and your phone, and you never expose it to the public internet.
The alternative (Let's Encrypt for a ``.local`` hostname) isn't
possible because ``.local`` is not a public DNS zone.
"""

from __future__ import annotations

import datetime
import ipaddress
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False


@dataclass
class CertPaths:
    key_path: Path
    cert_path: Path
    hostnames: List[str]
    ips: List[str]


CERT_DIR = Path(__file__).resolve().parent.parent / "certs"


def _get_mdns_hostname() -> str:
    """Return this Mac's ``.local`` hostname (e.g. ``MacBook-Air.local``),
    or an empty string if it can't be determined. Matches the banner
    in ``main.py`` so we generate a cert for the same URL users see."""
    try:
        r = subprocess.run(
            ["scutil", "--get", "LocalHostName"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if r.returncode == 0 and r.stdout.strip():
            return f"{r.stdout.strip()}.local"
    except Exception:
        pass
    return ""


def _get_lan_ip() -> str:
    """Best-effort: whatever interface the OS would use to reach the
    public internet. That's nearly always the one your phone sees too."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def _collect_sans() -> tuple[List[str], List[str]]:
    """Collect the hostnames and IPs that should be in the cert's
    Subject Alternative Name field. We always include localhost and
    127.0.0.1 so HTTPS works from the Mac itself too."""
    hostnames = ["localhost"]
    ips = ["127.0.0.1"]

    mdns = _get_mdns_hostname()
    if mdns:
        hostnames.append(mdns)

    lan = _get_lan_ip()
    if lan and lan not in ips:
        ips.append(lan)

    return hostnames, ips


def _read_existing_sans(cert_path: Path) -> tuple[List[str], List[str]]:
    """Pull DNS and IP SANs out of an existing cert so we can decide
    whether to regenerate. Returns ``([], [])`` if anything fails.

    Note: ``get_values_for_type`` returns the value directly (a ``str``
    for DNS entries, an ``ipaddress`` object for IPs) in modern
    cryptography releases — we don't need to pull ``.value`` off of
    each one. (Older releases returned ``GeneralName`` objects; doing
    so crashed with ``AttributeError: 'str' object has no attribute
    'value'`` under newer cryptography.)
    """
    try:
        cert_pem = cert_path.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_pem)
        ext = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        )
        san = ext.value
        dns = [str(n) for n in san.get_values_for_type(x509.DNSName)]
        ips = [str(n) for n in san.get_values_for_type(x509.IPAddress)]
        return dns, ips
    except Exception:
        return [], []


def ensure_cert() -> CertPaths:
    """Ensure a self-signed cert + key exist on disk and return their
    paths. Regenerates only if a *hostname* SAN is missing — LAN IP
    changes don't trigger a regen, because:

      (a) the user's phone connects via the ``.local`` Bonjour name
          (that's the URL we bake into the QR code and the bookmark),
          so a new LAN IP doesn't break the common path, and
      (b) regenerating invalidates any cert the user has already
          installed + trusted on their phone. Forcing them to re-
          install the cert every time they move to a new Wi-Fi would
          defeat the whole point of the trusted-install flow.

    Worst case: the IP URL in the banner shows a cert warning on a
    new network. The ``.local`` URL is always fine.
    """
    if not _CRYPTO_OK:
        raise RuntimeError(
            "The 'cryptography' package is required for HTTPS. "
            "Run ./run.sh to refresh dependencies."
        )

    CERT_DIR.mkdir(parents=True, exist_ok=True)
    key_path = CERT_DIR / "server.key"
    cert_path = CERT_DIR / "server.crt"

    hostnames, ips = _collect_sans()

    should_regen = not (key_path.exists() and cert_path.exists())
    if not should_regen:
        old_dns, _old_ips = _read_existing_sans(cert_path)
        missing = set(hostnames) - set(old_dns)
        if missing:
            print(f"[certs] hostname SAN added ({missing}) → regenerating cert")
            should_regen = True

    if should_regen:
        _write_new_cert(key_path, cert_path, hostnames, ips)
        print(
            f"[certs] self-signed cert written → "
            f"{cert_path.relative_to(Path.cwd()) if cert_path.is_absolute() and Path.cwd() in cert_path.parents else cert_path}"
        )

    return CertPaths(
        key_path=key_path,
        cert_path=cert_path,
        hostnames=hostnames,
        ips=ips,
    )


def _write_new_cert(
    key_path: Path,
    cert_path: Path,
    hostnames: List[str],
    ips: List[str],
) -> None:
    # 2048-bit RSA — easily good enough for a LAN cert that's re-
    # generated whenever the network changes, and fast enough to
    # generate without slowing down first-boot. EC would be smaller
    # but older iOS versions were finicky about EC-signed certs.
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Use the first hostname as the subject's CN for friendliness in
    # cert-inspector UIs (Safari shows the CN prominently when you
    # tap through the warning).
    cn = next((h for h in hostnames if h != "localhost"), "localhost")
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, cn),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Hand Control"),
    ])

    san_entries: list[x509.GeneralName] = [x509.DNSName(h) for h in hostnames]
    for ip in ips:
        try:
            san_entries.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            pass

    # 5-year validity. This is a LAN-only cert; you'll regenerate
    # naturally when the network changes, so we don't need the tight
    # 90-day validity of public certs.
    now = datetime.datetime.utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=365 * 5))
        .add_extension(
            x509.SubjectAlternativeName(san_entries),
            critical=False,
        )
        # Self-signed CA: ``ca=True`` is what makes iOS's "Certificate
        # Trust Settings" toggle (Settings → General → About → …) show
        # up and actually enable full SSL trust for the installed
        # profile. A leaf cert (``ca=False``) installs fine on iOS but
        # Safari will still refuse to treat the server as trusted —
        # which is the exact warning we're trying to eliminate.
        # ``path_length=0`` means this CA can sign its own leaf
        # certs but nothing further down a chain.
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=0),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                # Needed for ca=True — iOS rejects a CA that can't
                # sign certs as malformed, even if it's self-signed
                # and never actually issues anything.
                key_cert_sign=True,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(private_key=key, algorithm=hashes.SHA256())
    )

    key_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cert_bytes = cert.public_bytes(serialization.Encoding.PEM)

    key_path.write_bytes(key_bytes)
    # Make the key file user-only readable — we don't care about
    # exposure (it's trusted on a LAN) but it's the right habit.
    try:
        os.chmod(key_path, 0o600)
    except Exception:
        pass

    cert_path.write_bytes(cert_bytes)
