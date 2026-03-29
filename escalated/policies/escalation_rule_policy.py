from escalated.permissions import is_admin


class EscalationRulePolicy:
    @staticmethod
    def view(user, rule=None):
        return is_admin(user)

    @staticmethod
    def create(user):
        return is_admin(user)

    @staticmethod
    def update(user, rule):
        return is_admin(user)

    @staticmethod
    def delete(user, rule):
        return is_admin(user)
