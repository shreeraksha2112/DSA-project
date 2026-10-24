"""
MedRescue — Flask REST API
===========================
Serves the DSA engine results to the frontend dashboard.
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dsa_engine import MedRescueEngine
import os

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

# Initialize the engine (builds sample data + runs matching)
engine = MedRescueEngine()
engine.run_bipartite_matching()


# ── Static Files ──────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ── Dashboard Stats ──────────────────────────

@app.route("/api/stats")
def stats():
    return jsonify(engine.get_dashboard_stats())


@app.route("/api/expiry-timeline")
def expiry_timeline():
    return jsonify(engine.get_expiry_timeline())


@app.route("/api/category-breakdown")
def category_breakdown():
    return jsonify(engine.get_category_breakdown())


@app.route("/api/top-urgent")
def top_urgent():
    n = request.args.get("n", 10, type=int)
    return jsonify(engine.get_top_urgent(n))


# ── Facilities ────────────────────────────────

@app.route("/api/facilities")
def facilities():
    result = []
    for fid, fac in engine.graph.facilities.items():
        result.append(fac.to_dict(include_inventory=False))
    return jsonify(result)


@app.route("/api/facilities/<fid>")
def facility_detail(fid):
    fac = engine.graph.facilities.get(fid)
    if not fac:
        return jsonify({"error": "Facility not found"}), 404
    return jsonify(fac.to_dict(include_inventory=True))


@app.route("/api/facilities/<fid>/inventory", methods=["POST"])
def add_medicine(fid):
    try:
        medicine = engine.add_medicine(fid, request.get_json(silent=True))
    except LookupError as error:
        return jsonify({"error": str(error)}), 404
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(medicine), 201


@app.route("/api/facilities/<fid>/inventory/<medicine_id>", methods=["PATCH"])
def update_medicine_quantity(fid, medicine_id):
    payload = request.get_json(silent=True)
    quantity = payload.get("quantity") if isinstance(payload, dict) else None
    try:
        medicine = engine.update_medicine_quantity(fid, medicine_id, quantity)
    except LookupError as error:
        return jsonify({"error": str(error)}), 404
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    if medicine is None:
        return jsonify({"error": "Medicine not found"}), 404
    return jsonify(medicine)


@app.route("/api/facilities/<fid>/inventory/<medicine_id>", methods=["DELETE"])
def delete_medicine(fid, medicine_id):
    try:
        deleted = engine.delete_medicine(fid, medicine_id)
    except LookupError as error:
        return jsonify({"error": str(error)}), 404
    if not deleted:
        return jsonify({"error": "Medicine not found"}), 404
    return jsonify({"status": "deleted", "medicine_id": medicine_id})


@app.route("/api/insights")
def inventory_insights():
    return jsonify(engine.get_inventory_insights())


# ── Network Graph ─────────────────────────────

@app.route("/api/network")
def network():
    return jsonify(engine.graph.to_dict())


# ── Transfers ─────────────────────────────────

@app.route("/api/transfers")
def transfers():
    algo = request.args.get("algo", "bipartite")
    if algo == "greedy":
        engine.run_greedy_allocation()
    elif algo == "bipartite":
        engine.run_bipartite_matching()
    else:
        return jsonify({"error": "Algorithm must be 'bipartite' or 'greedy'."}), 400
    return jsonify([t.to_dict() for t in engine.approved_transfers + engine.transfers])


@app.route("/api/transfers/<tid>/approve", methods=["POST"])
def approve_transfer(tid):
    try:
        result = engine.approve_transfer(tid)
    except ValueError as error:
        return jsonify({"error": str(error)}), 409
    if result:
        return jsonify(result)
    return jsonify({"error": "Transfer not found"}), 404


# ── Algorithm Comparison ──────────────────────

@app.route("/api/compare-algorithms")
def compare_algorithms():
    current_transfers = engine.transfers
    bipartite_transfers = engine.run_bipartite_matching()
    bi_savings = sum(t.saved_value - t.transport_cost for t in bipartite_transfers)
    bi_wastage = sum(t.saved_value for t in bipartite_transfers)
    bi_count = len(bipartite_transfers)

    greedy_transfers = engine.run_greedy_allocation()
    gr_savings = sum(t.saved_value - t.transport_cost for t in greedy_transfers)
    gr_wastage = sum(t.saved_value for t in greedy_transfers)
    gr_count = len(greedy_transfers)

    engine.transfers = current_transfers

    return jsonify({
        "bipartite": {
            "name": "Bipartite Matching",
            "transfers": bi_count,
            "net_savings": round(bi_savings, 2),
            "wastage_prevented": round(bi_wastage, 2),
        },
        "greedy": {
            "name": "Greedy Allocation",
            "transfers": gr_count,
            "net_savings": round(gr_savings, 2),
            "wastage_prevented": round(gr_wastage, 2),
        },
    })


# ── Heap Visualization ───────────────────────

@app.route("/api/heap-state")
def heap_state():
    meds = engine.heap.to_sorted_list()[:20]
    med_fac = {}
    for fid, fac in engine.graph.facilities.items():
        for m in fac.inventory:
            med_fac[m.id] = fac.name
    result = []
    for m in meds:
        d = m.to_dict()
        d["facility"] = med_fac.get(m.id, "Unknown")
        result.append(d)
    return jsonify(result)


if __name__ == "__main__":
    print("\n[MedRescue] Server Starting...")
    print("  Dashboard: http://localhost:5000")
    print("  API Base:  http://localhost:5000/api/\n")
    app.run(debug=True, port=5000)
