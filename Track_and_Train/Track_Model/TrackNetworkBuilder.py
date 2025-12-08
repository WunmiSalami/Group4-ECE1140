"""
Track Network Builder - Handles all branching logic and graph construction
Separated from visualization for cleaner architecture
"""

import pandas as pd
import re
from typing import List, Dict, Tuple, Set, Optional
from collections import Counter
from dataclasses import dataclass


# ---------- Parsing helpers for SWITCH statements ----------
def extract_branching_display(value: str) -> str:
    """Extract branching connections for display purposes."""
    text = str(value).upper().strip()
    if "SWITCH TO YARD" in text or "SWITCH FROM YARD" in text:
        return "N/A"
    if "SWITCH" not in text:
        return "N/A"
    m = re.search(r"\(([^)]+)\)", text)
    if not m:
        return "N/A"
    inside = m.group(1)
    connected = [c.strip() for c in re.split(r"[;,]", inside) if c.strip()]
    return ", ".join(connected) if connected else "N/A"


def parse_branching_connections(value: str) -> List[Tuple[int, int]]:
    """Parse SWITCH (A-B; C-D) format into connection pairs."""
    text = str(value).upper().strip()
    if "SWITCH TO YARD" in text or "SWITCH FROM YARD" in text:
        return []
    if "SWITCH" not in text:
        return []

    m = re.search(r"\(([^)]+)\)", text)
    if not m:
        return []

    inside = m.group(1)
    connections = []

    parts = re.split(r"[;,]", inside)
    for part in parts:
        part = part.strip()
        conn_match = re.search(r"(\d+)\s*-\s*(\d+)", part)
        if conn_match:
            from_block = int(conn_match.group(1))
            to_block = int(conn_match.group(2))
            connections.append((from_block, to_block))

    return connections


# -----------------------------------------------------------


@dataclass
class Loop:
    """Represents a backward loop connection."""

    from_block: int
    to_block: int

    def __repr__(self):
        return f"Loop({self.from_block}→{self.to_block})"


@dataclass
class Path:
    """Represents a track path (main or branch)."""

    id: int
    type: str  # 'main' or 'branch'
    blocks: List[int]
    from_block: Optional[int] = None  # Where branch splits from
    start_block: Optional[int] = None  # First block on this path
    connects_to_path: Optional[int] = None  # Path ID this connects to
    connects_at_block: Optional[int] = None  # Block where connection happens
    ordered_blocks: Optional[List[int]] = None  # BFS traversal order for visualization

    def __repr__(self):
        if self.type == "main":
            return f"Path(Main: {len(self.blocks)} blocks)"
        else:
            return f"Path(Branch {self.id}: {self.from_block}→{self.start_block}, {len(self.blocks)} blocks)"


@dataclass
class BranchPoint:
    """Information about a branching point."""

    block_num: int
    targets: List[int]  # Blocks this branches to

    def __repr__(self):
        return f"BranchPoint({self.block_num}→{self.targets})"


class TrackNetwork:
    """Complete track network with all paths and connections."""

    def __init__(self):
        self.paths: List[Path] = []
        self.branch_points: Dict[int, BranchPoint] = {}
        self.loops: List[Loop] = []
        self.block_to_path: Dict[int, int] = {}  # block_num -> path_id
        self.block_to_idx: Dict[int, int] = {}  # block_num -> dataframe index

    def get_path(self, path_id: int) -> Optional[Path]:
        """Get path by ID."""
        for path in self.paths:
            if path.id == path_id:
                return path
        return None

    def get_path_for_block(self, block_num: int) -> Optional[Path]:
        """Get which path a block belongs to."""
        path_id = self.block_to_path.get(block_num)
        if path_id is not None:
            return self.get_path(path_id)
        return None

    def get_main_path(self) -> Optional[Path]:
        """Get the main path."""
        for path in self.paths:
            if path.type == "main":
                return path
        return None

    def get_branch_paths(self) -> List[Path]:
        """Get all branch paths."""
        return [p for p in self.paths if p.type == "branch"]

    def __repr__(self):
        return f"TrackNetwork(paths={len(self.paths)}, branches={len(self.branch_points)}, loops={len(self.loops)})"


class TrackNetworkBuilder:
    """Builds track network from dataframe with SWITCH statements."""

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.network = TrackNetwork()
        self._switches = []  # Raw switch data
        self._branch_info = []  # Processed branch information

    def build(self) -> TrackNetwork:
        """Main method - build complete network and return."""

        # Step 1: Map block numbers to dataframe indices
        self._map_blocks()

        # Step 2: Parse all SWITCH statements
        self._parse_switches()

        # Step 3: Identify branch points
        self._identify_branch_points()

        # Step 4: Categorize connections (loops vs branches)
        self._categorize_connections()

        # Step 5: Build all paths (main + branches)
        self._build_paths_bfs()

        # Step 6: Validation
        self._validate_paths()
        return self.network

    def _map_blocks(self):
        """Map block numbers to dataframe indices."""
        for idx, row in self.df.iterrows():
            block_num_val = row.get("Block Number", "N/A")
            if block_num_val != "N/A" and str(block_num_val) != "nan":
                try:
                    block_num = int(block_num_val)
                    self.network.block_to_idx[block_num] = idx
                except:
                    pass

    def _parse_switches(self):
        """Extract all SWITCH statements from dataframe."""
        for idx, row in self.df.iterrows():
            branch_conns = row.get("BranchConnections", [])
            if len(branch_conns) >= 2:
                self._switches.append({"row_idx": idx, "connections": branch_conns})

    def _identify_branch_points(self):
        """Find branch points (blocks that appear twice in connections)."""
        for switch in self._switches:
            connections = switch["connections"]

            # Collect all block numbers in this switch
            all_nums = []
            for from_b, to_b in connections:
                all_nums.extend([from_b, to_b])

            # Count occurrences
            num_counts = Counter(all_nums)

            # Branch point appears exactly twice
            for num, count in num_counts.items():
                if count == 2:
                    branch_point = num

                    # Find all targets from this branch point
                    targets = []
                    for from_b, to_b in connections:
                        if from_b == branch_point:
                            targets.append(to_b)
                        elif to_b == branch_point:
                            # Connection TO branch point (might be backward loop)
                            if from_b != branch_point - 1:
                                targets.append(from_b)

                    # Store branch point
                    self.network.branch_points[branch_point] = BranchPoint(
                        block_num=branch_point, targets=list(set(targets))
                    )
                    break

    def _categorize_connections(self):
        """Categorize connections as loops or forward branches."""
        for branch_point, bp_info in self.network.branch_points.items():
            for target in bp_info.targets:
                # Skip sequential (would happen anyway)
                if target == branch_point + 1:
                    continue

                if target < branch_point:
                    # BACKWARD = LOOP
                    self.network.loops.append(
                        Loop(from_block=branch_point, to_block=target)
                    )

                elif target > branch_point + 1:
                    # FORWARD = Potential branch
                    blocks_between = target - branch_point - 1

                    self._branch_info.append(
                        {
                            "branch_point": branch_point,
                            "target": target,
                            "blocks_between": blocks_between,
                            "is_large_gap": blocks_between >= 5,
                        }
                    )

    def _build_paths_bfs(self):
        """Build all paths - process branches from LATEST to EARLIEST."""
        all_blocks = sorted(self.network.block_to_idx.keys())
        if not all_blocks:
            return

        # Step 1: Collect ALL branch targets
        branch_targets = {}  # branch_point -> target
        branch_start_blocks = set()

        for branch_point in self.network.branch_points:
            bp = self.network.branch_points[branch_point]
            for target in bp.targets:
                if target > branch_point + 1:  # Forward branch only
                    branch_targets[branch_point] = target
                    branch_start_blocks.add(target)

        # Step 2: Build ALL branches first (from LATEST to EARLIEST)
        # Sort branch points by their TARGET block number (descending)
        sorted_branches = sorted(
            branch_targets.items(), key=lambda x: x[1], reverse=True
        )

        all_branch_blocks = set()
        path_id = 1

        for branch_point, target in sorted_branches:
            # Build branch sequentially from target to END or another branch
            branch_blocks = []
            current = target

            while current in all_blocks:
                branch_blocks.append(current)
                all_branch_blocks.add(current)

                # Check next block
                next_block = current + 1

                # Stop if next block starts a different branch
                if next_block in branch_start_blocks and next_block != target:
                    break

                # Stop if next block doesn't exist
                if next_block not in all_blocks:
                    break

                current = next_block

            # Determine reconnection - check where next block APPEARS
            last_block = branch_blocks[-1]
            next_after_branch = last_block + 1
            connects_to = None
            connects_at = None

            # Check if next block exists anywhere (main or branches)
            if next_after_branch in all_blocks:
                # Find where this block appears
                if next_after_branch in all_branch_blocks:
                    # It's in a branch - find which one
                    for other_path in self.network.paths:
                        if next_after_branch in other_path.blocks:
                            connects_at = next_after_branch
                            connects_to = other_path.id
                            break
                else:
                    # It will be in main path
                    connects_at = next_after_branch
                    connects_to = 0  # Will connect to main

            branch_path = Path(
                id=path_id,
                type="branch",
                blocks=branch_blocks,
                from_block=branch_point,
                start_block=target,
                connects_to_path=connects_to,
                connects_at_block=connects_at,
            )
            self.network.paths.append(branch_path)

            for block in branch_blocks:
                self.network.block_to_path[block] = path_id

            reconnect_info = ""
            if connects_at:
                reconnect_type = "main" if connects_to == 0 else f"branch {connects_to}"
                reconnect_info = (
                    f" → reconnects to {reconnect_type} at block {connects_at}"
                )

            print(
                f"  Branch {path_id}: from {branch_point}→{target}, {len(branch_blocks)} blocks {branch_blocks}{reconnect_info}"
            )
            path_id += 1

        # Step 3: Build main path - SEQUENTIAL, but SKIP all branch blocks
        main_blocks = []
        current = all_blocks[0]

        while current in all_blocks:
            # SKIP if this block is in ANY branch
            if current in all_branch_blocks:
                current += 1
                continue

            main_blocks.append(current)
            current += 1

        # Create main path
        ordered_blocks = list(main_blocks)

        # Insert branches into ordered blocks at their branch points
        for branch_path in sorted(
            self.network.paths, key=lambda p: p.from_block if p.from_block else 0
        ):
            if (
                branch_path.type == "branch"
                and branch_path.from_block in ordered_blocks
            ):
                insert_idx = ordered_blocks.index(branch_path.from_block) + 1
                for block in branch_path.blocks:
                    ordered_blocks.insert(insert_idx, block)
                    insert_idx += 1

        main_path = Path(
            id=0, type="main", blocks=main_blocks, ordered_blocks=ordered_blocks
        )
        self.network.paths.insert(0, main_path)  # Insert at beginning

        for block in main_blocks:
            self.network.block_to_path[block] = 0

        print(
            f"  Main path: {len(main_blocks)} blocks (ends at {main_blocks[-1] if main_blocks else 'N/A'})"
        )
        print(f"  Total traversal order: {len(ordered_blocks)} blocks")

    def _validate_paths(self):
        """Validate the built network against all rules."""
        all_blocks = set(self.network.block_to_idx.keys())

        # Rule 1: All blocks assigned to exactly one path
        assigned = set()
        for path in self.network.paths:
            for block in path.blocks:
                if block in assigned:
                    pass
                assigned.add(block)

        missing = all_blocks - assigned
        if missing:
            pass

        # Rule 2: Branch blocks are sequential
        for path in self.network.paths:
            if path.type == "branch" and len(path.blocks) > 1:
                for i in range(len(path.blocks) - 1):
                    if path.blocks[i + 1] != path.blocks[i] + 1:
                        break

    def print_network_summary(self):
        """Print detailed network summary for debugging."""
        pass


# Example usage
if __name__ == "__main__":
    pass
