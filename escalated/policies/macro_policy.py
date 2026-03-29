from escalated.permissions import is_admin


class MacroPolicy:
    @staticmethod
    def view(user, macro=None):
        if not user or not user.is_authenticated:
            return False
        return True

    @staticmethod
    def create(user):
        if not user or not user.is_authenticated:
            return False
        return True

    @staticmethod
    def update(user, macro):
        if is_admin(user):
            return True
        return macro.created_by == user and not macro.is_shared

    @staticmethod
    def delete(user, macro):
        if is_admin(user):
            return True
        return macro.created_by == user and not macro.is_shared
