from escalated.permissions import is_admin


class SlaPolicyPolicy:
    @staticmethod
    def view(user, sla_policy=None):
        return is_admin(user)

    @staticmethod
    def create(user):
        return is_admin(user)

    @staticmethod
    def update(user, sla_policy):
        return is_admin(user)

    @staticmethod
    def delete(user, sla_policy):
        return is_admin(user)
