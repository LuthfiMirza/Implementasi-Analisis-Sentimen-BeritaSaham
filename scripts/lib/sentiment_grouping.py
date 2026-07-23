from __future__ import annotations

from collections import defaultdict


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, item: str) -> None:
        self.parent.setdefault(item, item)

    def find(self, item: str) -> str:
        self.add(item)
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, left: str, right: str) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return
        keep, move = sorted([root_left, root_right])
        self.parent[move] = keep

    def groups(self) -> dict[str, list[str]]:
        output: dict[str, list[str]] = defaultdict(list)
        for item in list(self.parent):
            output[self.find(item)].append(item)
        return {root: sorted(items) for root, items in output.items()}
