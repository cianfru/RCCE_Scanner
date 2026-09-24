"""Validated policy artifact; absent or invalid artifacts always leave CTO in shadow.

After a study passes: python -m cto_policy REPORT.json POLICY.json
Deploy with CTO_POLICY_PATH pointing to POLICY.json and keep the report beside it.
"""
import json
import os
from pathlib import Path
from functools import lru_cache
from backtest.cto_study import fingerprint, promotion_gate, STUDY_VERSION
from decision_pipeline import VERSION
from opportunities import POLICY_VERSION, VARIANTS


def validate_artifact(artifact, report):
    if artifact.get("decision_version") != VERSION or artifact.get("policy_version") != POLICY_VERSION:
        raise ValueError("Policy engine version mismatch")
    if report.get("decision_version") != VERSION:
        raise ValueError("Report decision version mismatch")
    if report.get("version") != STUDY_VERSION or artifact.get("report_hash") != fingerprint(report):
        raise ValueError("Study version or report checksum mismatch")
    if artifact.get("policy") != report.get("selected") or not promotion_gate(report)["approved"]:
        raise ValueError("Study has not passed promotion criteria")
    if artifact.get("scope") != report.get("scope") or not report.get("scope"):
        raise ValueError("Policy scope mismatch")
    policy = artifact["policy"]
    if len(policy) != 2 or policy[0] not in VARIANTS or policy[1] not in (1, 2, 3):
        raise ValueError("Unsupported CTO policy")
    return tuple(policy)


@lru_cache(maxsize=1)
def active_policy():
    path = os.environ.get("CTO_POLICY_PATH")
    if not path:
        return ("baseline", 1), "shadow", None, {}
    try:
        path = Path(path)
        artifact = json.loads(path.read_text())
        report = json.loads((path.parent / artifact["report_file"]).read_text())
        policy = validate_artifact(artifact, report)
        return policy, "validated", artifact["report_hash"], artifact["scope"]
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return ("baseline", 1), "shadow", "Invalid policy artifact; baseline retained", {}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("policy", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    if not promotion_gate(report)["approved"]:
        parser.error("Promotion blocked: " + "; ".join(promotion_gate(report)["reasons"]))
    if args.report.resolve().parent != args.policy.resolve().parent:
        parser.error("Keep the report and policy artifact in the same directory")
    artifact = dict(decision_version=VERSION, policy_version=POLICY_VERSION,
                    report_hash=fingerprint(report), report_file=args.report.name, policy=report["selected"], scope=report["scope"])
    validate_artifact(artifact, report)
    with args.policy.open("x") as out:
        json.dump(artifact, out, indent=2)

if __name__ == "__main__":
    main()
