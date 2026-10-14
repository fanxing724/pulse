#!/usr/bin/env python3
"""Create a private configuration seed without overwriting existing credentials."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='.state/config.json')
    parser.add_argument('--origin', default='', help='Public HTTPS origin, e.g. https://pulse.example.com')
    args = parser.parse_args()
    if args.origin:
        origin = urlsplit(args.origin)
        if origin.scheme != 'https' or not origin.netloc or origin.path not in ('', '/') or origin.query or origin.fragment or origin.username or origin.password:
            parser.error('--origin must be an HTTPS origin without credentials, query or path')
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    salt = secrets.token_hex(16)
    body = {'password_salt': salt,
            'password_hash': hashlib.pbkdf2_hmac('sha256', b'admin', bytes.fromhex(salt), 200000).hex(),
            'must_change_password': True, 'public_origin': args.origin.rstrip('/'), 'origin_secret': ''}
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        parser.error('Configuration already exists; nothing was overwritten')
    with os.fdopen(fd, 'w') as f:
        json.dump(body, f, indent=2)
        f.write('\n')
    print(f'Created {path}; initial password: admin. Set your own password after login.')

if __name__ == '__main__':
    main()
