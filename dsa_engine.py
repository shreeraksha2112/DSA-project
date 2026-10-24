"""
MedRescue — DSA Engine
======================
Core algorithms powering the medicine redistribution system.

DSA Concepts Used:
1. Min-Heaps       — Expiry prioritization (soonest-expiring medicines surface first)
2. Weighted Graphs — Transport network (edges weighted by distance, storage compatibility)
3. Bipartite Matching — Optimal donor→receiver assignment (Hungarian / Kuhn's algorithm)
4. Greedy Allocation — Fast, regulation-aware resource distribution
"""

from __future__ import annotations

import heapq
import math
import random
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


# ──────────────────────────────────────────────
# 1.  Domain Models
# ──────────────────────────────────────────────

class StorageCondition(Enum):
    AMBIENT = "ambient"           # 15–25 °C
    REFRIGERATED = "refrigerated" # 2–8 °C
    FROZEN = "frozen"             # -20 °C

    @property
    def label(self):
        return self.value.capitalize()


class TransferStatus(Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


@dataclass
class Medicine:
    id: str
    name: str
    batch: str
    quantity: int
    expiry: date
    storage: StorageCondition
    category: str               # e.g. "Antibiotic", "Analgesic"
    unit_value: float           # $ value per unit
    regulatory_class: str       # "OTC", "Rx", "Controlled"

    @property
    def days_until_expiry(self) -> int:
        return (self.expiry - date.today()).days

    @property
    def is_expired(self) -> bool:
        return self.days_until_expiry <= 0

    @property
    def urgency_score(self) -> float:
        """Lower = more urgent. Used as heap key."""
        days = max(self.days_until_expiry, 0)
        # Weighted: controlled meds get a slight penalty (harder to transfer)
        penalty = 1.0 if self.regulatory_class == "OTC" else (
            1.2 if self.regulatory_class == "Rx" else 1.5
        )
        return days * penalty

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "batch": self.batch,
            "quantity": self.quantity,
            "expiry": self.expiry.isoformat(),
            "days_until_expiry": self.days_until_expiry,
            "storage": self.storage.value,
            "category": self.category,
            "unit_value": self.unit_value,
            "regulatory_class": self.regulatory_class,
            "is_expired": self.is_expired,
            "urgency_score": round(self.urgency_score, 2),
        }


@dataclass
class Facility:
    id: str
    name: str
    lat: float
    lon: float
    city: str
    storage_capabilities: Set[StorageCondition]
    can_handle_controlled: bool
    inventory: List[Medicine] = field(default_factory=list)
    demand: Dict[str, int] = field(default_factory=dict)  # medicine_name → qty needed

    @property
    def total_stock(self) -> int:
        return sum(m.quantity for m in self.inventory)

    @property
    def expiring_soon_count(self) -> int:
        return sum(1 for m in self.inventory if 0 < m.days_until_expiry <= 30)

    @property
    def expired_count(self) -> int:
        return sum(1 for m in self.inventory if m.is_expired)

    @property
    def inventory_value(self) -> float:
        return sum(m.quantity * m.unit_value for m in self.inventory if not m.is_expired)

    def to_dict(self, include_inventory: bool = False) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "city": self.city,
            "storage_capabilities": [s.value for s in self.storage_capabilities],
            "can_handle_controlled": self.can_handle_controlled,
            "total_stock": self.total_stock,
            "expiring_soon": self.expiring_soon_count,
            "expired": self.expired_count,
            "inventory_value": round(self.inventory_value, 2),
            "demand": self.demand,
        }
        if include_inventory:
            d["inventory"] = [m.to_dict() for m in self.inventory]
        return d


@dataclass
class Transfer:
    id: str
    medicine: Medicine
    quantity: int
    donor: Facility
    receiver: Facility
    distance_km: float
    transport_cost: float
    saved_value: float
    status: TransferStatus = TransferStatus.PROPOSED
    urgency: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "medicine_name": self.medicine.name,
            "medicine_id": self.medicine.id,
            "batch": self.medicine.batch,
            "quantity": self.quantity,
            "donor": self.donor.name,
            "donor_id": self.donor.id,
            "receiver": self.receiver.name,
            "receiver_id": self.receiver.id,
            "distance_km": round(self.distance_km, 1),
            "transport_cost": round(self.transport_cost, 2),
            "saved_value": round(self.saved_value, 2),
            "net_saving": round(self.saved_value - self.transport_cost, 2),
            "status": self.status.value,
            "days_until_expiry": self.medicine.days_until_expiry,
            "storage": self.medicine.storage.value,
            "regulatory_class": self.medicine.regulatory_class,
            "urgency": round(self.urgency, 2),
        }


# ──────────────────────────────────────────────
# 2.  Min-Heap — Expiry Prioritization
# ──────────────────────────────────────────────

class ExpiryHeap:
    """
    Priority queue (min-heap) that surfaces the most urgent
    medicines first.  Urgency = f(days-to-expiry, regulatory class).
    
    Time Complexity:
      - push:  O(log n)
      - pop:   O(log n)
      - peek:  O(1)
    """

    def __init__(self):
        self._heap: List[Tuple[float, str, Medicine]] = []

    def push(self, med: Medicine) -> None:
        heapq.heappush(self._heap, (med.urgency_score, med.id, med))

    def pop(self) -> Optional[Medicine]:
        if self._heap:
            _, _, med = heapq.heappop(self._heap)
            return med
        return None

    def peek(self) -> Optional[Medicine]:
        if self._heap:
            return self._heap[0][2]
        return None

    def push_batch(self, meds: List[Medicine]) -> None:
        for m in meds:
            self.push(m)

    def pop_n(self, n: int) -> List[Medicine]:
        result = []
        for _ in range(n):
            m = self.pop()
            if m is None:
                break
            result.append(m)
        return result

    def __len__(self):
        return len(self._heap)

    def to_sorted_list(self) -> List[Medicine]:
        """Drain a *copy* into a sorted list without mutating the heap."""
        copy = list(self._heap)
        result = []
        while copy:
            _, _, med = heapq.heappop(copy)
            result.append(med)
        return result


# ──────────────────────────────────────────────
# 3.  Weighted Graph — Transport Network
# ──────────────────────────────────────────────

class TransportGraph:
    """
    Undirected weighted graph of healthcare facilities.
    Edge weight = composite cost considering:
      - Haversine distance
      - Storage compatibility multiplier
      - Regulatory transfer difficulty

    Implemented via adjacency list with weighted edges.
    """

    COST_PER_KM = 0.5          # $/km base rate
    COLD_CHAIN_MULTIPLIER = 2.0
    FROZEN_MULTIPLIER = 3.5
    CONTROLLED_SURCHARGE = 50.0

    def __init__(self):
        # adjacency list: facility_id → [(neighbor_id, distance_km)]
        self.adj: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        self.facilities: Dict[str, Facility] = {}

    def add_facility(self, fac: Facility) -> None:
        self.facilities[fac.id] = fac
        if fac.id not in self.adj:
            self.adj[fac.id] = []

    def _haversine(self, lat1, lon1, lat2, lon2) -> float:
        R = 6371  # Earth radius in km
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def build_edges(self, max_distance_km: float = 500.0) -> int:
        """Connect every pair within max_distance_km. Returns edge count."""
        ids = list(self.facilities.keys())
        count = 0
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = self.facilities[ids[i]], self.facilities[ids[j]]
                dist = self._haversine(a.lat, a.lon, b.lat, b.lon)
                if dist <= max_distance_km:
                    self.adj[a.id].append((b.id, dist))
                    self.adj[b.id].append((a.id, dist))
                    count += 1
        return count

    def transport_cost(self, donor_id: str, receiver_id: str,
                       med: Medicine) -> Tuple[float, float]:
        """
        Returns (distance_km, cost_$) for shipping `med` from donor → receiver.
        """
        donor = self.facilities[donor_id]
        receiver = self.facilities[receiver_id]
        dist = self._haversine(donor.lat, donor.lon, receiver.lat, receiver.lon)

        # base cost
        cost = dist * self.COST_PER_KM

        # storage surcharges
        if med.storage == StorageCondition.REFRIGERATED:
            cost *= self.COLD_CHAIN_MULTIPLIER
        elif med.storage == StorageCondition.FROZEN:
            cost *= self.FROZEN_MULTIPLIER

        # controlled substance surcharge
        if med.regulatory_class == "Controlled":
            cost += self.CONTROLLED_SURCHARGE

        return dist, cost

    def is_compatible(self, receiver_id: str, med: Medicine) -> bool:
        """Check if receiver can store the medicine."""
        receiver = self.facilities[receiver_id]
        if med.storage not in receiver.storage_capabilities:
            return False
        if med.regulatory_class == "Controlled" and not receiver.can_handle_controlled:
            return False
        return True

    def get_neighbors(self, fac_id: str) -> List[Tuple[str, float]]:
        return self.adj.get(fac_id, [])

    def shortest_path_dijkstra(self, src: str, dst: str) -> Tuple[float, List[str]]:
        """Dijkstra's shortest path. Returns (distance, path)."""
        dist_map = {src: 0.0}
        prev = {}
        visited = set()
        pq = [(0.0, src)]

        while pq:
            d, u = heapq.heappop(pq)
            if u in visited:
                continue
            visited.add(u)
            if u == dst:
                break
            for v, w in self.adj[u]:
                nd = d + w
                if nd < dist_map.get(v, float("inf")):
                    dist_map[v] = nd
                    prev[v] = u
                    heapq.heappush(pq, (nd, v))

        if dst not in dist_map:
            return float("inf"), []
        path = []
        cur = dst
        while cur in prev:
            path.append(cur)
            cur = prev[cur]
        path.append(src)
        path.reverse()
        return dist_map[dst], path

    def to_dict(self) -> dict:
        nodes = []
        for fid, fac in self.facilities.items():
            nodes.append({
                "id": fid,
                "name": fac.name,
                "lat": fac.lat,
                "lon": fac.lon,
                "city": fac.city,
            })
        edges = []
        seen = set()
        for u in self.adj:
            for v, w in self.adj[u]:
                key = tuple(sorted([u, v]))
                if key not in seen:
                    seen.add(key)
                    edges.append({
                        "source": u,
                        "target": v,
                        "distance": round(w, 1),
                    })
        return {"nodes": nodes, "edges": edges}


# ──────────────────────────────────────────────
# 4.  Bipartite Matching — Donor↔Receiver
# ──────────────────────────────────────────────

class BipartiteMatcher:
    """
    Capacity-aware weighted bipartite allocation.

    Left  partition: (donor_facility, medicine)  → surplus stock
    Right partition: receiver_facility           → unmet demand
    Edge weight     = saved_value - transport_cost (net benefit)

    Feasible edges are processed by descending benefit while stock and
    demand capacities are maintained. This is a heuristic, not a
    globally optimal Hungarian or min-cost-flow solution.
    """

    def __init__(self):
        self.left_nodes: List[Tuple[str, Medicine, int]] = []   # (donor_id, med, qty)
        self.right_nodes: List[Tuple[str, str, int]] = []       # (receiver_id, med_name, qty_needed)
        self.edges: List[Tuple[int, int, float, float, float, int]] = []  # (l, r, net, dist, cost, qty)

    def build(self, graph: TransportGraph, heap: ExpiryHeap) -> None:
        """Scan all facilities; build bipartite edges."""
        self.left_nodes.clear()
        self.right_nodes.clear()
        self.edges.clear()

        # LEFT: surplus stock expiring within 90 days
        for fid, fac in graph.facilities.items():
            for med in fac.inventory:
                if med.is_expired:
                    continue
                if med.days_until_expiry <= 90 and med.quantity > 0:
                    self.left_nodes.append((fid, med, med.quantity))

        # RIGHT: unmet demand
        for fid, fac in graph.facilities.items():
            for med_name, qty_needed in fac.demand.items():
                if qty_needed > 0:
                    self.right_nodes.append((fid, med_name, qty_needed))

        # EDGES
        for li, (donor_id, med, qty_avail) in enumerate(self.left_nodes):
            for ri, (recv_id, med_name, qty_needed) in enumerate(self.right_nodes):
                if donor_id == recv_id:
                    continue
                if med.name != med_name:
                    continue
                if not graph.is_compatible(recv_id, med):
                    continue
                dist, cost = graph.transport_cost(donor_id, recv_id, med)
                transfer_qty = min(qty_avail, qty_needed)
                saved = transfer_qty * med.unit_value
                net = saved - cost
                if net > 0:  # only beneficial transfers
                    self.edges.append((li, ri, net, dist, cost, transfer_qty))

    def solve(self, graph: TransportGraph) -> List[Transfer]:
        """
        Capacity-aware weighted matching: sort feasible edges by net
        benefit and assign them while respecting stock and demand.

        For production scale, replace with the full Hungarian algorithm
        or min-cost max-flow.
        """
        # Sort by net benefit descending
        sorted_edges = sorted(self.edges, key=lambda e: -e[2])

        left_remaining = {i: qty for i, (_, _, qty) in enumerate(self.left_nodes)}
        right_remaining = {i: qty for i, (_, _, qty) in enumerate(self.right_nodes)}

        transfers: List[Transfer] = []

        for li, ri, net, dist, cost_per, qty in sorted_edges:
            avail = left_remaining.get(li, 0)
            needed = right_remaining.get(ri, 0)
            if avail <= 0 or needed <= 0:
                continue

            transfer_qty = min(avail, needed, qty)
            donor_id, med, _ = self.left_nodes[li]
            recv_id, _, _ = self.right_nodes[ri]

            saved = transfer_qty * med.unit_value

            t = Transfer(
                id=uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{med.id}:{donor_id}:{recv_id}:{transfer_qty}",
                ).hex,
                medicine=med,
                quantity=transfer_qty,
                donor=graph.facilities[donor_id],
                receiver=graph.facilities[recv_id],
                distance_km=dist,
                transport_cost=cost_per,
                saved_value=saved,
                urgency=med.urgency_score,
            )
            transfers.append(t)

            left_remaining[li] -= transfer_qty
            right_remaining[ri] -= transfer_qty

        return transfers


# ──────────────────────────────────────────────
# 5.  Greedy Allocator — Regulation-Aware
# ──────────────────────────────────────────────

class GreedyAllocator:
    """
    Greedy strategy: process medicines in expiry-urgency order
    (from the min-heap). For each, find the nearest compatible
    receiver with demand.

    This is faster than full matching but may not be globally
    optimal.  Used for quick "what-if" estimates and real-time
    suggestions.
    """

    @staticmethod
    def allocate(graph: TransportGraph) -> List[Transfer]:
        # Build a heap of all expiring medicines
        heap = ExpiryHeap()
        med_to_facility: Dict[str, str] = {}
        for fid, fac in graph.facilities.items():
            for med in fac.inventory:
                if not med.is_expired and med.days_until_expiry <= 90 and med.quantity > 0:
                    heap.push(med)
                    med_to_facility[med.id] = fid

        # Mutable copy of demand
        remaining_demand: Dict[str, Dict[str, int]] = {}
        for fid, fac in graph.facilities.items():
            remaining_demand[fid] = dict(fac.demand)

        transfers: List[Transfer] = []

        while len(heap) > 0:
            med = heap.pop()
            if med is None:
                break
            donor_id = med_to_facility[med.id]

            # Find best receiver: closest with demand + compatible
            best = None
            best_net = -float("inf")
            for recv_id, fac in graph.facilities.items():
                if recv_id == donor_id:
                    continue
                demand_qty = remaining_demand[recv_id].get(med.name, 0)
                if demand_qty <= 0:
                    continue
                if not graph.is_compatible(recv_id, med):
                    continue
                dist, cost = graph.transport_cost(donor_id, recv_id, med)
                transfer_qty = min(med.quantity, demand_qty)
                saved = transfer_qty * med.unit_value
                net = saved - cost
                if net > best_net and net > 0:
                    best_net = net
                    best = (recv_id, dist, cost, transfer_qty, saved)

            if best:
                recv_id, dist, cost, qty, saved = best
                t = Transfer(
                    id=uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"{med.id}:{donor_id}:{recv_id}:{qty}",
                    ).hex,
                    medicine=med,
                    quantity=qty,
                    donor=graph.facilities[donor_id],
                    receiver=graph.facilities[recv_id],
                    distance_km=dist,
                    transport_cost=cost,
                    saved_value=saved,
                    urgency=med.urgency_score,
                )
                transfers.append(t)
                remaining_demand[recv_id][med.name] -= qty

        return transfers


# ──────────────────────────────────────────────
# 6.  Sample Data Generator
# ──────────────────────────────────────────────

def generate_sample_data() -> TransportGraph:
    """Create a realistic demo dataset of Indian healthcare facilities."""
    random.seed(42)

    medicine_catalog = [
        ("Amoxicillin 500mg", "Antibiotic", StorageCondition.AMBIENT, 2.50, "Rx"),
        ("Paracetamol 500mg", "Analgesic", StorageCondition.AMBIENT, 0.80, "OTC"),
        ("Insulin Glargine", "Endocrine", StorageCondition.REFRIGERATED, 45.00, "Rx"),
        ("Metformin 850mg", "Endocrine", StorageCondition.AMBIENT, 1.20, "Rx"),
        ("Morphine 10mg", "Analgesic", StorageCondition.AMBIENT, 8.00, "Controlled"),
        ("Azithromycin 250mg", "Antibiotic", StorageCondition.AMBIENT, 3.00, "Rx"),
        ("Ondansetron 4mg", "Antiemetic", StorageCondition.AMBIENT, 5.50, "Rx"),
        ("Epinephrine 1mg", "Emergency", StorageCondition.REFRIGERATED, 25.00, "Rx"),
        ("COVID Vaccine", "Vaccine", StorageCondition.FROZEN, 18.00, "Rx"),
        ("Rabies Vaccine", "Vaccine", StorageCondition.REFRIGERATED, 35.00, "Rx"),
        ("Diazepam 5mg", "Sedative", StorageCondition.AMBIENT, 4.00, "Controlled"),
        ("Ciprofloxacin 500mg", "Antibiotic", StorageCondition.AMBIENT, 2.00, "Rx"),
    ]

    facilities_info = [
        ("Apollo Hospital Mumbai", 19.076, 72.877, "Mumbai",
         {StorageCondition.AMBIENT, StorageCondition.REFRIGERATED, StorageCondition.FROZEN}, True),
        ("AIIMS Delhi", 28.567, 77.210, "Delhi",
         {StorageCondition.AMBIENT, StorageCondition.REFRIGERATED, StorageCondition.FROZEN}, True),
        ("CMC Vellore", 12.916, 79.132, "Vellore",
         {StorageCondition.AMBIENT, StorageCondition.REFRIGERATED}, True),
        ("PHC Raichur", 16.212, 77.355, "Raichur",
         {StorageCondition.AMBIENT, StorageCondition.REFRIGERATED}, False),
        ("District Hospital Bhopal", 23.259, 77.413, "Bhopal",
         {StorageCondition.AMBIENT, StorageCondition.REFRIGERATED}, True),
        ("Fortis Bangalore", 12.972, 77.594, "Bangalore",
         {StorageCondition.AMBIENT, StorageCondition.REFRIGERATED, StorageCondition.FROZEN}, True),
        ("Rural Clinic Dharwad", 15.459, 75.007, "Dharwad",
         {StorageCondition.AMBIENT}, False),
        ("Medanta Gurgaon", 28.440, 77.042, "Gurgaon",
         {StorageCondition.AMBIENT, StorageCondition.REFRIGERATED, StorageCondition.FROZEN}, True),
        ("JIPMER Puducherry", 11.943, 79.808, "Puducherry",
         {StorageCondition.AMBIENT, StorageCondition.REFRIGERATED, StorageCondition.FROZEN}, True),
        ("PHC Satara", 17.686, 74.000, "Satara",
         {StorageCondition.AMBIENT, StorageCondition.REFRIGERATED}, False),
    ]

    graph = TransportGraph()

    facilities: List[Facility] = []
    for name, lat, lon, city, storage, controlled in facilities_info:
        fac = Facility(
            id=str(uuid.uuid4())[:8],
            name=name,
            lat=lat,
            lon=lon,
            city=city,
            storage_capabilities=storage,
            can_handle_controlled=controlled,
        )
        facilities.append(fac)
        graph.add_facility(fac)

    # Generate inventory: some facilities get surplus, some get shortage
    today = date.today()
    for i, fac in enumerate(facilities):
        # Each facility gets 4-8 random medicines
        n_meds = random.randint(4, 8)
        chosen = random.sample(medicine_catalog, min(n_meds, len(medicine_catalog)))
        for name, cat, storage, val, reg in chosen:
            if storage not in fac.storage_capabilities:
                continue
            if reg == "Controlled" and not fac.can_handle_controlled:
                continue
            # Some stock will be expiring soon (within 7-60 days)
            # Some will be fine (60-365 days)
            if random.random() < 0.4:
                exp_days = random.randint(3, 45)  # expiring soon
            else:
                exp_days = random.randint(60, 365)
            qty = random.randint(20, 500)
            med = Medicine(
                id=str(uuid.uuid4())[:8],
                name=name,
                batch=f"BATCH-{random.randint(1000, 9999)}",
                quantity=qty,
                expiry=today + timedelta(days=exp_days),
                storage=storage,
                category=cat,
                unit_value=val,
                regulatory_class=reg,
            )
            fac.inventory.append(med)

    # Generate demand
    for fac in facilities:
        n_demands = random.randint(2, 5)
        for _ in range(n_demands):
            med_name = random.choice(medicine_catalog)[0]
            fac.demand[med_name] = random.randint(30, 300)

    # Build transport edges
    graph.build_edges(max_distance_km=800)

    return graph


# ──────────────────────────────────────────────
# 7.  Orchestrator — Ties Everything Together
# ──────────────────────────────────────────────

class MedRescueEngine:
    """
    Main engine that combines all DSA components to produce
    optimal transfer recommendations.
    """

    def __init__(self):
        self.graph: TransportGraph = generate_sample_data()
        self.heap = ExpiryHeap()
        self.matcher = BipartiteMatcher()
        self.transfers: List[Transfer] = []
        self.approved_transfers: List[Transfer] = []
        self._build_heap()

    def _build_heap(self):
        """Populate the expiry heap from all facility inventories."""
        self.heap = ExpiryHeap()
        for fid, fac in self.graph.facilities.items():
            for med in fac.inventory:
                if not med.is_expired and med.quantity > 0:
                    self.heap.push(med)

    def run_bipartite_matching(self) -> List[Transfer]:
        """Run capacity-aware weighted matching for transfer recommendations."""
        self.matcher.build(self.graph, self.heap)
        self.transfers = self.matcher.solve(self.graph)
        self.transfers.sort(key=lambda t: t.urgency)
        return self.transfers

    def run_greedy_allocation(self) -> List[Transfer]:
        """Run greedy allocation for quick suggestions."""
        self.transfers = GreedyAllocator.allocate(self.graph)
        self.transfers.sort(key=lambda t: t.urgency)
        return self.transfers

    def get_dashboard_stats(self) -> dict:
        total_meds = 0
        total_value = 0.0
        expiring_soon = 0
        expired = 0
        total_demand = 0

        for fid, fac in self.graph.facilities.items():
            for med in fac.inventory:
                total_meds += med.quantity
                if not med.is_expired:
                    total_value += med.quantity * med.unit_value
                if med.is_expired:
                    expired += med.quantity
                elif med.days_until_expiry <= 30:
                    expiring_soon += med.quantity
            for _, qty in fac.demand.items():
                total_demand += qty

        all_transfers = self.transfers + self.approved_transfers
        transfer_savings = sum(t.saved_value - t.transport_cost for t in all_transfers)
        wastage_prevented = sum(t.saved_value for t in all_transfers)

        return {
            "total_facilities": len(self.graph.facilities),
            "total_medicines": total_meds,
            "total_value": round(total_value, 2),
            "expiring_soon": expiring_soon,
            "expired": expired,
            "total_demand": total_demand,
            "active_transfers": len(all_transfers),
            "transfer_savings": round(transfer_savings, 2),
            "wastage_prevented": round(wastage_prevented, 2),
        }

    def get_expiry_timeline(self) -> List[dict]:
        """Return medicines grouped by expiry buckets."""
        buckets = {
            "0-7 days": 0,
            "8-14 days": 0,
            "15-30 days": 0,
            "31-60 days": 0,
            "61-90 days": 0,
            "90+ days": 0,
        }
        for fid, fac in self.graph.facilities.items():
            for med in fac.inventory:
                d = med.days_until_expiry
                if d <= 0:
                    continue
                elif d <= 7:
                    buckets["0-7 days"] += med.quantity
                elif d <= 14:
                    buckets["8-14 days"] += med.quantity
                elif d <= 30:
                    buckets["15-30 days"] += med.quantity
                elif d <= 60:
                    buckets["31-60 days"] += med.quantity
                elif d <= 90:
                    buckets["61-90 days"] += med.quantity
                else:
                    buckets["90+ days"] += med.quantity
        return [{"range": k, "count": v} for k, v in buckets.items()]

    def get_category_breakdown(self) -> List[dict]:
        cats: Dict[str, int] = defaultdict(int)
        for fid, fac in self.graph.facilities.items():
            for med in fac.inventory:
                cats[med.category] += med.quantity
        return [{"category": k, "count": v} for k, v in sorted(cats.items(), key=lambda x: -x[1])]

    def get_top_urgent(self, n: int = 10) -> List[dict]:
        """Top n most urgent medicines from the heap."""
        meds = self.heap.to_sorted_list()[:n]
        result = []
        # find which facility each medicine is in
        med_fac = {}
        for fid, fac in self.graph.facilities.items():
            for m in fac.inventory:
                med_fac[m.id] = fac.name
        for m in meds:
            d = m.to_dict()
            d["facility"] = med_fac.get(m.id, "Unknown")
            result.append(d)
        return result

    def approve_transfer(self, transfer_id: str) -> Optional[dict]:
        for t in self.transfers:
            if t.id == transfer_id:
                donor_stock = next(
                    (medicine for medicine in t.donor.inventory if medicine.id == t.medicine.id),
                    None,
                )
                demand = t.receiver.demand.get(t.medicine.name, 0)
                if donor_stock is None or donor_stock.quantity < t.quantity or demand < t.quantity:
                    raise ValueError("Transfer is no longer feasible; refresh recommendations.")

                t.status = TransferStatus.APPROVED
                donor_stock.quantity -= t.quantity
                t.receiver.demand[t.medicine.name] = demand - t.quantity
                self.approved_transfers.append(t)
                self._build_heap()
                self.run_bipartite_matching()
                return t.to_dict()
        return None
