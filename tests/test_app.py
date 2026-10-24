import unittest

import app as medrescue_app
from dsa_engine import MedRescueEngine


class MedRescueApiTests(unittest.TestCase):
    def setUp(self):
        self.original_engine = medrescue_app.engine
        medrescue_app.engine = MedRescueEngine()
        medrescue_app.engine.run_bipartite_matching()
        self.client = medrescue_app.app.test_client()

    def tearDown(self):
        medrescue_app.engine = self.original_engine

    def test_dashboard_and_static_frontend_are_served(self):
        page = self.client.get("/")
        stats = self.client.get("/api/stats")

        self.assertEqual(page.status_code, 200)
        self.assertIn(b"MedRescue", page.data)
        page.close()
        self.assertEqual(stats.status_code, 200)
        self.assertGreater(stats.json["total_facilities"], 0)

    def test_transfer_api_validates_algorithm(self):
        self.assertEqual(self.client.get("/api/transfers?algo=greedy").status_code, 200)
        response = self.client.get("/api/transfers?algo=unknown")
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json)

    def test_approval_updates_inventory_demand_and_traceable_history(self):
        recommendations = self.client.get("/api/transfers").json
        self.assertTrue(recommendations, "sample data should produce a feasible transfer")
        transfer = recommendations[0]
        donor = medrescue_app.engine.graph.facilities[transfer["donor_id"]]
        receiver = medrescue_app.engine.graph.facilities[transfer["receiver_id"]]
        medicine = next(item for item in donor.inventory if item.id == transfer["medicine_id"])
        quantity_before = medicine.quantity
        demand_before = receiver.demand[transfer["medicine_name"]]

        response = self.client.post(f"/api/transfers/{transfer['id']}/approve")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "approved")
        self.assertEqual(medicine.quantity, quantity_before - transfer["quantity"])
        self.assertEqual(
            receiver.demand[transfer["medicine_name"]],
            demand_before - transfer["quantity"],
        )
        self.assertEqual(len(medrescue_app.engine.approved_transfers), 1)
        self.assertEqual(
            self.client.post(f"/api/transfers/{transfer['id']}/approve").status_code,
            404,
        )

    def test_algorithm_comparison_does_not_replace_active_recommendations(self):
        recommendations = self.client.get("/api/transfers?algo=greedy").json
        active_transfers = medrescue_app.engine.transfers

        response = self.client.get("/api/compare-algorithms")

        self.assertEqual(response.status_code, 200)
        self.assertIs(medrescue_app.engine.transfers, active_transfers)
        self.assertEqual(
            [item.id for item in active_transfers],
            [item["id"] for item in recommendations],
        )


if __name__ == "__main__":
    unittest.main()
