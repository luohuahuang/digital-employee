"""
Patch script: add judge_results_json and rules_result_json to existing
seed exam runs. Safe to re-run — only writes rows where these fields are NULL.

Run from the project root:
    python scripts/update_seed_judge_data.py
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.db.database import SessionLocal, init_db
from web.db.models import ExamRun

# Import data tables from seed script
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from seed_exam_data import JUDGE_RESULTS, RULES_RESULTS


def patch():
    init_db()   # ensures new columns exist via migration
    db = SessionLocal()
    try:
        # Find runs that are missing judge data
        runs = db.query(ExamRun).filter(
            ExamRun.judge_results_json.is_(None),
            ExamRun.status == "done",
            ExamRun.prompt_version_num.isnot(None),
        ).all()

        updated = 0
        skipped = 0
        for run in runs:
            v_key   = f"v{run.prompt_version_num}"
            exam_id = run.exam_id

            judge = JUDGE_RESULTS.get(exam_id, {}).get(v_key)
            rules = RULES_RESULTS.get(exam_id, {}).get(v_key)

            if judge is None and rules is None:
                skipped += 1
                continue

            run.judge_results_json = json.dumps(judge or {}, ensure_ascii=False)
            run.rules_result_json  = json.dumps(rules or [], ensure_ascii=False)
            updated += 1

        db.commit()
        print(f"✅ Updated {updated} runs with judge/rules data  ({skipped} skipped — no matching data)")

    finally:
        db.close()


if __name__ == "__main__":
    patch()
