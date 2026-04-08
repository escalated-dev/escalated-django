from escalated.models import AgentProfile, ChatSession


class ChatAvailabilityService:
    """Service for checking chat availability."""

    def is_available(self, department=None):
        """
        Check if live chat is currently available (any agents online).

        Args:
            department: Optional Department to check availability for.

        Returns:
            bool: True if at least one agent is online and available.
        """
        agents = self.get_online_agents(department)
        return len(agents) > 0

    def get_online_agents(self, department=None):
        """
        Get a list of agents currently online for chat.

        Args:
            department: Optional Department to filter by.

        Returns:
            list: List of User objects for online agents.
        """
        profiles = AgentProfile.objects.filter(chat_status=AgentProfile.ChatStatus.ONLINE)

        if department:
            agent_ids = department.agents.values_list("pk", flat=True)
            profiles = profiles.filter(user_id__in=agent_ids)

        return [p.user for p in profiles.select_related("user")]

    def get_queue_position(self, session):
        """
        Get the queue position of a waiting chat session.

        Returns:
            int: Position in the queue (1-based), or 0 if not waiting.
        """
        if session.status != ChatSession.Status.WAITING:
            return 0

        ahead = ChatSession.objects.filter(
            status=ChatSession.Status.WAITING,
            created_at__lt=session.created_at,
        ).count()

        return ahead + 1

    def get_agent_chat_count(self, agent):
        """
        Get the number of active chats for an agent.

        Returns:
            int: Number of active chat sessions.
        """
        return ChatSession.objects.filter(
            agent=agent,
            status=ChatSession.Status.ACTIVE,
        ).count()
