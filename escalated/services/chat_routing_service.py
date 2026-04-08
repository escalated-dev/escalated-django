import random

from escalated.models import AgentProfile, ChatRoutingRule, ChatSession


class ChatRoutingService:
    """Service for routing chats to available agents."""

    def find_available_agent(self, department=None):
        """
        Find an available agent based on routing rules.

        Args:
            department: Optional Department to filter agents by.

        Returns:
            User or None: The selected agent, or None if nobody is available.
        """
        rule = self._get_routing_rule(department)
        strategy = rule.routing_strategy if rule else ChatRoutingRule.RoutingStrategy.ROUND_ROBIN
        max_concurrent = rule.max_concurrent_chats if rule else 5

        agents = self._get_online_agents(department)
        if not agents:
            return None

        # Filter out agents at capacity
        available = []
        for agent in agents:
            active_count = ChatSession.objects.filter(
                agent=agent,
                status=ChatSession.Status.ACTIVE,
            ).count()
            if active_count < max_concurrent:
                available.append((agent, active_count))

        if not available:
            return None

        if strategy == ChatRoutingRule.RoutingStrategy.LEAST_ACTIVE:
            available.sort(key=lambda x: x[1])
            return available[0][0]
        elif strategy == ChatRoutingRule.RoutingStrategy.RANDOM:
            return random.choice(available)[0]
        else:
            # Round robin: pick agent with fewest active chats
            available.sort(key=lambda x: x[1])
            return available[0][0]

    def evaluate_routing(self, department=None):
        """
        Evaluate routing and return the routing rule and available agent count.

        Returns:
            dict with routing_rule, available_agents count, and recommendation.
        """
        rule = self._get_routing_rule(department)
        agents = self._get_online_agents(department)
        max_concurrent = rule.max_concurrent_chats if rule else 5

        available_count = 0
        for agent in agents:
            active_count = ChatSession.objects.filter(
                agent=agent,
                status=ChatSession.Status.ACTIVE,
            ).count()
            if active_count < max_concurrent:
                available_count += 1

        offline_behavior = rule.offline_behavior if rule else ChatRoutingRule.OfflineBehavior.TICKET

        return {
            "routing_rule": rule,
            "total_online_agents": len(agents),
            "available_agents": available_count,
            "offline_behavior": offline_behavior,
            "is_available": available_count > 0,
        }

    def _get_routing_rule(self, department=None):
        """Get the applicable routing rule."""
        if department:
            rule = ChatRoutingRule.objects.active().filter(department=department).first()
            if rule:
                return rule

        # Fall back to global rule (no department)
        return ChatRoutingRule.objects.active().filter(department__isnull=True).first()

    def _get_online_agents(self, department=None):
        """Get agents who are online for chat."""
        profiles = AgentProfile.objects.filter(chat_status=AgentProfile.ChatStatus.ONLINE)

        if department:
            agent_ids = department.agents.values_list("pk", flat=True)
            profiles = profiles.filter(user_id__in=agent_ids)

        return [p.user for p in profiles.select_related("user")]
