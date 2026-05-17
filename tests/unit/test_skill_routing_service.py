import pytest

from escalated.models import SkillRoutingDepartment, SkillRoutingTag
from escalated.services.skill_routing_service import SkillRoutingService
from tests.factories import (
    AgentSkillFactory,
    DepartmentFactory,
    SkillFactory,
    TagFactory,
    TicketFactory,
    UserFactory,
)


@pytest.mark.django_db
def test_routing_matches_via_explicit_tag_mapping_not_skill_name():
    """Skill name differs from tag name; routing uses SkillRoutingTag only."""
    tag_bug = TagFactory(name="bug", slug="bug")

    skill = SkillFactory(name="Networking Expert", slug="networking-expert")
    SkillRoutingTag.objects.create(skill=skill, tag=tag_bug)

    # Name-match legacy would look for Skill named "bug"; none exists.
    assert not skill.name.lower() == tag_bug.name.lower()

    user_match = UserFactory(username="has_skill")
    user_no = UserFactory(username="no_skill")
    AgentSkillFactory(user=user_match, skill=skill, proficiency=5)

    ticket = TicketFactory()
    ticket.tags.add(tag_bug)

    svc = SkillRoutingService()
    agents = list(svc.find_matching_agents(ticket))
    assert agents == [user_match]
    assert user_no not in agents


@pytest.mark.django_db
def test_routing_requires_all_skills_and_orders_by_proficiency_sum():
    dept = DepartmentFactory()
    tag = TagFactory()
    s_a = SkillFactory(name="Skill A", slug="skill-a")
    s_b = SkillFactory(name="Skill B", slug="skill-b")
    SkillRoutingTag.objects.create(skill=s_a, tag=tag)
    SkillRoutingTag.objects.create(skill=s_b, tag=tag)

    strong = UserFactory(username="strong")
    weak = UserFactory(username="weak")
    AgentSkillFactory(user=strong, skill=s_a, proficiency=5)
    AgentSkillFactory(user=strong, skill=s_b, proficiency=5)
    AgentSkillFactory(user=weak, skill=s_a, proficiency=2)
    AgentSkillFactory(user=weak, skill=s_b, proficiency=1)

    ticket = TicketFactory(department=dept)
    ticket.tags.add(tag)

    svc = SkillRoutingService()
    agents = list(svc.find_matching_agents(ticket))
    assert agents[0] == strong
    assert agents[1] == weak


@pytest.mark.django_db
def test_routing_matches_via_department_mapping():
    dept = DepartmentFactory()
    skill = SkillFactory(name="Billing", slug="billing")
    SkillRoutingDepartment.objects.create(skill=skill, department=dept)

    user = UserFactory()
    AgentSkillFactory(user=user, skill=skill, proficiency=3)

    ticket = TicketFactory(department=dept)

    svc = SkillRoutingService()
    agents = list(svc.find_matching_agents(ticket))
    assert agents == [user]
