"""
Generates a local-development-only RSA keypair for signing JWTs (RS256,
Section 12.1). Run once per environment:

    python scripts/generate_dev_keys.py

Writes ./dev_keys/jwt_private.pem and ./dev_keys/jwt_public.pem (gitignored).
Pass a directory to write the pair there instead -- for a production pair,
somewhere outside the repository:

    python scripts/generate_dev_keys.py ~/mockmateai-prod-keys

Never reuse these files outside local development — staging/production keys
must come from a secrets manager, per Section 21.1.
"""
import pathlib
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "dev_keys"


def main() -> None:
    out_dir = pathlib.Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    private_path = out_dir / "jwt_private.pem"
    public_path = out_dir / "jwt_public.pem"

    if private_path.exists() and public_path.exists():
        print(f"Keys already exist at {out_dir}, skipping generation.")
        return

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)
    print(f"Wrote JWT keypair to {out_dir}")


if __name__ == "__main__":
    main()
