"""Decrypt the one-use sender address for an in-memory PowerShell pipe only."""
import base64
import ipaddress
import sys
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

try:
    key = serialization.load_pem_private_key(Path(sys.argv[1]).read_bytes(), password=None)
    ciphertext = base64.b64decode(Path(sys.argv[2]).read_bytes(), validate=True)
    value = key.decrypt(ciphertext, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    address = ipaddress.ip_address(value.decode('ascii').strip())
    if address.version != 4 or not address.is_global:
        raise ValueError('Expected one public IPv4')
    # This stdout is captured by the firewall script, not shown to the console.
    sys.stdout.write(str(address))
except Exception:
    print('Could not validate encrypted sender address.', file=sys.stderr)
    sys.exit(1)
