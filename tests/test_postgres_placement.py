#!/usr/bin/env python3
"""invidious-postgres stays on the CORE side of the Deco backhaul (homelab#2075).

invidious, the only pod that queries this DB, runs on a CORE worker. The
primary was on k8s-node-hpm-01, which is alone on the MAIN side of the Deco
Wi-Fi backhaul (homelab architecture/network-topology.md), so every query
crossed it. hpm-01 is also an untainted control plane + etcd member: the
n8n-workflow#301 DB drops happened there.

So the Cluster carries a REQUIRED node affinity, in one term:
  * homelab/segment In [core]   -- the backhaul side (audited node label)
  * control-plane DoesNotExist  -- the n8n-workflow#352 pattern
Without tolerations that leaves node-01/node-02. longhorn-cnpg is
dataLocality: disabled, so the volume follows the pod.

Renders overlays/: the cluster gets the rendered output, not the raw file.

Run:  python3 -m unittest tests.test_postgres_placement -v
"""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SEGMENT = "homelab/segment"
CONTROL_PLANE = "node-role.kubernetes.io/control-plane"


def rendered():
    out = subprocess.run(["kubectl", "kustomize", str(ROOT / "overlays")],
                         check=True, capture_output=True, text=True).stdout
    return [d for d in yaml.safe_load_all(out) if d]


def one(docs, kind, name):
    hits = [d for d in docs if d["kind"] == kind and d["metadata"]["name"] == name]
    if len(hits) != 1:
        raise AssertionError(f"expected exactly one {kind}/{name}, got {len(hits)}")
    return hits[0]


def pinned_to_core(node_affinity):
    """True iff EVERY required term keeps the pod on CORE and off control planes.

    Required terms are ORed, so one term without both expressions lets the
    pod onto MAIN or onto a control plane.
    """
    req = (node_affinity or {}).get("requiredDuringSchedulingIgnoredDuringExecution") or {}
    terms = req.get("nodeSelectorTerms") or []
    if not terms:
        return False

    def ok(term):
        exprs = term.get("matchExpressions") or []
        core = any(e.get("key") == SEGMENT and e.get("operator") == "In"
                   and e.get("values") == ["core"] for e in exprs)
        no_cp = any(e.get("key") == CONTROL_PLANE and e.get("operator") == "DoesNotExist"
                    for e in exprs)
        return core and no_cp

    return all(ok(t) for t in terms)


def _req(*terms):
    return {"requiredDuringSchedulingIgnoredDuringExecution": {"nodeSelectorTerms": list(terms)}}


CORE = {"key": SEGMENT, "operator": "In", "values": ["core"]}
NO_CP = {"key": CONTROL_PLANE, "operator": "DoesNotExist"}


class Checker(unittest.TestCase):
    """The checker itself, so a green result is not a vacuous one."""

    def test_rejects_missing_and_preferred_only(self):
        self.assertFalse(pinned_to_core(None))
        self.assertFalse(pinned_to_core({"preferredDuringSchedulingIgnoredDuringExecution": [
            {"weight": 100, "preference": {"matchExpressions": [CORE, NO_CP]}}]}))

    def test_rejects_either_half_alone(self):
        self.assertFalse(pinned_to_core(_req({"matchExpressions": [CORE]})))
        self.assertFalse(pinned_to_core(_req({"matchExpressions": [NO_CP]})))

    def test_rejects_main_or_both_segments(self):
        self.assertFalse(pinned_to_core(_req({"matchExpressions": [
            {"key": SEGMENT, "operator": "In", "values": ["main"]}, NO_CP]})))
        self.assertFalse(pinned_to_core(_req({"matchExpressions": [
            {"key": SEGMENT, "operator": "In", "values": ["core", "main"]}, NO_CP]})))

    def test_rejects_an_ored_term_without_it(self):
        self.assertFalse(pinned_to_core(_req({"matchExpressions": [CORE, NO_CP]},
                                             {"matchExpressions": [NO_CP]})))

    def test_accepts_both_in_one_term(self):
        self.assertTrue(pinned_to_core(_req({"matchExpressions": [CORE, NO_CP]})))


class Placement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cluster = one(rendered(), "Cluster", "invidious-postgres")

    def test_cluster_is_pinned_to_core(self):
        aff = self.cluster["spec"].get("affinity") or {}
        self.assertTrue(pinned_to_core(aff.get("nodeAffinity")), aff)

    def test_cluster_is_single_instance(self):
        # A second instance would need its own anti-affinity answer: with
        # only node-01/02 eligible, both could land on one node (n8n today).
        self.assertEqual(self.cluster["spec"]["instances"], 1)


if __name__ == "__main__":
    unittest.main()
