# veil/tls.py - the certificate for the pages (https://<server>:8771/).
#
# web: tls: in settings.yaml:
#   auto   a self-signed certificate made on first start in data/tls/ (veil.crt, veil.key),
#          for the server's names and addresses (web: tls_names: adds more). Browsers warn
#          once; accept it, or give the browser data/tls/veil.crt to trust.
#   {cert: path, key: path}   your own (from Oread's household CA, Let's Encrypt, ...)
#   off    plain http: only on a network you trust (passwords cross it in the clear)

import datetime as dt
import ipaddress
import logging
import os
import socket

log = logging.getLogger("router")


def files(web, data_dir):
    """(cert path, key path) to serve with, or (None, None) for plain http."""
    tls = (web or {}).get("tls", "auto")
    if tls in (False, "off", "no", None):
        return None, None
    if isinstance(tls, dict):
        return tls.get("cert"), tls.get("key")
    folder = os.path.join(data_dir, "tls")
    cert, key = os.path.join(folder, "veil.crt"), os.path.join(folder, "veil.key")
    if not (os.path.exists(cert) and os.path.exists(key)):
        try:
            make(cert, key, (web or {}).get("tls_names") or [])
        except Exception as e:
            log.info("  ! couldn't make a certificate (%s): the pages use plain http", e)
            return None, None
    return cert, key


def _names(extra):
    names = {"localhost", "127.0.0.1", socket.gethostname()}
    try:
        names.add(socket.gethostbyname(socket.gethostname()))
    except OSError:
        pass
    names.update(str(n) for n in extra)
    return sorted(n for n in names if n)


def make(cert_path, key_path, extra):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    os.makedirs(os.path.dirname(cert_path), exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    alt = []
    for n in _names(extra):
        try:
            alt.append(x509.IPAddress(ipaddress.ip_address(n)))
        except ValueError:
            alt.append(x509.DNSName(n))
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Wepwawet Veil")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName(alt), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    old = os.umask(0o077)
    try:
        with open(key_path, "wb") as f:
            f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    finally:
        os.umask(old)
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    log.info("made a self-signed certificate for the pages: %s (names: %s)", cert_path, ", ".join(_names(extra)))
