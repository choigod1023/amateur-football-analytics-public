import ipaddress
import os
import sys

try:
    address = ipaddress.ip_address(os.environ['FOOTBALL_DEMO_PEER'])
    valid = address.version == 4 and address.is_global and not address.is_multicast
except (KeyError, ValueError):
    valid = False
sys.exit(0 if valid else 1)
