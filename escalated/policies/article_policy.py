from escalated.permissions import is_admin


class ArticlePolicy:
    @staticmethod
    def view(user, article=None):
        return True

    @staticmethod
    def create(user):
        return is_admin(user)

    @staticmethod
    def update(user, article):
        return is_admin(user)

    @staticmethod
    def delete(user, article):
        return is_admin(user)
