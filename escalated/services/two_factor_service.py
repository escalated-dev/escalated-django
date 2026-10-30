"""
Two-factor authentication (ADR 2026-10-29-configurable-access-features):
TOTP (RFC 6238: SHA-1, 6 digits, 30 s steps) through pyotp, with one step of
drift either side, plus single-use recovery codes.
"""

import hmac
import os
import secrets
import time

import pyotp

TRUE_VALUES = {"1", "true", "yes", "on"}


class TwoFactorService:
    PERIOD = 30
    DIGITS = 6
    WINDOW = 1

    def generate_secret(self):
        """A random 32-character base32 secret (160 bits, the RFC 4226 recommendation)."""
        return pyotp.random_base32(32)

    def generate_qr_uri(self, secret, email):
        """The otpauth:// URI an authenticator app reads."""
        issuer = self.issuer()
        return (
            f"otpauth://totp/{issuer}:{email}"
            f"?secret={secret}&issuer={issuer}&algorithm=SHA1&digits={self.DIGITS}&period={self.PERIOD}"
        )

    def code_step(self, secret, code, now=None):
        """The time step a code is valid for right now (one step of drift either side), or None."""
        code = "".join(str(code or "").split())
        if len(code) != self.DIGITS or not code.isdigit():
            return None
        now = int(now if now is not None else time.time())
        totp = pyotp.TOTP(secret, digits=self.DIGITS, interval=self.PERIOD)
        for offset in (0, -1, 1):
            moment = now + offset * self.PERIOD
            if hmac.compare_digest(totp.at(moment), code):
                return moment // self.PERIOD
        return None

    def verify(self, secret, code):
        """Whether the code is valid for the secret right now (no replay check)."""
        return self.code_step(secret, code) is not None

    def verify_and_consume(self, two_factor, code):
        """
        Check a code for an enrolment and record its time step, refusing a step
        at or before the last one accepted, so a code works once.
        """
        from django.db.models import Q

        from escalated.models import TwoFactor

        step = self.code_step(two_factor.secret, code)
        if step is None:
            return False
        updated = (
            TwoFactor.objects.filter(pk=two_factor.pk)
            .filter(Q(last_used_step__isnull=True) | Q(last_used_step__lt=step))
            .update(last_used_step=step)
        )
        if updated != 1:
            return False
        two_factor.last_used_step = step
        return True

    def use_recovery_code(self, two_factor, code):
        """Use a recovery code: True, and it is removed, when it matches one."""
        given = str(code or "").strip().upper()
        if not given:
            return False
        codes = list(two_factor.recovery_codes or [])
        for index, candidate in enumerate(codes):
            if hmac.compare_digest(str(candidate).upper().encode(), given.encode()):
                codes.pop(index)
                two_factor.recovery_codes = codes
                two_factor.save(update_fields=["recovery_codes", "updated_at"])
                return True
        return False

    def generate_recovery_codes(self):
        """Eight recovery codes formatted as XXXXXXXX-XXXXXXXX."""
        return [f"{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}" for _ in range(8)]

    @staticmethod
    def issuer():
        from django.conf import settings

        configured = ((getattr(settings, "ESCALATED", {}) or {}).get("TWO_FACTOR", {}) or {}).get("ISSUER")
        return (
            configured
            or os.environ.get("ESCALATED_TWO_FACTOR_ISSUER")
            or getattr(settings, "ESCALATED_APP_NAME", "Escalated")
        )

    @staticmethod
    def required():
        """
        Whether staff must enrol: the ``two_factor_required`` setting once saved,
        else ``ESCALATED["TWO_FACTOR"]["REQUIRED"]`` / ESCALATED_TWO_FACTOR_REQUIRED.
        Only while the two-factor switch is on.
        """
        from django.conf import settings

        from escalated.access import feature_enabled
        from escalated.models import EscalatedSetting

        if not feature_enabled("two_factor"):
            return False
        configured = ((getattr(settings, "ESCALATED", {}) or {}).get("TWO_FACTOR", {}) or {}).get("REQUIRED")
        if configured is None:
            configured = os.environ.get("ESCALATED_TWO_FACTOR_REQUIRED")
        fallback = configured is True or str(configured or "").strip().lower() in TRUE_VALUES
        stored = EscalatedSetting.get("two_factor_required")
        if stored in (None, ""):
            return fallback
        return str(stored).strip().lower() in TRUE_VALUES

    @staticmethod
    def confirmed_for(user):
        from escalated.models import TwoFactor

        if not user or not getattr(user, "is_authenticated", False):
            return None
        return TwoFactor.objects.filter(user=user, confirmed_at__isnull=False).first()
