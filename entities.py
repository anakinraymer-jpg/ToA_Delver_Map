import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Entity:
    name: str
    node: int
    color: str
    is_group: bool = False
    is_bot: bool = False
    members: list = field(default_factory=list)   # list[str] — member entity IDs (groups only)
    bot_target: Optional[int] = None              # target hex node for auto-pathfinding (bots only)
    flavor_text: str = ""                         # optional notes / backstory shown in info panel
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def label(self) -> str:
        words = self.name.split()
        initials = "".join(w[0] for w in words[:3]).upper()
        if self.is_group and self.members:
            return f"{initials}×{len(self.members)}"
        if len(words) == 1:
            return self.name[:3].upper()
        return initials


class EntityManager:
    def __init__(self):
        self._entities: dict[str, Entity] = {}

    # ------------------------------------------------------------------
    # Basic CRUD
    # ------------------------------------------------------------------

    def add(self, entity: Entity) -> Entity:
        self._entities[entity.id] = entity
        return entity

    def remove(self, entity_id: str):
        self._entities.pop(entity_id, None)

    def get(self, entity_id: str) -> Optional[Entity]:
        return self._entities.get(entity_id)

    def move(self, entity_id: str, new_node: int):
        e = self._entities.get(entity_id)
        if e:
            e.node = new_node
            # Drag all group members along
            if e.is_group:
                for mid in e.members:
                    m = self._entities.get(mid)
                    if m:
                        m.node = new_node

    # ------------------------------------------------------------------
    # Group membership helpers
    # ------------------------------------------------------------------

    def is_group_member(self, entity_id: str) -> bool:
        """Return True if this entity currently belongs to a group."""
        return any(
            entity_id in e.members
            for e in self._entities.values()
            if e.is_group
        )

    def group_of(self, entity_id: str) -> Optional[Entity]:
        """Return the group this entity belongs to, or None."""
        for e in self._entities.values():
            if e.is_group and entity_id in e.members:
                return e
        return None

    def add_to_group(self, group_id: str, member_id: str):
        group = self._entities.get(group_id)
        member = self._entities.get(member_id)
        if group and member and group.is_group and member_id not in group.members:
            group.members.append(member_id)
            member.node = group.node          # sync position

    def remove_from_group(self, group_id: str, member_id: str):
        group = self._entities.get(group_id)
        if group and member_id in group.members:
            group.members.remove(member_id)
            member = self._entities.get(member_id)
            if member:
                member.node = group.node      # reappear at group's hex

    def merge_into_group(
        self,
        entity_ids: list,
        name: str,
        color: str,
        is_bot: bool = False,
    ) -> Entity:
        """Create a new group containing the given entities."""
        nodes = [
            self._entities[eid].node
            for eid in entity_ids
            if eid in self._entities
        ]
        node = nodes[0] if nodes else 1
        group = Entity(
            name=name,
            node=node,
            color=color,
            is_group=True,
            is_bot=is_bot,
            members=list(entity_ids),
        )
        self.add(group)
        return group

    def disband_group(self, group_id: str):
        """Delete the group entity; members reappear independently."""
        group = self._entities.get(group_id)
        if not group or not group.is_group:
            return
        for mid in group.members:
            m = self._entities.get(mid)
            if m:
                m.node = group.node           # set to group's last position
        self.remove(group_id)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def all(self) -> list:
        """All entities including group members (used for save/load)."""
        return list(self._entities.values())

    @property
    def toplevel(self) -> list:
        """Entities that are not currently inside a group."""
        return [e for e in self._entities.values() if not self.is_group_member(e.id)]

    def at_node(self, node: int) -> list:
        """Top-level entities at this hex node (excludes group members)."""
        return [
            e for e in self._entities.values()
            if e.node == node and not self.is_group_member(e.id)
        ]
