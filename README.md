# MedRescue

MedRescue is a Flask-backed demonstration dashboard for reducing medicine expiry waste by recommending stock transfers between healthcare facilities. It combines an expiry min-heap, a distance-weighted transport graph, capacity-aware weighted matching, and expiry-priority greedy allocation.

## Run locally

1. Create and activate a Python virtual environment.
2. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Start the application:

   ```powershell
   python app.py
   ```

4. Open <http://localhost:5000>.

The Flask application serves the frontend and its `/api` endpoints from the same origin. The included facility, inventory, and demand data is generated for demonstration and held in memory; approved transfers update the running inventory and demand, and restarting the server restores the demo data.

## Tests

Run the API and transfer-flow tests with:

```powershell
python -m unittest discover -s tests -v
```

## Main API

| Endpoint | Description |
| --- | --- |
| `GET /api/stats` | Dashboard inventory and transfer metrics |
| `GET /api/transfers?algo=bipartite` | Capacity-aware weighted transfer recommendations |
| `GET /api/transfers?algo=greedy` | Expiry-priority greedy recommendations |
| `POST /api/transfers/{id}/approve` | Approves a recommendation and updates stock and demand |
| `GET /api/facilities` | Facility summaries |
| `GET /api/facilities/{id}` | Facility inventory and demand |
| `GET /api/network` | Transport graph nodes and edges |
| `GET /api/heap-state` | Expiry-priority queue contents |
| `GET /api/compare-algorithms` | Compares both recommendation strategies |
