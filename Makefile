.PHONY: setup data smoke review review-round2 import-review import-review-round2 sweep sweep-apply eval eval-test eval-router eval-router-test eval-answers eval-answers-test answer answer-test spend test clean

PY := .venv/bin/python

setup:                     ## Create venv and install dependencies
	uv venv --python 3.11
	uv pip install --python $(PY) -e ".[dev]"

data:                      ## Fetch upstream dataset and build the eval set (needs API key for label drafting)
	$(PY) -m triage.build_dataset

smoke:                     ## Cheap end-to-end pipeline check on ~16 tickets (not an eval)
	$(PY) -m triage.build_dataset --smoke 16 --model gpt-5.6-luna --effort none
	$(PY) -m triage.evaluate --split dev --smoke --model gpt-5.6-luna --effort none
	$(PY) -m triage.export_review --smoke -n 8
	$(PY) -m triage.import_review --smoke

spend:                     ## Print total API spend recorded in results/spend_log.jsonl
	@$(PY) -c "from triage.llm import total_spend; print(f'Project API spend to date: \$${total_spend():.4f}')"

review:                    ## Re-export the round-1 review sample from the current eval set
	$(PY) -m triage.export_review

review-round2:             ## Draw a fresh random block from the tickets no round has reviewed
	$(PY) -m triage.export_review --round 2 --random-controls 30

import-review:             ## Fold the corrected round-1 review CSV back into the eval set
	$(PY) -m triage.import_review

import-review-round2:      ## Fold the corrected round-2 CSV back into the eval set
	$(PY) -m triage.import_review --round 2

sweep:                     ## Show which labels the current brief's rules would change
	$(PY) -m triage.sweep --dry-run

sweep-apply:               ## Apply those rule changes to the eval set (logged to results/)
	$(PY) -m triage.sweep --apply

eval:                      ## Score the baseline on the DEV split (this is the command to run)
	$(PY) -m triage.evaluate --split dev

eval-test:                 ## Score the baseline on the HELD-OUT TEST split. Do not use while tuning.
	$(PY) -m triage.evaluate --split test

eval-router:               ## Score the router on dev and compare it to results/latest_dev.json
	$(PY) -m triage.evaluate_router --split dev

eval-router-test:          ## Score the router on the HELD-OUT TEST split. Do not use while tuning.
	$(PY) -m triage.evaluate_router --split test

eval-answers:              ## Score a candidates.jsonl against the DEV answer eval (needs ANSWERS=path/to/candidates.jsonl)
	$(PY) -m triage.eval_answers --split dev --answers $(ANSWERS)

eval-answers-test:         ## Score against the HELD-OUT TEST answer eval. Do not use while tuning.
	$(PY) -m triage.eval_answers --split test --answers $(ANSWERS)

answer:                    ## Run the full router+answerer+judge pipeline on DEV and score it
	$(PY) -m triage.evaluate_answerer --split dev

answer-test:                ## Run the full pipeline on the HELD-OUT TEST split. Do not use while tuning.
	$(PY) -m triage.evaluate_answerer --split test

clean:
	rm -rf results/*.json results/*.md

test:                      ## Run the checks that need no API key
	$(PY) -m pytest tests/ -q
