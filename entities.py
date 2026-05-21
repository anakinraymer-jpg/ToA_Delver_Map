import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Entity:
    name: str
    node: int
    color: str
    is_group: bool = False
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def label(self) -> str:
        words = self.name.split()
        if len(words) == 1:
            return self.name[:3].upper()
        return "".join(w[0] for w in words[:3]).upper()


class EntityManager:
    def __init__(self):
        self._entities: dict[str, Entity] = {}

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

    @property
    def all(self) -> list[Entity]:
        return list(self._entities.values())

    def at_node(self, node: int) -> list[Entity]:
        return [e for e in self._entities.values() if e.node == node]
