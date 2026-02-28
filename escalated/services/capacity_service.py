class CapacityService:
    def can_accept_ticket(self, user_id, channel="default"):
        """Check if an agent can accept a new ticket."""
        from escalated.models import AgentCapacity

        capacity, _ = AgentCapacity.objects.get_or_create(
            user_id=user_id,
            channel=channel,
            defaults={"max_concurrent": 10, "current_count": 0},
        )
        return capacity.has_capacity()

    def increment_load(self, user_id, channel="default"):
        """Increment the agent's current load."""
        from escalated.models import AgentCapacity

        capacity, _ = AgentCapacity.objects.get_or_create(
            user_id=user_id,
            channel=channel,
            defaults={"max_concurrent": 10, "current_count": 0},
        )
        capacity.current_count += 1
        capacity.save(update_fields=["current_count", "updated_at"])

    def decrement_load(self, user_id, channel="default"):
        """Decrement the agent's current load."""
        from escalated.models import AgentCapacity

        capacity, _ = AgentCapacity.objects.get_or_create(
            user_id=user_id,
            channel=channel,
            defaults={"max_concurrent": 10, "current_count": 0},
        )
        if capacity.current_count > 0:
            capacity.current_count -= 1
            capacity.save(update_fields=["current_count", "updated_at"])

    def get_all_capacities(self):
        """Get all agent capacities for admin view."""
        from escalated.models import AgentCapacity

        return AgentCapacity.objects.select_related("user").all()
