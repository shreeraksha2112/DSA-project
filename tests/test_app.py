import unittest
from datetime import date, timedelta

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
        self.assertIn(b"Smart Stock Alerts", page.data)
        self.assertIn(b'id="inventoryForm"', page.data)
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

    def test_inventory_can_be_added_adjusted_and_deleted(self):
        facility = next(
            item for item in medrescue_app.engine.graph.facilities.values()
            if "ambient" in {condition.value for condition in item.storage_capabilities}
        )
        payload = {
            "name": "Test Medicine",
            "batch": "TEST-001",
            "quantity": 24,
            "expiry": (date.today() + timedelta(days=90)).isoformat(),
            "storage": "ambient",
            "category": "Test",
            "unit_value": 2.5,
            "regulatory_class": "OTC",
        }

        added = self.client.post(
            f"/api/facilities/{facility.id}/inventory", json=payload
        )

        self.assertEqual(added.status_code, 201)
        medicine_id = added.json["id"]
        self.assertEqual(added.json["quantity"], 24)
        self.assertTrue(
            any(item.id == medicine_id for item in medrescue_app.engine.heap.to_sorted_list())
        )

        updated = self.client.patch(
            f"/api/facilities/{facility.id}/inventory/{medicine_id}",
            json={"quantity": 12},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json["quantity"], 12)

        deleted = self.client.delete(
            f"/api/facilities/{facility.id}/inventory/{medicine_id}"
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(
            self.client.delete(
                f"/api/facilities/{facility.id}/inventory/{medicine_id}"
            ).status_code,
            404,
        )

    def test_inventory_rejects_invalid_and_incompatible_stock(self):
        facility = next(
            item for item in medrescue_app.engine.graph.facilities.values()
            if not item.can_handle_controlled
        )
        payload = {
            "name": "Controlled Test",
            "batch": "TEST-002",
            "quantity": 1,
            "expiry": (date.today() + timedelta(days=90)).isoformat(),
            "storage": "ambient",
            "category": "Test",
            "unit_value": 2.5,
            "regulatory_class": "Controlled",
        }

        response = self.client.post(
            f"/api/facilities/{facility.id}/inventory", json=payload
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("controlled", response.json["error"])
        payload["regulatory_class"] = "OTC"
        payload["storage"] = "frozen"
        response = self.client.post(
            f"/api/facilities/{facility.id}/inventory", json=payload
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("store", response.json["error"])
        payload["storage"] = "ambient"
        payload["quantity"] = 0
        self.assertEqual(
            self.client.post(
                f"/api/facilities/{facility.id}/inventory", json=payload
            ).status_code,
            400,
        )
        payload["quantity"] = 1
        payload["regulatory_class"] = []
        response = self.client.post(
            f"/api/facilities/{facility.id}/inventory", json=payload
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Regulatory class", response.json["error"])
        self.assertEqual(
            self.client.post("/api/facilities/missing/inventory", json=payload).status_code,
            404,
        )

    def test_smart_insights_report_local_shortages_and_expiring_lots(self):
        facility = next(iter(medrescue_app.engine.graph.facilities.values()))
        medicine = facility.inventory[0]
        medicine.expiry = date.today() + timedelta(days=7)
        facility.demand[medicine.name] = 100000

        insights = self.client.get("/api/insights")

        self.assertEqual(insights.status_code, 200)
        self.assertTrue(
            any(
                item["facility_id"] == facility.id
                and item["medicine_name"] == medicine.name
                and item["shortage"] > 0
                for item in insights.json["shortages"]
            )
        )
        self.assertTrue(
            any(
                item["medicine_id"] == medicine.id
                for item in insights.json["expiring_lots"]
            )
        )


if __name__ == "__main__":
    unittest.main()
