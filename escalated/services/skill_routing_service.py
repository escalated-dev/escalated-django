class SkillRoutingService:
    def find_matching_agents(self, ticket):
        """Find agents eligible for every skill required by the ticket's tags and department.

        Required skills are those with a routing tag overlapping the ticket's tags, or a
        routing department matching the ticket's department. Eligible agents hold an
        AgentSkill row for every required skill. Results are ordered by sum of matched
        proficiencies (desc), then by open ticket load (asc).
        """
        from django.contrib.auth import get_user_model
        from django.db.models import Count, Q, Sum

        from escalated.models import AgentSkill, Skill

        User = get_user_model()

        tag_ids = list(ticket.tags.values_list("id", flat=True))
        department_id = ticket.department_id

        skill_parts = []
        if tag_ids:
            skill_parts.append(Q(routing_tags__in=tag_ids))
        if department_id:
            skill_parts.append(Q(routing_departments=department_id))
        if not skill_parts:
            return User.objects.none()

        combined = skill_parts[0]
        for part in skill_parts[1:]:
            combined |= part

        required_skill_ids = list(Skill.objects.filter(combined).distinct().values_list("id", flat=True))
        required_count = len(required_skill_ids)
        if required_count == 0:
            return User.objects.none()

        eligible_user_ids = (
            AgentSkill.objects.filter(skill_id__in=required_skill_ids)
            .values("user_id")
            .annotate(matched_skills=Count("skill_id", distinct=True))
            .filter(matched_skills=required_count)
            .values_list("user_id", flat=True)
        )

        return (
            User.objects.filter(pk__in=eligible_user_ids)
            .annotate(
                matched_proficiency_sum=Sum(
                    "agentskill__proficiency",
                    filter=Q(agentskill__skill_id__in=required_skill_ids),
                ),
                open_tickets_count=Count(
                    "escalated_assigned_tickets",
                    filter=~Q(escalated_assigned_tickets__status__in=["resolved", "closed"]),
                ),
            )
            .order_by("-matched_proficiency_sum", "open_tickets_count")
        )
