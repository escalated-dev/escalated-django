from escalated.permissions import is_admin


class CannedResponsePolicy:
    @staticmethod
    def view(user, canned_response=None):
        if not user or not user.is_authenticated:
            return False
        return True

    @staticmethod
    def create(user):
        if not user or not user.is_authenticated:
            return False
        return True

    @staticmethod
    def update(user, canned_response):
        if is_admin(user):
            return True
        return canned_response.created_by == user and not canned_response.is_shared

    @staticmethod
    def delete(user, canned_response):
        if is_admin(user):
            return True
        return canned_response.created_by == user and not canned_response.is_shared
