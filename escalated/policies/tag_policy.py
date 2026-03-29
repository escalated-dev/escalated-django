from escalated.permissions import is_admin, is_agent


class TagPolicy:
    @staticmethod
    def view(user, tag=None):
        if not user or not user.is_authenticated:
            return False
        return is_admin(user) or is_agent(user)

    @staticmethod
    def create(user):
        return is_admin(user)

    @staticmethod
    def update(user, tag):
        return is_admin(user)

    @staticmethod
    def delete(user, tag):
        return is_admin(user)
