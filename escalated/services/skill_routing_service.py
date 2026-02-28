class SkillRoutingService:
    def find_matching_agents(self, ticket):
        """Find agents with skills matching ticket tags, sorted by current load.

        Maps ticket tags to skills by name, then finds agents who have those skills,
        ordered by current open ticket count (ascending).
        """
        from django.contrib.auth import get_user_model
        from django.db.models import Count, Q

        from escalated.models import AgentSkill, Skill

        User = get_user_model()
        tag_names = list(ticket.tags.values_list("name", flat=True))
        if not tag_names:
            return User.objects.none()

        skill_ids = list(Skill.objects.filter(name__in=tag_names).values_list("id", flat=True))
        if not skill_ids:
            return User.objects.none()

        # Find user IDs who have these skills
        agent_user_ids = list(
            AgentSkill.objects.filter(skill_id__in=skill_ids)
            .values_list("user_id", flat=True)
            .distinct()
        )
        if not agent_user_ids:
            return User.objects.none()

        # Return agents sorted by open ticket count
        return (
            User.objects.filter(pk__in=agent_user_ids)
            .annotate(
                open_tickets_count=Count(
                    "escalated_assigned_tickets",
                    filter=~Q(escalated_assigned_tickets__status__in=["resolved", "closed"]),
                )
            )
            .order_by("open_tickets_count")
        )
