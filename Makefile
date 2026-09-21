.PHONY: setup data smoke review eval eval-test test clean

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

review:                    ## Re-export the human-review sample from the current eval set
	$(PY) -m triage.export_review

eval:                      ## Score the baseline on the DEV split (this is the command to run)
	$(PY) -m triage.evaluate --split dev

eval-test:                 ## Score the baseline on the HELD-OUT TEST split. Do not use while tuning.
	$(PY) -m triage.evaluate --split test

clean:
	rm -rf results/*.json results/*.md

test:                      ## Run the checks that need no API key
	$(PY) -m pytest tests/ -q
