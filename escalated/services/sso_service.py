import base64
import hashlib
import hmac
import json
import struct
import time
import xml.etree.ElementTree as ET


class SsoValidationError(Exception):
    pass


class SsoService:
    CONFIG_KEYS = [
        "sso_provider",
        "sso_entity_id",
        "sso_url",
        "sso_certificate",
        "sso_attr_email",
        "sso_attr_name",
        "sso_attr_role",
        "sso_jwt_secret",
        "sso_jwt_algorithm",
    ]

    DEFAULTS = {
        "sso_provider": "none",
        "sso_entity_id": "",
        "sso_url": "",
        "sso_certificate": "",
        "sso_attr_email": "email",
        "sso_attr_name": "name",
        "sso_attr_role": "role",
        "sso_jwt_secret": "",
        "sso_jwt_algorithm": "HS256",
    }

    SAML_NS = {
        "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
        "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    }

    def get_config(self):
        """Get all SSO configuration values."""
        from escalated.models import EscalatedSetting

        config = {}
        for key in self.CONFIG_KEYS:
            try:
                setting = EscalatedSetting.objects.get(key=key)
                config[key] = setting.value
            except EscalatedSetting.DoesNotExist:
                config[key] = self.DEFAULTS.get(key, "")
        return config

    def save_config(self, data):
        """Save SSO configuration values."""
        from escalated.models import EscalatedSetting

        for key in self.CONFIG_KEYS:
            if key in data:
                EscalatedSetting.objects.update_or_create(
                    key=key,
                    defaults={"value": data[key]},
                )

    def is_enabled(self):
        """Check if SSO is enabled (provider != 'none')."""
        return self.get_provider() != "none"

    def get_provider(self):
        """Get the current SSO provider."""
        from escalated.models import EscalatedSetting

        try:
            return EscalatedSetting.objects.get(key="sso_provider").value
        except EscalatedSetting.DoesNotExist:
            return "none"

    # -----------------------------------------------------------------
    # SAML Assertion Validation
    # -----------------------------------------------------------------

    def validate_saml_assertion(self, saml_response):
        """
        Validate a base64-encoded SAML response and extract user attributes.

        Returns dict with 'email', 'name', 'role', 'attributes'.
        Raises SsoValidationError on failure.
        """
        config = self.get_config()

        try:
            xml_bytes = base64.b64decode(saml_response)
        except Exception:
            raise SsoValidationError("Invalid SAML response: base64 decode failed.")

        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError:
            raise SsoValidationError("Invalid SAML response: malformed XML.")

        # Check issuer
        entity_id = config.get("sso_entity_id", "").strip()
        if entity_id:
            issuer_el = root.find(".//saml:Issuer", self.SAML_NS)
            if issuer_el is None:
                raise SsoValidationError("SAML assertion missing Issuer element.")
            issuer = (issuer_el.text or "").strip()
            if issuer != entity_id:
                raise SsoValidationError(
                    f"SAML Issuer mismatch: expected '{entity_id}', got '{issuer}'."
                )

        # Validate conditions
        conditions_el = root.find(".//saml:Conditions", self.SAML_NS)
        if conditions_el is not None:
            self._validate_saml_conditions(conditions_el)

        # Extract attributes
        attr_email = config.get("sso_attr_email", "email")
        attr_name = config.get("sso_attr_name", "name")
        attr_role = config.get("sso_attr_role", "role")

        attributes = self._extract_saml_attributes(root)

        email = attributes.get(attr_email)
        if not email:
            # Fall back to NameID
            name_id_el = root.find(".//saml:Subject/saml:NameID", self.SAML_NS)
            if name_id_el is not None:
                email = (name_id_el.text or "").strip()

        if not email:
            raise SsoValidationError("SAML assertion missing email attribute.")

        return {
            "email": email,
            "name": attributes.get(attr_name, ""),
            "role": attributes.get(attr_role, ""),
            "attributes": attributes,
        }

    def _validate_saml_conditions(self, conditions_el):
        now = time.time()
        skew = 120

        not_before = conditions_el.get("NotBefore")
        if not_before:
            from email.utils import parsedate_to_datetime
            import datetime

            try:
                dt = datetime.datetime.fromisoformat(not_before.replace("Z", "+00:00"))
                if dt.timestamp() > (now + skew):
                    raise SsoValidationError("SAML assertion is not yet valid.")
            except (ValueError, TypeError):
                pass

        not_on_or_after = conditions_el.get("NotOnOrAfter")
        if not_on_or_after:
            import datetime

            try:
                dt = datetime.datetime.fromisoformat(not_on_or_after.replace("Z", "+00:00"))
                if dt.timestamp() < (now - skew):
                    raise SsoValidationError("SAML assertion has expired.")
            except (ValueError, TypeError):
                pass

    def _extract_saml_attributes(self, root):
        attributes = {}
        for attr_el in root.findall(
            ".//saml:AttributeStatement/saml:Attribute", self.SAML_NS
        ):
            name = attr_el.get("Name", "")
            value_el = attr_el.find("saml:AttributeValue", self.SAML_NS)
            if value_el is not None:
                attributes[name] = (value_el.text or "").strip()
        return attributes

    # -----------------------------------------------------------------
    # JWT Token Validation
    # -----------------------------------------------------------------

    def validate_jwt_token(self, token):
        """
        Validate a JWT token and extract user attributes.

        Returns dict with 'email', 'name', 'role', 'claims'.
        Raises SsoValidationError on failure.
        """
        config = self.get_config()

        parts = token.split(".")
        if len(parts) != 3:
            raise SsoValidationError("Invalid JWT: expected 3 segments.")

        header_b64, payload_b64, signature_b64 = parts

        # Decode header
        try:
            header = json.loads(self._base64url_decode(header_b64))
        except (json.JSONDecodeError, Exception):
            raise SsoValidationError("Invalid JWT: malformed header.")

        # Decode payload
        try:
            payload = json.loads(self._base64url_decode(payload_b64))
        except (json.JSONDecodeError, Exception):
            raise SsoValidationError("Invalid JWT: malformed payload.")

        # Verify signature
        secret = config.get("sso_jwt_secret", "")
        algorithm = config.get("sso_jwt_algorithm", "HS256")

        if not secret:
            raise SsoValidationError("JWT secret is not configured.")

        signature = self._base64url_decode(signature_b64)
        signing_input = f"{header_b64}.{payload_b64}".encode()

        if not self._verify_jwt_signature(signing_input, signature, secret, algorithm):
            raise SsoValidationError("Invalid JWT: signature verification failed.")

        # Check expiration
        now = time.time()
        skew = 60

        exp = payload.get("exp")
        if exp is not None and exp < (now - skew):
            raise SsoValidationError("JWT has expired.")

        nbf = payload.get("nbf")
        if nbf is not None and nbf > (now + skew):
            raise SsoValidationError("JWT is not yet valid.")

        # Extract user attributes
        attr_email = config.get("sso_attr_email", "email")
        attr_name = config.get("sso_attr_name", "name")
        attr_role = config.get("sso_attr_role", "role")

        email = payload.get(attr_email) or payload.get("email") or payload.get("sub")
        if not email:
            raise SsoValidationError("JWT missing email claim.")

        return {
            "email": email,
            "name": payload.get(attr_name) or payload.get("name", ""),
            "role": payload.get(attr_role) or payload.get("role", ""),
            "claims": payload,
        }

    def _verify_jwt_signature(self, signing_input, signature, secret, algorithm):
        hmac_algos = {
            "HS256": hashlib.sha256,
            "HS384": hashlib.sha384,
            "HS512": hashlib.sha512,
        }
        if algorithm in hmac_algos:
            expected = hmac.new(
                secret.encode(), signing_input, hmac_algos[algorithm]
            ).digest()
            return hmac.compare_digest(expected, signature)

        raise SsoValidationError(f"Unsupported JWT algorithm: {algorithm}")

    def _base64url_decode(self, s):
        s += "=" * (-len(s) % 4)
        return base64.urlsafe_b64decode(s)
