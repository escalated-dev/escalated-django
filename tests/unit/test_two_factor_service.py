import pytest

from escalated.services.two_factor_service import TwoFactorService


class TestTwoFactorService:
    def test_generate_secret_returns_string(self):
        service = TwoFactorService()
        secret = service.generate_secret()
        assert isinstance(secret, str)
        assert len(secret) >= 10

    def test_generate_qr_uri(self):
        service = TwoFactorService()
        secret = service.generate_secret()
        uri = service.generate_qr_uri(secret, "user@example.com")
        assert uri.startswith("otpauth://totp/")
        assert secret in uri
        assert "user@example.com" in uri

    def test_verify_with_correct_code(self):
        service = TwoFactorService()
        secret = service.generate_secret()
        # Generate a current code
        import time
        time_step = int(time.time()) // service.PERIOD
        code = service._generate_totp(secret, time_step)
        assert service.verify(secret, code) is True

    def test_verify_with_wrong_code(self):
        service = TwoFactorService()
        secret = service.generate_secret()
        assert service.verify(secret, "000000") is False

    def test_generate_recovery_codes(self):
        service = TwoFactorService()
        codes = service.generate_recovery_codes()
        assert len(codes) == 8
        for code in codes:
            assert "-" in code
            parts = code.split("-")
            assert len(parts) == 2
            assert len(parts[0]) == 8
            assert len(parts[1]) == 8
