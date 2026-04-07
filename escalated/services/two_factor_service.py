import base64
import hashlib
import hmac
import os
import secrets
import struct
import time


class TwoFactorService:
    PERIOD = 30
    DIGITS = 6

    def generate_secret(self):
        """Generate a 16-character base32 secret."""
        random_bytes = os.urandom(10)
        return base64.b32encode(random_bytes).decode("utf-8").rstrip("=")

    def generate_qr_uri(self, secret, email):
        """Generate an otpauth:// URI for QR code scanning."""
        from django.conf import settings

        issuer = getattr(settings, "ESCALATED_APP_NAME", "Escalated")
        return (
            f"otpauth://totp/{issuer}:{email}"
            f"?secret={secret}&issuer={issuer}&algorithm=SHA1&digits={self.DIGITS}&period={self.PERIOD}"
        )

    def verify(self, secret, code):
        """Verify a TOTP code, allowing +-1 time step for clock drift."""
        current_time = int(time.time())
        for offset in [-1, 0, 1]:
            time_step = (current_time // self.PERIOD) + offset
            generated = self._generate_totp(secret, time_step)
            if generated == code:
                return True
        return False

    def generate_recovery_codes(self):
        """Generate 8 recovery codes formatted as XXXXXXXX-XXXXXXXX."""
        codes = []
        for _ in range(8):
            part1 = secrets.token_hex(4).upper()
            part2 = secrets.token_hex(4).upper()
            codes.append(f"{part1}-{part2}")
        return codes

    def _generate_totp(self, secret, time_step):
        """Generate a TOTP code for a given time step."""
        # Pad secret for base32 decoding
        padded = secret + "=" * (-len(secret) % 8)
        key = base64.b32decode(padded, casefold=True)

        # Pack time step as big-endian 8-byte int
        msg = struct.pack(">Q", time_step)

        # HMAC-SHA1
        hmac_digest = hmac.new(key, msg, hashlib.sha1).digest()

        # Dynamic truncation
        offset = hmac_digest[-1] & 0x0F
        truncated = struct.unpack(">I", hmac_digest[offset : offset + 4])[0] & 0x7FFFFFFF

        code = truncated % (10**self.DIGITS)
        return str(code).zfill(self.DIGITS)
