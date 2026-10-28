# research_make_tau_drift_pack.py: a dev script. Builds tau_drift_refund_v1 (research/tau_drift.py) as a policy_drift pack and
# runs the pack audits on it:
#   uv run python scripts/research_make_tau_drift_pack.py <out.zip>
# Uses: research/tau_drift.py, research/pack_audits.py.
import io
import json
import sys
import zipfile

from app.research import pack_audits, tau_drift


def build_pack() -> bytes:
    files = tau_drift.build()
    files["manifest.json"] = json.dumps({"kind": "policy_drift", "name": "tau_drift_refund_v1", "version": "1.0.0", "company": "Finebase Labs", "timezone": "Asia/Colombo",
                                         "currency": "LKR", "created_by": "research_lab", "license": "generated for the Finebrain Research Lab",
                                         "files": sorted(files)}, indent=1)  # no exposure check: generated text has nothing to search for
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.writestr(zipfile.ZipInfo(path, (2026, 1, 1, 0, 0, 0)), files[path])
    return buffer.getvalue()


if __name__ == "__main__":
    data = build_pack()
    open(sys.argv[1], "wb").write(data)
    _, sha, checks = pack_audits.audit_pack(data)
    print(f"{sys.argv[1]}: {len(data)} bytes, sha256 {sha[:16]}, verdict {pack_audits.verdict(checks)}")
    for check in checks:
        print(f"  {check['status']:<15} {check['label']}: {check['detail']}", *(f"\n      {line}" for line in check["lines"][:5]))
